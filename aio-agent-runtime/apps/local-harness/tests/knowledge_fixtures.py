"""Synthetic parser/model adapters for real PostgreSQL invariants; actual Docker parsing is a separate suite."""

import base64
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import os

import pytest
from sqlalchemy import select, update

from app.db import schema as s
from app.knowledge.catalog import current_knowledge
from app.knowledge.contracts import DocumentCreate, EmbeddingCreate, KnowledgeCreate
from app.knowledge.embedding import Embedder, EmbeddingStore
from app.knowledge.jobs import KnowledgeJobs
from app.knowledge.retrieval import KnowledgeRetrieval
from app.knowledge.service import KnowledgeService
from app.knowledge.worker import KnowledgeWorker
from app.runtime.actions import canonical_digest
from app.runtime.execution import ExecutionStore
from app.runtime.service import PlatformService
from app.workspaces.storage import BlobStore


class SyntheticEmbeddingFactory:
    def __init__(self):
        self.requests = []
        self.fail = False
        self.unknown_usage = False

    def create(self, definition):
        outer = self

        class Client:
            async def embed(self, texts):
                outer.requests.append(list(texts))
                if outer.fail:
                    raise RuntimeError("Synthetic lost embedding response after billing boundary")
                vectors = []
                for text in texts:
                    if any(word in text.lower() for word in ("休假", "年假", "vacation", "leave")):
                        vectors.append([1.0, 0.0, 0.0])
                    elif any(word in text.lower() for word in ("报销", "发票", "expense")):
                        vectors.append([0.0, 1.0, 0.0])
                    else:
                        vectors.append([0.0, 0.0, 1.0])
                return {
                    "vectors": vectors,
                    "input_tokens": None if outer.unknown_usage else 10,
                    "charge": None if outer.unknown_usage else Decimal("0.001000"),
                }

            async def close(self):
                pass

        return Client()


class SyntheticParserManager:
    def __init__(self, jobs):
        self.jobs, self.outputs, self.calls = jobs, {}, []
        self.hook = None

    async def call(self, operation, payload):
        self.jobs.authorize(operation, payload)
        self.calls.append(operation)
        spec = payload["spec"]
        base = {"binding_id": spec["binding_id"], "spec_digest": canonical_digest("aio-cell-spec-v1", spec)}
        if operation == "ensure":
            return {**base, "state": "ready"}
        if operation == "acknowledge":
            self.outputs.pop(spec["binding_id"], None)
            return {**base, "state": "acknowledged"}
        if operation == "stop":
            return {**base, "state": "destroyed"}
        if operation == "execute":
            # Only the explicitly synthetic UTF-8 fixture data is read here, never product document parsers.
            raw = base64.b64decode(next(i["content_b64"] for i in spec["inputs"] if i["path"] == "document.bin"))
            text = raw.decode("utf-8")
            data = {
                "schema_version": 1,
                "parser_version": "document-parser-v1",
                "format": "txt",
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "text_bytes": len(raw),
                "chunks": [
                    {
                        "ordinal": 0,
                        "text": text,
                        "location": {"kind": "lines", "line_start": 1, "line_end": 1},
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                ],
                "warnings": [],
            }
            encoded = json.dumps(data, ensure_ascii=False).encode()
            self.outputs[spec["binding_id"]] = encoded
            if self.hook:
                self.hook()
            return {
                **base,
                "dispatch_id": payload["dispatch_id"],
                "exit_code": 0,
                "error_code": None,
                "truncated": False,
                "stdout": json.dumps(
                    {
                        "status": "parsed",
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                        "bytes": len(encoded),
                        "chunks": 1,
                    }
                ),
            }
        assert operation == "finalize"
        output = self.outputs[spec["binding_id"]]
        return {
            **base,
            "state": "destroyed",
            "files": [
                {
                    "path": "parsed-document.json",
                    "sha256": hashlib.sha256(output).hexdigest(),
                    "bytes": len(output),
                    "content_b64": base64.b64encode(output).decode(),
                }
            ],
        }


@pytest.fixture
def knowledge_platform(tenant, tmp_path):
    t = dict(tenant)
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.user_id.in_([t["alice"].user_id, t["bob"].user_id]))
            .values(role="org_admin")
        )
    image = os.environ.get("AIO_TEST_DOCUMENT_IMAGE", "sha256:" + "2" * 64)
    settings = replace(
        t["settings"],
        artifact_root=(tmp_path / "blobs").resolve(),
        manager_url="http://127.0.0.1:9988",
        manager_token="synthetic-parser-manager-" + "p" * 40,
        document_profiles=({"id": "documents", "image_digest": image, "max_timeout_seconds": 120},),
        model_allowed_origins=frozenset({"https://embedding.example.test"}),
        model_secret_names=frozenset({"SYNTHETIC_EMBEDDING_KEY"}),
    )
    blobs = BlobStore(settings.artifact_root)
    knowledge = KnowledgeService(t["db"], settings, blobs)
    execution = ExecutionStore(t["db"], settings)
    jobs = KnowledgeJobs(t["db"], settings, knowledge)
    factory = SyntheticEmbeddingFactory()
    billing = EmbeddingStore(t["db"], settings, jobs, execution)
    embedder = Embedder(billing, factory)
    manager = SyntheticParserManager(jobs)
    t.update(
        settings=settings,
        knowledge=knowledge,
        jobs=jobs,
        billing=billing,
        embedder=embedder,
        embedding_factory=factory,
        manager=manager,
        store=execution,
        service=PlatformService(t["db"], settings),
        retrieval=KnowledgeRetrieval(t["db"], execution, embedder),
        blobs=blobs,
    )
    return t


