"""Real PostgreSQL/pgvector ownership, publication, billing and deletion invariants."""

import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update

from app.admin.contracts import AgentCreate, GrantCreate
from app.db import schema as s
from app.db.provisioning import provision_model
from app.knowledge.catalog import current_version
from app.knowledge.contracts import DocumentVisibility
from app.knowledge.retrieval import KnowledgeDriver
from app.platform_errors import PlatformError
from app.runtime.contracts import ModelTurn, PlannedCall
from app.runtime.worker import DurableWorker, ToolDrivers
from knowledge_fixtures import base, grant_search, ingest, upload


def test_isolated_parse_is_published_atomically_and_chinese_keywords_are_searchable(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    doc = upload(t, kb, "报销流程：月底前提交发票，餐费上限200元。")
    with t["db"].transaction(t["alice"]) as c:
        assert c.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar_one()
        assert c.execute(select(s.knowledge_chunks.c.id).where(s.knowledge_chunks.c.org_id == t["org"])).first() is None
    assert asyncio.run(ingest(t))["state"] == "ready"
    result = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "报销餐费发票", "preview:" + uuid4().hex))
    assert result["answerable"] and result["retrieval_mode"] == "lexical"
    assert result["matches"][0]["document_id"] == str(doc["document_id"])
    assert result["matches"][0]["location"]["line_start"] == 1
    assert t["manager"].calls == ["ensure", "execute", "finalize", "acknowledge"]
    assert not t["manager"].outputs


def test_restricted_documents_do_not_leak_through_shared_kb_search_or_citation(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    private = upload(t, kb, "内部薪酬规则：绝不可泄漏的测试内容", visibility="restricted", title="私有薪酬")
    asyncio.run(ingest(t))
    public = upload(t, kb, "员工报销规则：每月提交发票", visibility="inherited", title="共享报销")
    asyncio.run(ingest(t))
    grant_search(t, kb, t["bob"])
    rows = t["knowledge"].documents(t["bob"], kb["id"])
    assert [row["id"] for row in rows] == [public["document_id"]]
    result = asyncio.run(t["retrieval"].search(t["bob"], kb["id"], "薪酬规则", "preview:" + uuid4().hex))
    assert "绝不可泄漏" not in str(result)
    with pytest.raises(PlatformError):
        t["knowledge"].download(t["bob"], private["version_id"])
    own = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "薪酬", "preview:" + uuid4().hex))
    with pytest.raises(PlatformError):
        t["retrieval"].get_citation(t["bob"], UUID(own["matches"][0]["id"]))
    with pytest.raises(PlatformError):
        t["retrieval"].get_citation(t["outsider"], UUID(own["matches"][0]["id"]))


def test_document_permission_change_invalidates_old_results_without_switching_citation_target(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    doc = upload(t, kb, "报销上限200元", visibility="inherited")
    asyncio.run(ingest(t))
    grant_search(t, kb, t["bob"])
    result = asyncio.run(t["retrieval"].search(t["bob"], kb["id"], "报销上限", "preview:" + uuid4().hex))
    row = t["knowledge"].documents(t["alice"], kb["id"])[0]
    t["knowledge"].visibility(
        t["alice"], doc["document_id"], DocumentVisibility(expected_revision=row["revision"], visibility="restricted")
    )
    with pytest.raises(PlatformError):
        t["retrieval"].get_citation(t["bob"], UUID(result["matches"][0]["id"]))
    assert asyncio.run(t["retrieval"].search(t["bob"], kb["id"], "报销上限", "preview:" + uuid4().hex))["matches"] == []


def test_document_replacement_is_versioned_and_old_citations_become_unavailable(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    old = upload(t, kb, "出差上限100元")
    asyncio.run(ingest(t))
    citation = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "出差上限", "preview:" + uuid4().hex))[
        "matches"
    ][0]
    row = t["knowledge"].documents(t["alice"], kb["id"])[0]
    new = upload(t, kb, "出差上限300元", document=old["document_id"], revision=row["revision"])
    # While candidate parsing is pending, the old complete index remains the active source.
    assert t["retrieval"].get_citation(t["alice"], UUID(citation["id"]))["text"] == "出差上限100元"
    asyncio.run(ingest(t))
    with pytest.raises(PlatformError):
        t["retrieval"].get_citation(t["alice"], UUID(citation["id"]))
    result = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "出差上限", "preview:" + uuid4().hex))
    assert result["matches"][0]["version_id"] == str(new["version_id"])


