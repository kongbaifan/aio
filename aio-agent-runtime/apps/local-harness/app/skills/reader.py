"""A database-backed package reader, not a global filesystem glob or code executor."""

import asyncio
from uuid import UUID

from ..platform_errors import PlatformError
from .catalog import current_skill, file_text


class SkillReferenceDriver:
    def __init__(self, store):
        self.store = store

    def read(self, permit):
        with self.store.locked(permit.handle) as (c, run, job, now, facts):
            skill = current_skill(
                c,
                permit.handle.principal,
                UUID(permit.config["skill_id"]),
                permit.config["skill_digest"],
                action="skill.read",
            )
            path = permit.arguments.get("path")
            if path not in skill["package"]["reference_paths"]:
                raise PlatformError("SKILL_FILE_NOT_FOUND", "Reference is not declared by this Skill", 404)
            return {
                "skill_id": str(skill["id"]),
                "digest": skill["digest"],
                "path": path,
                "content": file_text(skill, path),
                "untrusted_guidance": True,
            }

    async def execute(self, permit):
        return await asyncio.to_thread(self.read, permit)