def base(t, *, hybrid=False):
    model = None
    if hybrid:
        model = t["knowledge"].create_embedding_model(
            t["alice"],
            EmbeddingCreate(
                name="Synthetic semantic embedding",
                model="fixture-embedding",
                endpoint="https://embedding.example.test/v1/embeddings",
                secret_env="SYNTHETIC_EMBEDDING_KEY",
                dimensions=3,
                input_price_per_million=Decimal("100"),
                max_call_charge=Decimal("0.02"),
                batch_size=4,
            ),
        )
    return t["knowledge"].create(
        t["alice"],
        KnowledgeCreate(
            name="部门知识",
            description="Synthetic test knowledge",
            parser_profile="documents",
            embedding_model_id=model["id"] if model else None,
        ),
    )


def upload(t, kb, text, *, visibility="inherited", title="报销说明", document=None, revision=None):
    body = DocumentCreate(
        title=title,
        filename="source.txt",
        max_bytes=len(text.encode()),
        visibility=visibility,
        document_id=document,
        expected_revision=revision,
    )
    version = t["knowledge"].prepare_upload(t["alice"], kb["id"], body)
    t["knowledge"].upload(t["alice"], version["version_id"], text.encode())
    with t["db"].transaction(t["alice"]) as c:
        job = (
            c.execute(
                select(s.knowledge_jobs).where(
                    s.knowledge_jobs.c.org_id == t["org"], s.knowledge_jobs.c.version_id == version["version_id"]
                )
            )
            .mappings()
            .one()
        )
    return {**version, "job_id": job["id"]}


async def ingest(t):
    return await KnowledgeWorker(t["jobs"], t["manager"], t["embedder"], t["org"], "knowledge-test-worker").run_once()


def grant_search(t, kb, p):
    from app.admin.contracts import GrantCreate

    t["knowledge"].admin.set_grants(
        t["alice"],
        kb["id"],
        GrantCreate(subject_type="user", subject_id=p.user_id, actions=("knowledge.read", "knowledge.search")),
    )
    with t["db"].transaction(t["alice"]) as c:
        row = current_knowledge(c, t["alice"], kb["id"])
    if row["embedding_model_id"]:
        t["knowledge"].admin.set_grants(
            t["alice"],
            row["embedding_model_id"],
            GrantCreate(
                subject_type="user", subject_id=p.user_id, actions=("embedding_model.read", "embedding_model.use")
            ),
        )