def test_delete_revokes_access_first_then_purges_text_vector_citation_and_raw_blob(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    doc = upload(t, kb, "删除专用文档测试内容")
    asyncio.run(ingest(t))
    result = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "删除专用", "preview:" + uuid4().hex))
    row = t["knowledge"].documents(t["alice"], kb["id"])[0]
    with t["db"].transaction(t["alice"]) as c:
        version, _ = current_version(c, t["alice"], doc["version_id"])
    t["knowledge"].delete_document(t["alice"], doc["document_id"], row["revision"])
    with pytest.raises(PlatformError):
        t["retrieval"].get_citation(t["alice"], UUID(result["matches"][0]["id"]))
    assert t["knowledge"].purge(t["org"]) == 1
    assert t["knowledge"].purge(t["org"]) == 0
    with pytest.raises(PlatformError):
        t["blobs"].get(t["org"], version["source_sha256"], version["source_bytes"])
    with t["db"].transaction(t["alice"]) as c:
        assert not c.execute(
            select(s.knowledge_chunks.c.id).where(s.knowledge_chunks.c.version_id == doc["version_id"])
        ).first()
        assert not c.execute(
            select(s.knowledge_citations.c.id).where(s.knowledge_citations.c.version_id == doc["version_id"])
        ).first()


def test_delete_during_parsing_cannot_be_undone_by_the_old_job(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    doc = upload(t, kb, "待删除的摄取内容")
    row = t["knowledge"].documents(t["alice"], kb["id"])[0]
    t["manager"].hook = lambda: t["knowledge"].delete_document(t["alice"], doc["document_id"], row["revision"])
    assert asyncio.run(ingest(t))["state"] == "failed"
    assert t["knowledge"].purge(t["org"]) == 1
    with t["db"].transaction(t["alice"]) as c:
        state = c.execute(
            select(s.knowledge_documents.c.state).where(s.knowledge_documents.c.id == doc["document_id"])
        ).scalar_one()
        assert state == "deleted"


def test_unknown_embedding_response_retains_budget_and_is_never_blindly_retried(knowledge_platform):
    t = knowledge_platform
    kb = base(t, hybrid=True)
    doc = upload(t, kb, "年假申请规则")
    t["embedding_factory"].fail = True
    assert asyncio.run(ingest(t))["state"] != "ready"
    with t["db"].transaction(t["alice"]) as c:
        call = c.execute(select(s.embedding_calls).where(s.embedding_calls.c.org_id == t["org"])).mappings().one()
        assert call["state"] == "unknown"
        budget = (
            c.execute(
                select(s.budgets).where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id)
            )
            .mappings()
            .one()
        )
        assert budget["reserved"] == Decimal("0.020000") and budget["consumed"] == 0
        assert (
            c.execute(select(s.knowledge_jobs.c.state).where(s.knowledge_jobs.c.id == doc["job_id"])).scalar_one()
            == "recovery_required"
        )
    assert asyncio.run(ingest(t)) is None
    assert len(t["embedding_factory"].requests) == 1
    assert t["billing"].reconcile(t["bob"], call["id"], Decimal("0.001"), "synthetic-receipt") == {
        "id": call["id"],
        "recorded": True,
    }
    t["billing"].reconcile(t["bob"], call["id"], Decimal("0.001"), "synthetic-receipt")
    with t["db"].transaction(t["alice"]) as c:
        budget = c.execute(select(s.budgets).where(s.budgets.c.id == call["budget_id"])).mappings().one()
        assert budget["reserved"] == 0 and budget["consumed"] == Decimal("0.001")


