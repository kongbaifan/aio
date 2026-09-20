"""Actual isolated document-image parsing with real PG/pgvector publication and source policy."""

import asyncio
import io
import os
import zipfile

import httpx
import pytest
from sqlalchemy import select

from app.db import schema as s
from app.execution.sandbox_client import ManagerClient
from app.knowledge.contracts import DocumentCreate
from app.knowledge.worker import KnowledgeWorker
from knowledge_fixtures import base


def office(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def pdf(active=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 250 Td (Travel policy limit 200.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    if active:
        writer.add_js("app.alert('synthetic active content')")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def real_documents(knowledge_platform, tmp_path):
    image = os.environ.get("AIO_TEST_DOCUMENT_IMAGE")
    if not image:
        pytest.skip("Real document parser requires AIO_TEST_DOCUMENT_IMAGE")
    from aio_sandbox_manager.api import create_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager

    t = knowledge_platform
    journal = Journal((tmp_path / "document-manager").resolve())

    class Guard:
        def validate(self, operation, payload):
            t["jobs"].authorize(operation, payload)

    profile = Profile(
        "documents",
        image,
        memory_bytes=512 * 1024 * 1024,
        artifact_bytes=16 * 1024 * 1024,
        artifact_files=4,
        max_timeout_seconds=60,
    )
    manager = SandboxManager(journal, DockerBackend(journal.installation_id), {"documents": profile}, Guard())
    token = "synthetic-document-manager-" + "m" * 40
    t.update(
        manager_app=create_app(manager, token, manage_lifecycle=False), manager_token=token, manager_instance=manager
    )
    try:
        yield t
    finally:
        manager.close()


async def work(t):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=t["manager_app"])) as http:
        client = ManagerClient("http://127.0.0.1:9008", t["manager_token"], client=http)
        return await KnowledgeWorker(t["jobs"], client, t["embedder"], t["org"], "real-document-worker").run_once()


@pytest.mark.parametrize("kind", ["txt", "md", "csv", "pdf", "docx", "xlsx"])
def test_supported_document_type_is_parsed_in_real_readonly_no_network_cell(real_documents, kind):
    t = real_documents
    kb = base(t)
    if kind == "pdf":
        data = pdf()
    elif kind == "docx":
        data = office(
            {
                "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>出差报销标准200元</w:t></w:r></w:p></w:document>'
            }
        )
    elif kind == "xlsx":
        data = office(
            {
                "xl/workbook.xml": '<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="标准" sheetId="1" r:id="s1"/></sheets></workbook>',
                "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="s1" Target="worksheets/sheet1.xml"/></Relationships>',
                "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>出差标准</t></is></c><c r="B1"><v>200</v></c></row></sheetData></worksheet>',
            }
        )
    else:
        data = "出差标准,200\n".encode()
    slot = t["knowledge"].prepare_upload(
        t["alice"],
        kb["id"],
        DocumentCreate(title="真实解析验证", filename="policy." + kind, max_bytes=len(data), visibility="inherited"),
    )
    t["knowledge"].upload(t["alice"], slot["version_id"], data)
    result = asyncio.run(work(t))
    assert result["state"] == "ready", result
    hits = asyncio.run(t["retrieval"].search(t["alice"], kb["id"], "200", "actual-parser-" + kind))
    assert hits["matches"] and "200" in hits["matches"][0]["text"]
    with t["db"].transaction(t["alice"]) as c:
        job = c.execute(select(s.knowledge_jobs).where(s.knowledge_jobs.c.id == result["id"])).mappings().one()
        assert job["cleanup_state"] == "confirmed" and job["export_acknowledged"]
        assert job["storage_reserved_bytes"] == 0 and job["spec"]["inputs"] == []
        binding = job["binding_id"]
    assert not t["manager_instance"].journal.cell(binding)["export_json"]


@pytest.mark.parametrize("kind", ["xml_entities", "pdf_javascript", "macro"])
def test_active_or_malicious_document_is_not_published_and_parser_data_is_retired(real_documents, kind):
    t = real_documents
    kb = base(t)
    if kind == "pdf_javascript":
        data, ext = pdf(True), "pdf"
    elif kind == "macro":
        data, ext = office({"word/document.xml": "<r/>", "word/vbaProject.bin": "inert"}), "docx"
    else:
        data, ext = (
            office({"word/document.xml": '<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'}),
            "docx",
        )
    slot = t["knowledge"].prepare_upload(
        t["alice"], kb["id"], DocumentCreate(title="不可发布夹具", filename="fixture." + ext, max_bytes=len(data))
    )
    t["knowledge"].upload(t["alice"], slot["version_id"], data)
    result = asyncio.run(work(t))
    assert result["state"] == "failed", result
    with t["db"].transaction(t["alice"]) as c:
        job = c.execute(select(s.knowledge_jobs).where(s.knowledge_jobs.c.id == result["id"])).mappings().one()
        assert job["cleanup_state"] == "confirmed" and job["export_acknowledged"]
        assert not c.execute(
            select(s.knowledge_chunks.c.id).where(s.knowledge_chunks.c.version_id == slot["version_id"])
        ).first()
