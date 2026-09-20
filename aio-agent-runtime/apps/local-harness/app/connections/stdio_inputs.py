"""Explicit Run attachment copies for stdio; no workspace enumeration or document parsing."""

import base64
from uuid import UUID

from sqlalchemy import select

from ..db import schema as s
from ..platform_errors import PlatformError
from ..workspaces.service import ArtifactService

MAX_STDIO_INPUT_BYTES = 4 * 1024 * 1024
MAX_STDIO_INPUT_FILES = 32


class StdioInputStore:
    def __init__(self, authority):
        self.authority = authority

    @staticmethod
    def manifest(c, p, kind, target, template):
        if template.get("input_policy", "none") != "run_attachments":
            return None
        if kind != "run":
            return []
        run = c.execute(select(s.runs).where(s.runs.c.org_id == p.org_id, s.runs.c.id == target)).mappings().one()
        if run["input"].get("allow_stdio_attachments", False) is not True:
            return []
        records = []
        for raw in run["input"].get("input_artifact_ids", []):
            item = ArtifactService.require_artifact(c, p, UUID(raw))
            if item["project_id"] != run["project_id"]:
                raise PlatformError(
                    "STDIO_INPUT_SCOPE_DENIED", "Only this Run's selected project attachments are allowed", 403
                )
            records.append(
                {
                    "artifact_id": str(item["id"]),
                    "source_path": item["path"],
                    "path": "attachments/" + str(item["id"]),
                    "sha256": item["sha256"],
                    "bytes": item["bytes"],
                }
            )
        if (
            len(records) > MAX_STDIO_INPUT_FILES
            or len({item["artifact_id"] for item in records}) != len(records)
            or sum(item["bytes"] for item in records) > MAX_STDIO_INPUT_BYTES
        ):
            raise PlatformError(
                "STDIO_INPUT_QUOTA_EXCEEDED", "Stdio accepts at most 32 selected files totaling 4 MiB", 413
            )
        return sorted(records, key=lambda item: item["artifact_id"])

    def load(self, payload):
        context, spec = payload.get("context"), payload.get("spec")
        if (
            set(payload) != {"context", "spec"}
            or not isinstance(context, dict)
            or set(context) != {"operation", "payload"}
            or context["operation"] != "call"
            or not isinstance(context["payload"], dict)
            or not isinstance(spec, dict)
            or spec.get("schema_version") != 2
        ):
            self.authority.deny("STDIO_INPUT_SCOPE_DENIED")

        def inspect():
            with self.authority.scope("call", context["payload"]) as (c, p, binding, kind, target, generation, _):
                row = self.authority.row(c, spec, lock=True)
                if (
                    row["state"] != "preparing"
                    or row["run_id"] != target
                    or row["generation"] != generation
                    or row["credential_ref"] != binding["id"]
                ):
                    self.authority.deny("STDIO_INPUT_SCOPE_DENIED")
                self.authority.live(c, row)
                profile = self.authority.service.profile(binding["endpoint_id"], binding["endpoint_digest"])
                manifest = self.manifest(c, p, kind, target, profile["stdio"])
                if manifest is None or manifest != spec.get("input_manifest"):
                    self.authority.deny("STDIO_INPUT_MANIFEST_MISMATCH")
                return p.org_id, manifest

        org, manifest = inspect()
        artifacts = self.authority.store.workspace.artifacts
        if artifacts is None:
            raise PlatformError(
                "STDIO_INPUT_STORAGE_UNAVAILABLE", "Private immutable attachment storage is required", 503
            )
        # Blob reads/checksums occur outside the DB transaction; no document format is interpreted here.
        files = [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "content_b64": base64.b64encode(artifacts.blobs.get(org, item["sha256"], item["bytes"])).decode(
                    "ascii"
                ),
            }
            for item in manifest
        ]
        if inspect() != (org, manifest):
            self.authority.deny("STDIO_INPUT_MANIFEST_MISMATCH")
        return {"input_files": files}