def test_hybrid_ingestion_and_worker_retrieval_use_real_pgvector_and_share_run_budget(knowledge_platform):
    t = knowledge_platform
    kb = base(t, hybrid=True)
    upload(t, kb, "年假与休假申请规则：至少提前三天提交。", title="休假规则")
    assert asyncio.run(ingest(t))["state"] == "ready"
    with t["admin"].begin() as c:
        model = provision_model(
            c,
            org_id=t["org"],
            owner_id=t["alice"].user_id,
            provider="fixture",
            model="fixture",
            config={"max_call_charge": "0.020000"},
        )
    agent = t["knowledge"].admin.create_agent(
        t["alice"],
        AgentCreate(
            name="Knowledge Agent",
            version="1",
            instruction="Use authorized evidence and cite actual references",
            model_id=UUID(model["id"]),
            knowledge_ids=(kb["id"],),
            run_budget=Decimal("0.1"),
            max_rounds=3,
        ),
    )
    t["knowledge"].admin.set_grants(
        t["alice"],
        agent["id"],
        GrantCreate(
            subject_type="user",
            subject_id=t["bob"].user_id,
            actions=("agent.read", "agent.use"),
            include_dependencies=True,
        ),
    )
    project = t["service"].create_project(t["bob"], "Private evidence work")
    session = t["service"].create_session(t["bob"], project["id"], agent["id"], "Evidence answer")
    run = t["service"].create_run(
        t["bob"],
        session["id"],
        {
            "message": "annual leave policy",
            "agent_version_id": str(agent["id"]),
            "expected_session_revision": 0,
            "input_artifact_ids": [],
            "mode": "single",
        },
        "knowledge-rag-" + uuid4().hex,
    )

    class Model:
        max_charge = Decimal("0.020000")

        def charge(self, turn):
            return Decimal("0.001000")

        async def stream(self, messages, tools):
            if any(m["role"] == "tool" for m in messages):
                yield ModelTurn(
                    content="依据已检索的休假规则，至少提前三天提交。",
                    finish_reason="stop",
                    input_tokens=10,
                    output_tokens=5,
                )
            else:
                yield ModelTurn(
                    tool_calls=(
                        PlannedCall(
                            id="search", name=tools[0]["function"]["name"], arguments={"query": "annual leave policy"}
                        ),
                    ),
                    finish_reason="tool_calls",
                    input_tokens=10,
                    output_tokens=5,
                )

        async def close(self):
            pass

    class Factory:
        def create(self, definition):
            return Model()

    result = asyncio.run(
        DurableWorker(
            t["store"],
            t["org"],
            "knowledge-rag-worker",
            Factory(),
            ToolDrivers({"knowledge.search": KnowledgeDriver(t["retrieval"])}),
        ).run_once()
    )
    assert result["state"] == "succeeded", result
    result = t["service"].get_run(t["bob"], run["run_id"])["result"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["title"] == "休假规则"
    with t["db"].transaction(t["bob"]) as c:
        query = (
            c.execute(select(s.knowledge_queries).where(s.knowledge_queries.c.run_id == run["run_id"])).mappings().one()
        )
        assert query["query_vector"] is not None
        budget = (
            c.execute(select(s.budgets).where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["bob"].user_id))
            .mappings()
            .one()
        )
        assert budget["consumed"] == Decimal("0.003000") and budget["reserved"] == 0
        # Run query embedding shares the Run allocation; it is not charged again
        # as a standalone call. The organization also includes the author's ingestion.
        pool = (
            c.execute(
                select(s.budget_pools).where(
                    s.budget_pools.c.org_id == t["org"], s.budget_pools.c.department_id.is_(None)
                )
            )
            .mappings()
            .one()
        )
        assert pool["consumed"] == Decimal("0.004000") and pool["reserved"] == 0
        bound = (
            c.execute(
                select(s.budget_allocations).where(
                    s.budget_allocations.c.org_id == t["org"], s.budget_allocations.c.run_id == run["run_id"]
                )
            )
            .mappings()
            .one()
        )
        assert bound["consumed"] == Decimal("0.003000") and bound["embedding_call_id"] is None
    assert t["embedding_factory"].requests[-1] == ["annual leave policy"]


