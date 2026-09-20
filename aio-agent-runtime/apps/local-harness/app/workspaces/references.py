"""Blob reachability shared by knowledge and internal workspace checkpoint GC.

Caller holds the organization storage lock, also taken before writers bind blobs.
This is not an authorization API and never treats a hash as a grant.
"""

from sqlalchemy import select
from ..db import schema as s


def blob_referenced(c, org, sha, *, excluding_knowledge=None, excluding_checkpoint=None, excluding_import=None):
    knowledge = select(s.knowledge_versions.c.id).where(
        s.knowledge_versions.c.org_id == org,
        s.knowledge_versions.c.source_sha256 == sha,
        s.knowledge_versions.c.purged_at.is_(None),
    )
    if excluding_knowledge is not None:
        knowledge = knowledge.where(s.knowledge_versions.c.id != excluding_knowledge)
    checkpoints = select(s.workspace_checkpoints.c.id).where(
        s.workspace_checkpoints.c.org_id == org,
        s.workspace_checkpoints.c.state != "purged",
        s.workspace_checkpoints.c.manifest.contains([{"sha256": sha}]),
    )
    if excluding_checkpoint is not None:
        checkpoints = checkpoints.where(s.workspace_checkpoints.c.id != excluding_checkpoint)
    imports = select(s.skill_imports.c.id).where(
        s.skill_imports.c.org_id == org,
        s.skill_imports.c.archive_sha256 == sha,
        s.skill_imports.c.archive_purged.is_(False),
        s.skill_imports.c.upload_bound.is_(True),
    )
    if excluding_import is not None:
        imports = imports.where(s.skill_imports.c.id != excluding_import)
    queries = [
        imports,
        knowledge,
        checkpoints,
        select(s.artifacts.c.id).where(s.artifacts.c.org_id == org, s.artifacts.c.sha256 == sha),
        select(s.workspace_versions.c.id).where(
            s.workspace_versions.c.org_id == org, s.workspace_versions.c.manifest.contains([{"sha256": sha}])
        ),
        select(s.upload_slots.c.id).where(s.upload_slots.c.org_id == org, s.upload_slots.c.content_sha256 == sha),
        select(s.workspace_leases.c.project_id).where(
            s.workspace_leases.c.org_id == org, s.workspace_leases.c.export_manifest.contains([{"sha256": sha}])
        ),
    ]
    return any(c.execute(query.limit(1)).first() is not None for query in queries)
