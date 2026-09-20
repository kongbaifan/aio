"""Explicitly synthetic Skill fixtures; no source is executed by these fake adapters."""

import json
import os
from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.admin.service import AdminService
from app.db import schema as s
from app.runtime.actions import canonical_digest
from app.runtime.service import PlatformService
from app.skills.contracts import SkillCreate, SkillPackage, SkillValidate, SkillReview
from app.skills.service import SkillService
from app.skills.validation import SkillValidationStore
from app.skills.worker import SkillValidationWorker


def sample_package(*, version="1.0.0", typed=True, references=True):
    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    package = {
        "name": "department-calculation",
        "version": version,
        "description": "Synthetic bounded calculation",
        "source": "internal-test-fixture",
        "license": "Internal test only",
        "instruction_path": "SKILL.md",
        "files": [
            {"path": "SKILL.md", "content": "Use the approved calculation helper. This is guidance, not permission."}
        ],
        "entrypoints": [],
        "reference_paths": [],
    }
    if references:
        package["files"].append(
            {"path": "references/rules.md", "content": "Synthetic reference: double the supplied integer."}
        )
        package["reference_paths"] = ["references/rules.md"]
    if typed:
        package["files"].append(
            {
                "path": "scripts/calculate.py",
                "content": "from pathlib import Path\ndef run(payload):\n    value = payload['value'] * 2\n    Path('skill-output.txt').write_text(str(value))\n    return {'value': value}\n",
            }
        )
        package["entrypoints"] = [
            {
                "name": "department_calculate",
                "path": "scripts/calculate.py",
                "description": "Double a number in the isolated workspace",
                "input_schema": schema,
                "output_schema": schema,
                "tests": [{"input": {"value": 7}, "expected": {"value": 14}}],
                "timeout_seconds": 10,
            }
        ]
    return SkillPackage.model_validate(package)


@pytest.fixture
def skill_registry(tenant):
    t = dict(tenant)
    with t["admin"].begin() as c:
        c.execute(
            update(s.memberships)
            .where(s.memberships.c.user_id.in_([t["alice"].user_id, t["bob"].user_id, t["outsider"].user_id]))
            .values(role="org_admin")
        )
    image = os.environ.get("AIO_TEST_COMPUTE_IMAGE", "sha256:" + "1" * 64)
    settings = replace(
        t["settings"],
        manager_url="http://127.0.0.1:9999",
        manager_token="synthetic-manager-" + "m" * 40,
        sandbox_profiles=({"id": "test", "image_digest": image, "max_timeout_seconds": 120},),
    )
    t.update(
        settings=settings,
        skills=SkillService(t["db"], settings),
        validation=SkillValidationStore(t["db"], settings),
        administration=AdminService(t["db"], settings),
        service=PlatformService(t["db"], settings),
    )
    return t


class SyntheticValidationManager:
    def __init__(self, t, *, stop_fails=False, fail_execution=False):
        self.t, self.stop_fails, self.fail_execution = t, stop_fails, fail_execution
        self.calls = []

    async def call(self, operation, payload):
        self.t["validation"].authorize(operation, payload)
        self.calls.append(operation)
        spec = payload["spec"]
        if operation == "stop":
            if self.stop_fails:
                raise RuntimeError("Synthetic lost stop confirmation")
            return {"binding_id": spec["binding_id"], "state": "destroyed"}
        if operation == "ensure":
            return {
                "binding_id": spec["binding_id"],
                "state": "ready",
                "spec_digest": canonical_digest("aio-cell-spec-v1", spec),
            }
        with self.t["db"].scoped(self.t["org"], self.t["alice"].user_id) as c:
            job = (
                c.execute(select(s.skill_validation_jobs).where(s.skill_validation_jobs.c.id == UUID(spec["run_id"])))
                .mappings()
                .one()
            )
            skill = c.execute(select(s.skill_versions).where(s.skill_versions.c.id == job["skill_id"])).mappings().one()
        command = job["commands"][len(job["results"])]
        p = skill["package"]
        if command["kind"] == "scan":
            value = {
                "schema_version": 1,
                "files": len(p["files"]),
                "python_files": sum(f["path"].endswith(".py") for f in p["files"]),
                "entrypoints": len(p["entrypoints"]),
                "checks": ["bounded-text-package", "python-ast", "entrypoint-signature", "credential-patterns"],
            }
        else:
            e = next(v for v in p["entrypoints"] if v["name"] == command["entrypoint"])
            value = e["tests"][command["case"]]["expected"]
        return {
            "binding_id": spec["binding_id"],
            "dispatch_id": command["dispatch_id"],
            "exit_code": 1 if self.fail_execution else 0,
            "stdout": "AIO_SKILL_RESULT:" + json.dumps(value),
            "stderr": "synthetic-private-error-never-persist",
            "truncated": False,
            "error_code": None,
        }


async def publish_sample(t, *, package=None, manager=None, profile="test"):
    row = t["skills"].create(t["alice"], SkillCreate(package=package or sample_package(), sandbox_profile=profile))
    t["skills"].submit(t["alice"], row["id"], SkillValidate(expected_revision=0, reviewer_id=t["bob"].user_id))
    result = await SkillValidationWorker(
        t["validation"], manager or SyntheticValidationManager(t), t["org"], "skill-test-worker"
    ).run_once()
    assert result["state"] == "passed", result
    row = t["skills"].detail(t["alice"], row["id"])
    return t["skills"].review(
        t["bob"],
        row["id"],
        SkillReview(
            expected_revision=row["revision"],
            decision="approve",
            note="Reviewed synthetic test fixture, not a production approval",
        ),
    )
