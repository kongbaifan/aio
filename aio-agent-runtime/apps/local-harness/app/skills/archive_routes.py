"""Owner-only Skill archive routes inside the BFF auth/CSRF boundary."""

import asyncio
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import Response

from .archive_contracts import SkillArchivePrepare, SkillArchiveRevision


def register_archive_routes(app, service, principal):
    @app.get("/api/v2/admin/skill-imports/config")
    async def archive_configuration(identity=Depends(principal)):
        return await asyncio.to_thread(service.configuration, identity)

    @app.get("/api/v2/admin/skill-imports")
    async def list_archive_imports(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list, identity)}

    @app.post("/api/v2/admin/skill-imports", status_code=201)
    async def prepare_archive_import(body: SkillArchivePrepare, identity=Depends(principal)):
        return await asyncio.to_thread(service.prepare, identity, body)

    @app.get("/api/v2/admin/skill-imports/{import_id}")
    async def archive_import_detail(import_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(service.detail, identity, import_id)

    @app.put("/api/v2/admin/skill-imports/{import_id}/content")
    async def upload_archive(import_id: UUID, request: Request, identity=Depends(principal)):
        return await asyncio.to_thread(service.upload, identity, import_id, await request.body())

    @app.get("/api/v2/admin/skill-imports/{import_id}/download")
    async def download_archive(import_id: UUID, identity=Depends(principal)):
        metadata, data = await asyncio.to_thread(service.download, identity, import_id)
        name = "skill-archive." + metadata["archive_format"]
        return Response(
            data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/api/v2/admin/skill-imports/{import_id}/delete")
    async def delete_archive(import_id: UUID, body: SkillArchiveRevision, identity=Depends(principal)):
        result = await asyncio.to_thread(service.delete, identity, import_id, body.expected_revision)
        await asyncio.to_thread(service.gc, identity.org_id)
        return await asyncio.to_thread(service.detail, identity, import_id) if not result["archive_purged"] else result
