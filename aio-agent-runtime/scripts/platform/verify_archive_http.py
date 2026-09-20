"""Synthetic archive bytes exercise real HTTP/quarantine/scanner/PG/reviewer boundaries."""

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time
from uuid import uuid4
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def bundle(package, *, kind="zip", native=False, unsafe=False):
    files = [(f["path"], f["content"].encode("utf-8")) for f in package["files"]]
    if not native:
        files.insert(
            0,
            (
                "skill.json",
                json.dumps({k: v for k, v in package.items() if k != "files"}, ensure_ascii=False).encode("utf-8"),
            ),
        )
    if unsafe:
        files.append(("../outside.txt", b"must never escape the isolated scanner"))
    output = io.BytesIO()
    if kind == "zip":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for path, data in files:
                z.writestr(path, data)
        return output.getvalue()
    with tarfile.open(fileobj=output, mode="w") as tar:
        for path, data in files:
            member = tarfile.TarInfo(path)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return gzip.compress(output.getvalue(), mtime=0)


def verify_archives(admin, reviewer, employee, check):
    config = admin.get("/api/v2/admin/skill-imports/config")
    check("archive_operator_scanner_configured", config.status_code == 200 and config.json()["available"])
    package = {
        "schema_version": 1,
        "name": "archive-http-check",
        "version": "1.0.0",
        "description": "Synthetic archive verification",
        "source": "internal synthetic fixture",
        "license": "MIT",
        "instruction_path": "SKILL.md",
        "reference_paths": [],
        "entrypoints": [
            {
                "name": "double",
                "path": "double.py",
                "description": "Synthetic doubled value",
                "input_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                "tests": [{"input": {"value": 21}, "expected": {"value": 42}}],
                "timeout_seconds": 10,
            }
        ],
        "files": [
            {"path": "SKILL.md", "content": "# Synthetic archive\nUse only authorized capabilities."},
            {"path": "double.py", "content": "def run(payload):\n    return {'value': payload['value'] * 2}\n"},
        ],
    }
    ids, skills = [], []

    def imported(value, label, *, profile="standard", native=False, kind="zip", unsafe=False):
        raw = bundle(value, native=native, kind=kind, unsafe=unsafe)
        request = {
            "request_id": str(uuid4()),
            "archive_format": kind,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sandbox_profile": profile,
            "native": {k: value[k] for k in ("name", "version", "description", "source", "license")}
            if native
            else None,
        }
        created = admin.post("/api/v2/admin/skill-imports", json=request)
        check("archive_intention_" + label, created.status_code == 201)
        id = created.json()["id"]
        ids.append(id)
        retry = admin.post("/api/v2/admin/skill-imports", json=request)
        check("archive_idempotent_intention_" + label, retry.status_code == 201 and retry.json()["id"] == id)
        path = "/api/v2/admin/skill-imports/" + id
        check("archive_other_admin_cannot_read_" + label, reviewer.get(path).status_code == 404)
        check(
            "archive_nonadmin_cannot_import_" + label,
            employee.post("/api/v2/admin/skill-imports", json=request).status_code == 403,
        )
        uploaded = admin.put(path + "/content", content=raw, headers={"Content-Type": "application/octet-stream"})
        check("archive_opaque_upload_" + label, uploaded.status_code == 200)
        end = time.monotonic() + 90
        while True:
            current = admin.get(path).json()
            if current["state"] in {"imported", "rejected", "cancelled"}:
                break
            if time.monotonic() > end:
                raise RuntimeError("Archive import did not reach a terminal state")
            time.sleep(0.25)
        check(
            "archive_terminal_clean_" + label,
            current["cleanup_state"] == "confirmed" and current["manager_acknowledged"],
        )
        check("archive_current_owner_raw_download_" + label, admin.get(path + "/download").content == raw)
        check("archive_other_admin_raw_denied_" + label, reviewer.get(path + "/download").status_code == 404)
        if unsafe:
            check("archive_unsafe_no_skill", current["state"] == "rejected" and current["skill_id"] is None)
        else:
            check(
                "archive_private_draft_" + label,
                current["state"] == "imported" and not current["automatically_published"],
            )
            skill = admin.get("/api/v2/admin/skills/" + current["skill_id"]).json()
            check("archive_not_auto_published_" + label, skill["state"] == "draft" and not skill["published_tools"])
            check(
                "archive_employee_catalog_hidden_" + label,
                current["skill_id"] not in [s["id"] for s in employee.get("/api/v2/skills").json()["items"]],
            )
            skills.append(current["skill_id"])
        return current, path

    current, path = imported(package, "manifest")
    skill_path = "/api/v2/admin/skills/" + current["skill_id"]
    draft = admin.get(skill_path).json()
    reviewer_id = reviewer.get("/api/v2/me").json()["user_id"]
    submitted = admin.post(
        skill_path + "/validate", json={"expected_revision": draft["revision"], "reviewer_id": reviewer_id}
    )
    check("archive_existing_isolated_validation_queued", submitted.status_code == 202)
    until = time.monotonic() + 90
    while True:
        draft = admin.get(skill_path).json()
        if draft["state"] != "validating":
            break
        if time.monotonic() > until:
            raise RuntimeError("Imported Skill validation did not finish")
        time.sleep(0.25)
    check("archive_declared_entrypoint_really_validated", draft["state"] == "validated")
    denied = admin.post(
        skill_path + "/review",
        json={"expected_revision": draft["revision"], "decision": "approve", "note": "self review denied"},
    )
    check("archive_author_cannot_self_publish", denied.status_code in {403, 404})
    decision = reviewer.post(
        skill_path + "/review",
        json={
            "expected_revision": draft["revision"],
            "decision": "approve",
            "note": "Synthetic source, license and doubled-value behavior reviewed",
        },
    )
    check(
        "archive_distinct_reviewer_published", decision.status_code == 200 and decision.json()["state"] == "published"
    )
    deleted = admin.post(path + "/delete", json={"expected_revision": current["revision"]})
    check("archive_raw_purge_confirmed", deleted.status_code == 200 and deleted.json()["archive_purged"])
    check("archive_purged_raw_is_unavailable", admin.get(path + "/download").status_code == 404)
    check("archive_purging_does_not_delete_skill", admin.get(skill_path).json()["state"] == "published")
    native = {**package, "name": "archive-native-http-check", "entrypoints": []}
    native_result, _ = imported(native, "native", native=True, kind="tar.gz")
    check(
        "archive_native_no_automatic_entrypoints",
        not admin.get("/api/v2/admin/skills/" + native_result["skill_id"]).json()["package"]["entrypoints"],
    )
    dependency = json.loads((ROOT / "config/skill-packages/example-analytics.json").read_text(encoding="utf-8"))
    dependency["name"] = "archive-dependency-http-check"
    options = admin.get("/api/v2/admin/options").json()
    environment = next(p for p in options["sandbox_profiles"] if p.get("runtime"))
    dep_result, _ = imported(dependency, "dependencies", profile=environment["id"])
    dep = admin.get("/api/v2/admin/skills/" + dep_result["skill_id"]).json()
    check(
        "archive_v2_exact_environment_preserved",
        dep["package"]["schema_version"] == 2
        and dep["runtime_manifest_digest"] == dependency["runtime_manifest_digest"],
    )
    imported({**package, "name": "archive-unsafe-http-check"}, "unsafe", unsafe=True)
    return {"import_ids": ids, "skill_ids": skills}