def test_parser_authority_does_not_allow_arbitrary_commands_or_unowned_sources(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    upload(t, kb, "受限解析输入")
    handle = t["jobs"].claim(t["org"], "worker")
    handle = t["jobs"].prepare(handle)
    with pytest.raises(PlatformError):
        t["jobs"].authorize(
            "execute",
            {
                "spec": handle["spec"],
                "dispatch_id": str(handle["dispatch_id"]),
                "language": "python",
                "timeout_seconds": 60,
                "code": "print('unapproved')",
            },
        )
    with pytest.raises(PlatformError):
        t["jobs"].authorize("ensure", {"spec": {**handle["spec"], "org_id": str(t["outsider"].org_id)}})
    with pytest.raises(PlatformError):
        t["knowledge"].documents(t["outsider"], kb["id"])


def test_embedding_vectors_with_missing_usage_publish_but_keep_a_nonzero_budget_hold(knowledge_platform):
    t = knowledge_platform
    kb = base(t, hybrid=True)
    t["embedding_factory"].unknown_usage = True
    upload(t, kb, "休假政策：提前三天申请")
    assert asyncio.run(ingest(t))["state"] == "ready"
    with t["db"].transaction(t["alice"]) as c:
        call = c.execute(select(s.embedding_calls).where(s.embedding_calls.c.org_id == t["org"])).mappings().one()
        budget = c.execute(select(s.budgets).where(s.budgets.c.id == call["budget_id"])).mappings().one()
        assert call["state"] == "succeeded" and call["actual_charge"] is None
        assert budget["reserved"] == call["max_charge"] and budget["consumed"] == 0
    with pytest.raises(PlatformError):
        t["billing"].reconcile(t["alice"], call["id"], Decimal("0.001"), "cannot-self-approve")
    t["billing"].reconcile(t["bob"], call["id"], Decimal("0.001"), "synthetic-confirmed-usage")
    with t["db"].transaction(t["alice"]) as c:
        budget = c.execute(select(s.budgets).where(s.budgets.c.id == call["budget_id"])).mappings().one()
        assert budget["reserved"] == 0 and budget["consumed"] == Decimal("0.001")


def test_embedding_quota_fails_before_network_and_manual_retry_reuses_confirmed_parser_checkpoint(knowledge_platform):
    from fastapi.testclient import TestClient
    from app.api.v2.application import create_platform_app
    from app.auth.service import AuthService, csrf_token

    t = knowledge_platform
    kb = base(t, hybrid=True)
    doc = upload(t, kb, "报销资料")
    with t["admin"].begin() as c:
        c.execute(
            update(s.budgets)
            .where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id)
            .values(hard_limit=Decimal("0.001"))
        )
    assert asyncio.run(ingest(t))["error_code"] == "QUOTA_EXCEEDED"
    assert t["embedding_factory"].requests == []
    parser_calls = list(t["manager"].calls)
    with t["admin"].begin() as c:
        c.execute(
            update(s.budgets)
            .where(s.budgets.c.org_id == t["org"], s.budgets.c.owner_id == t["alice"].user_id)
            .values(hard_limit=Decimal("10"))
        )
    token, _ = AuthService(t["db"], t["settings"]).create_session(
        t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id)
    )
    with TestClient(
        create_platform_app(t["settings"], database=t["db"]), base_url=t["settings"].public_origin
    ) as client:
        client.cookies.set(t["settings"].session_cookie, token)
        response = client.post(
            f"/api/v2/knowledge/jobs/{doc['job_id']}/retry",
            json={"expected_generation": 1},
            headers={"Origin": t["settings"].public_origin, "X-CSRF-Token": csrf_token(token)},
        )
        assert response.status_code == 202, response.text
    assert asyncio.run(ingest(t))["state"] == "ready"
    assert t["manager"].calls == parser_calls
    assert len(t["embedding_factory"].requests) == 1


