"""All Skill endpoints use the platform's current authentication and CSRF boundary."""

import asyncio
from uuid import UUID

from fastapi import Depends, Query

from .contracts import SkillCreate, SkillValidate, SkillReview


def register_skill_routes(app, service, principal):
    @app.get("/api/v2/skills")
    async def list_skills(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.list_authorized, identity)}

    @app.get("/api/v2/skills/{skill_id}/file")
    async def read_file(skill_id: UUID, path: str = Query(min_length=1, max_length=256), identity=Depends(principal)):
        return await asyncio.to_thread(service.read_file, identity, skill_id, path)

    @app.get("/api/v2/admin/skills")
    async def list_drafts(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(service.management_list, identity)}

    @app.post("/api/v2/admin/skills", status_code=201)
    async def create_skill(body: SkillCreate, identity=Depends(principal)):
        return await asyncio.to_thread(service.create, identity, body)

    @app.get("/api/v2/admin/skills/{skill_id}")
    async def detail(skill_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(service.detail, identity, skill_id)

    @app.post("/api/v2/admin/skills/{skill_id}/validate", status_code=202)
    async def validate(skill_id: UUID, body: SkillValidate, identity=Depends(principal)):
        return await asyncio.to_thread(service.submit, identity, skill_id, body)

    @app.post("/api/v2/admin/skills/{skill_id}/review")
    async def review(skill_id: UUID, body: SkillReview, identity=Depends(principal)):
        return await asyncio.to_thread(service.review, identity, skill_id, body)