def test_knowledge_http_upload_requires_auth_csrf_and_owner_binding(knowledge_platform):
    from fastapi.testclient import TestClient
    from app.api.v2.application import create_platform_app
    from app.auth.service import AuthService, csrf_token
    from app.knowledge.contracts import DocumentCreate

    t = knowledge_platform
    kb = base(t)
    slot = t["knowledge"].prepare_upload(
        t["alice"], kb["id"], DocumentCreate(title="HTTP 文档", filename="document.txt", max_bytes=100)
    )
    auth = AuthService(t["db"], t["settings"])
    token, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["alice"].user_id))
    path = f"/api/v2/knowledge/uploads/{slot['version_id']}/content"
    with TestClient(
        create_platform_app(t["settings"], database=t["db"]), base_url=t["settings"].public_origin
    ) as client:
        assert (
            client.put(path, content=b"test", headers={"Content-Type": "application/octet-stream"}).status_code == 401
        )
        client.cookies.set(t["settings"].session_cookie, token)
        assert (
            client.put(path, content=b"test", headers={"Content-Type": "application/octet-stream"}).status_code == 403
        )
        headers = {
            "Content-Type": "application/octet-stream",
            "Origin": t["settings"].public_origin,
            "X-CSRF-Token": csrf_token(token),
        }
        assert client.put(path, content=b"test", headers=headers).status_code == 200
        assert client.put(path, content=b"different", headers=headers).status_code == 409
        other, _ = auth.create_session(t["org"], t["settings"].oidc_issuer, str(t["bob"].user_id))
        client.cookies.set(t["settings"].session_cookie, other)
        headers["X-CSRF-Token"] = csrf_token(other)
        assert client.put(path, content=b"test", headers=headers).status_code in {403, 404}


def test_duplicate_upload_does_not_fail_when_another_attempt_already_queued_the_same_bytes(
    knowledge_platform, monkeypatch
):
    from app.knowledge.contracts import DocumentCreate
    from sqlalchemy import insert

    t = knowledge_platform
    kb = base(t)
    slot = t["knowledge"].prepare_upload(
        t["alice"], kb["id"], DocumentCreate(title="Concurrent upload", filename="data.txt", max_bytes=4)
    )
    put = t["blobs"].put

    def another_attempt_finishes(org, data):
        result = put(org, data)
        with t["admin"].begin() as c:
            c.execute(
                update(s.knowledge_versions)
                .where(s.knowledge_versions.c.id == slot["version_id"])
                .values(upload_state="stored", state="parsing")
            )
            c.execute(
                insert(s.knowledge_jobs).values(
                    org_id=t["org"],
                    id=uuid4(),
                    version_id=slot["version_id"],
                    requested_by=t["alice"].user_id,
                    membership_revision=0,
                )
            )
        return result

    monkeypatch.setattr(t["blobs"], "put", another_attempt_finishes)
    assert t["knowledge"].upload(t["alice"], slot["version_id"], b"same")["state"] == "parsing"
    with t["db"].transaction(t["alice"]) as c:
        assert (
            len(
                c.execute(
                    select(s.knowledge_jobs.c.id).where(s.knowledge_jobs.c.version_id == slot["version_id"])
                ).all()
            )
            == 1
        )


def test_late_heartbeat_failure_cannot_undo_a_committed_knowledge_index(knowledge_platform):
    t = knowledge_platform
    kb = base(t)
    doc = upload(t, kb, "已完成的知识索引")
    assert asyncio.run(ingest(t))["state"] == "ready"
    with t["db"].transaction(t["alice"]) as c:
        handle = dict(
            c.execute(select(s.knowledge_jobs).where(s.knowledge_jobs.c.id == doc["job_id"])).mappings().one()
        )
    t["jobs"].fail(handle, "LATE_HEARTBEAT")
    with t["db"].transaction(t["alice"]) as c:
        assert (
            c.execute(select(s.knowledge_jobs.c.state).where(s.knowledge_jobs.c.id == doc["job_id"])).scalar_one()
            == "ready"
        )
        current_version(c, t["alice"], doc["version_id"])
