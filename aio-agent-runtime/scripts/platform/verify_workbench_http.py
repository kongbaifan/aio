"""Verify the live workbench preview through real HTTP, including its signed synthetic OIDC flow.

This is not browser visual QA. The target must be the active loopback-only fixture
created by preview_workbench.py, with the same organization ID and finite lifetime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--info", type=Path, default=ROOT / "var/verification/workbench-preview.json")
    args = parser.parse_args()
    info = json.loads(args.info.read_text(encoding="utf-8"))
    origin = info["url"]
    issuer = info["identity_url"]
    org = info["org_id"]
    if (
        info["state"] != "running"
        or info["expires_at_epoch"] <= time.time()
        or not info["verification_id"].startswith("preview-")
        or any(urlsplit(url).hostname != "127.0.0.1" for url in (origin, issuer))
    ):
        raise RuntimeError("Target is not an active, owned loopback verification fixture")
    checks = []
    clients = []
    failed_check = None
    report_path = ROOT / "var/verification/workbench-http.json"
    report = {
        "status": "running",
        "verification_id": info["verification_id"],
        "checks": checks,
        "browser_visual_verified": False,
        "timestamp_epoch": time.time(),
    }

    def write_report():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # A failed newer run must never leave an older success looking like current evidence.
    write_report()

    def check(label, value):
        nonlocal failed_check
        if not value:
            failed_check = label
            raise AssertionError(label)
        checks.append(label)

    def run_stdio_attachment(client, project_id, agent_id, artifact_id, consent, label):
        created = client.post(
            "/api/v2/sessions",
            json={"project_id": project_id, "agent_version_id": agent_id, "title": "stdio 附件授权验收"},
        )
        check("stdio_input_session_" + label, created.status_code == 201)
        accepted = client.post(
            f"/api/v2/sessions/{created.json()['id']}/runs",
            json={
                "message": "stdio-attachment:" + artifact_id,
                "agent_version_id": agent_id,
                "expected_session_revision": 0,
                "mode": "single",
                "input_artifact_ids": [artifact_id],
                "allow_stdio_attachments": consent,
            },
            headers={"Idempotency-Key": "stdio-input-http-" + uuid4().hex},
        )
        check("stdio_input_run_accepted_" + label, accepted.status_code == 202)
        deadline = time.monotonic() + 90
        while True:
            result = client.get("/api/v2/runs/" + accepted.json()["run_id"]).json()
            if result["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Stdio attachment run exceeded its verification window")
            time.sleep(0.25)
        if result["state"] != "succeeded" or result["cleanup_state"] != "clean":
            print(
                "STDIO_INPUT_RUN_DIAGNOSTIC",
                {key: result.get(key) for key in ("id", "state", "error_code", "cleanup_state")},
            )
        check(
            "stdio_input_run_terminal_clean_" + label,
            result["state"] == "succeeded" and result["cleanup_state"] == "clean",
        )
        return result

    def login(subject):
        client = httpx.Client(base_url=origin, timeout=20, trust_env=False, follow_redirects=False)
        clients.append(client)
        public = client.get("/api/public/login").json()
        check("fixture_org_" + subject, public["organization_id"] == org)
        start = client.get("/auth/login", params={"org_id": org})
        check("oidc_redirect_" + subject, start.status_code == 303)
        location = start.headers["location"]
        check("approved_fixture_issuer_" + subject, location.startswith(issuer + "/authorize?"))
        page = client.get(location)
        request_id = re.search(r'name="request_id" value="([^"]+)"', page.text).group(1)
        selected = client.post(issuer + "/choose", data={"request_id": request_id, "subject": subject})
        callback = selected.headers["location"]
        check("fixed_callback_" + subject, callback.startswith(origin + "/auth/callback?"))
        finished = client.get(callback)
        check("signed_login_" + subject, finished.status_code == 303)
        me = client.get("/api/v2/me").json()
        client.headers.update({"Origin": origin, "X-CSRF-Token": me["csrf_token"]})
        return client, me

    def run_team(client, session_id, agent_id, label):
        session_info = client.get("/api/v2/sessions/" + session_id).json()
        check("team_mode_advertised_" + label, "team" in session_info["supported_modes"])
        submission = client.post(
            f"/api/v2/sessions/{session_id}/runs",
            json={
                "message": "通过已批准的能力进行多步骤验证，保留实际输出和引用。",
                "agent_version_id": agent_id,
                "expected_session_revision": session_info["revision"],
                "input_artifact_ids": [],
                "mode": "team",
            },
            headers={"Idempotency-Key": "team-http-" + uuid4().hex},
        )
        check("team_run_accepted_" + label, submission.status_code == 202)
        id = submission.json()["run_id"]
        deadline = time.monotonic() + 90
        while True:
            run = client.get("/api/v2/runs/" + id).json()
            if run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Live team verification did not finish")
            time.sleep(0.25)
        check(
            "team_durable_steps_" + label,
            run["state"] == "succeeded"
            and run["mode"] == "team"
            and run["team"]["stage"] == "completed"
            and [step["state"] for step in run["team"]["steps"]] == ["succeeded", "succeeded"],
        )
        replay = client.get("/api/v2/runs/" + id + "/events")
        check(
            "team_stage_replay_" + label,
            replay.status_code == 200
            and "event: team.plan.committed" in replay.text
            and "event: team.synthesis.started" in replay.text,
        )
        return run

    try:
        alice, alice_me = login("alice")
        bob, bob_me = login("bob")
        admin, admin_me = login("admin")
        reviewer, reviewer_me = login("reviewer")
        index = alice.get("/")
        check("spa_entrypoint_served", index.status_code == 200 and '<div id="root"></div>' in index.text)
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index.text)
        check("hashed_assets_present", len(assets) >= 2)
        for asset in assets:
            check("asset_" + asset, alice.get(asset).status_code == 200)
        check(
            "csp_without_inline_scripts",
            "script-src 'unsafe-inline'" not in index.headers.get("content-security-policy", ""),
        )
        check("alice_not_admin", not alice_me["permissions"]["organization_admin"])
        check("admin_role_verified", admin_me["permissions"]["organization_admin"])
        check("member_api_denied", alice.get("/api/v2/admin/members").status_code == 403)
        check("admin_member_api", len(admin.get("/api/v2/admin/members").json()["items"]) == 4)
        a_agents = alice.get("/api/v2/agents").json()["items"]
        b_agents = bob.get("/api/v2/agents").json()["items"]
        check(
            "department_agent_filter",
            {a["name"] for a in a_agents}
            == {
                "文件分析助手",
                "文字整理助手",
                "MCP 身份资料助手",
                "知识库引用助手",
                "审批文件协作助手",
                "OAuth 身份资料助手",
                "隔离进程资料助手",
                "固定依赖分析助手",
            }
            and {a["name"] for a in b_agents}
            == {"财务资料助手", "MCP 身份资料助手", "OAuth 身份资料助手", "隔离进程资料助手", "固定依赖分析助手"},
        )
        project = alice.get("/api/v2/projects").json()["items"][0]
        agent = next(a for a in a_agents if a["name"] == "文件分析助手")
        created = alice.post(
            "/api/v2/sessions",
            json={"project_id": project["id"], "agent_version_id": agent["id"], "title": "HTTP 端到端验收任务"},
        )
        check("session_created", created.status_code == 201)
        session = created.json()
        request = {
            "message": "生成一份本地验收结果文件。",
            "agent_version_id": agent["id"],
            "expected_session_revision": session["revision"],
            "input_artifact_ids": [],
            "mode": "single",
        }
        key = "http-verification-" + uuid4().hex
        submitted = alice.post(f"/api/v2/sessions/{session['id']}/runs", json=request, headers={"Idempotency-Key": key})
        check("run_accepted", submitted.status_code == 202)
        run_id = submitted.json()["run_id"]
        duplicate = alice.post(f"/api/v2/sessions/{session['id']}/runs", json=request, headers={"Idempotency-Key": key})
        check("idempotent_run_replay", duplicate.status_code == 202 and duplicate.json()["run_id"] == run_id)
        deadline = time.monotonic() + 90
        while True:
            run = alice.get("/api/v2/runs/" + run_id).json()
            if run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Verification run did not finish in time")
            time.sleep(0.25)
        check("real_worker_completed", run["state"] == "succeeded")
        check("real_cell_cleanup_confirmed", run["cleanup_state"] == "clean")
        files = run["result"]["artifacts"]
        file = next(f for f in files if f["path"] == "analysis-result.csv")
        download = alice.get(f"/api/v2/artifacts/{file['artifact_id']}/download")
        check("generated_file_download", download.status_code == 200 and b"example,42" in download.content)
        dependency_agent = next(item for item in a_agents if item["name"] == "固定依赖分析助手")
        dependency_detail = admin.get("/api/v2/admin/skills/" + info["dependency_fixture"]["skill_id"])
        check(
            "dependency_skill_v2_and_real_environment_check",
            dependency_detail.status_code == 200
            and dependency_detail.json()["package"]["schema_version"] == 2
            and dependency_detail.json()["validations"][0]["results"][0]["kind"] == "runtime",
        )
        dependency_project = alice.post("/api/v2/projects", json={"name": "依赖环境独立验收"})
        check("dependency_private_project_created", dependency_project.status_code == 201)
        dependency_session = alice.post(
            "/api/v2/sessions",
            json={
                "project_id": dependency_project.json()["id"],
                "agent_version_id": dependency_agent["id"],
                "title": "固定依赖运行验收",
            },
        )
        check("dependency_session_created", dependency_session.status_code == 201)
        dependency_accepted = alice.post(
            f"/api/v2/sessions/{dependency_session.json()['id']}/runs",
            json={
                "message": "使用已审核依赖计算数值摘要",
                "agent_version_id": dependency_agent["id"],
                "expected_session_revision": 0,
                "input_artifact_ids": [],
                "mode": "single",
            },
            headers={"Idempotency-Key": "dependency-http-" + uuid4().hex},
        )
        check("dependency_run_accepted", dependency_accepted.status_code == 202)
        dependency_run_id = dependency_accepted.json()["run_id"]
        deadline = time.monotonic() + 90
        while True:
            dependency_run = alice.get("/api/v2/runs/" + dependency_run_id).json()
            if dependency_run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Dependency Run did not finish in the verification window")
            time.sleep(0.25)
        check(
            "dependency_real_numpy_pandas_run_and_cleanup",
            dependency_run["state"] == "succeeded" and dependency_run["cleanup_state"] == "clean",
        )
        dependency_artifact = next(
            item for item in dependency_run["result"]["artifacts"] if item["path"] == "analytics-result.csv"
        )
        dependency_bytes = alice.get(f"/api/v2/artifacts/{dependency_artifact['artifact_id']}/download")
        check(
            "dependency_actual_dataframe_artifact",
            dependency_bytes.status_code == 200 and dependency_bytes.content == b"value\n2\n4\n6\n",
        )
        check(
            "dependency_artifact_not_shared_by_profile",
            bob.get(f"/api/v2/artifacts/{dependency_artifact['artifact_id']}/download").status_code == 404,
        )
        check("attachment_not_inline", download.headers.get("content-disposition", "").startswith("attachment;"))
        check("bob_cannot_read_alice_session", bob.get("/api/v2/sessions/" + session["id"]).status_code == 404)
        check(
            "admin_no_implicit_private_session_access",
            admin.get("/api/v2/sessions/" + session["id"]).status_code == 404,
        )
        check(
            "bob_cannot_download_alice_file",
            bob.get(f"/api/v2/artifacts/{file['artifact_id']}/download").status_code == 404,
        )
        events = alice.get("/api/v2/runs/" + run_id + "/events")
        check(
            "durable_sse_replay",
            events.status_code == 200
            and "event: run.completed" in events.text
            and "event: artifact.ready" in events.text,
        )
        file_team = run_team(alice, session["id"], agent["id"], "compute")
        team_file = next(item for item in file_team["result"]["artifacts"] if item["path"] == "analysis-result.csv")
        check(
            "team_real_compute_artifact",
            b"example,42" in alice.get(f"/api/v2/artifacts/{team_file['artifact_id']}/download").content,
        )
        check("team_other_user_cannot_read_steps", bob.get("/api/v2/runs/" + file_team["id"]).status_code == 404)
        handoff_agent = next(a for a in a_agents if a["name"] == "审批文件协作助手")
        handoff_session = alice.post(
            "/api/v2/sessions",
            json={"project_id": project["id"], "agent_version_id": handoff_agent["id"], "title": "工作区交接验收"},
        )
        check("handoff_session_created", handoff_session.status_code == 201)
        handoff_request = alice.post(
            f"/api/v2/sessions/{handoff_session.json()['id']}/runs",
            json={
                "message": "验证计算后审批并恢复同一任务文件。",
                "agent_version_id": handoff_agent["id"],
                "expected_session_revision": 0,
                "input_artifact_ids": [],
                "mode": "team",
            },
            headers={"Idempotency-Key": "handoff-http-" + uuid4().hex},
        )
        check("handoff_run_accepted", handoff_request.status_code == 202)
        handoff_id = handoff_request.json()["run_id"]
        deadline = time.monotonic() + 90
        while True:
            handoff_run = alice.get("/api/v2/runs/" + handoff_id).json()
            snapshot = handoff_run.get("workspace_checkpoint")
            if handoff_run["state"] == "waiting_approval" and snapshot and snapshot["state"] == "ready":
                break
            if (
                handoff_run["state"] in {"failed", "cancelled", "timed_out", "recovery_required"}
                or time.monotonic() > deadline
            ):
                raise RuntimeError("Handoff did not reach a safe persisted approval boundary")
            time.sleep(0.25)
        check(
            "checkpoint_stops_old_compute_before_approval",
            handoff_run["cleanup_state"] == "clean"
            and snapshot["file_count"] > 0
            and snapshot["preserved_state"] == "filesystem_only",
        )
        check(
            "checkpoint_projection_not_internal_payload",
            not any(key in snapshot for key in ("spec", "manifest", "provenance_source_ids")),
        )
        check(
            "reviewer_cannot_read_private_workspace",
            reviewer.get("/api/v2/runs/" + handoff_id).status_code in {403, 404},
        )
        pending = next(
            item for item in reviewer.get("/api/v2/approvals").json()["items"] if item["run_id"] == handoff_id
        )
        decision = reviewer.post(
            "/api/v2/approvals/" + pending["id"] + "/decision",
            json={
                "expected_revision": pending["revision"],
                "action_digest": pending["action_digest"],
                "decision": "approve",
            },
        )
        check("handoff_approved_by_other_identity", decision.status_code == 200)
        while True:
            handoff_run = alice.get("/api/v2/runs/" + handoff_id).json()
            if handoff_run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Approved filesystem handoff did not complete")
            time.sleep(0.25)
        check(
            "handoff_new_generation_completed",
            handoff_run["state"] == "succeeded" and handoff_run["generation"] > snapshot["generation"],
        )
        final_file = next(item for item in handoff_run["result"]["artifacts"] if item["path"] == "handoff-result.txt")
        check(
            "handoff_restored_file_bytes",
            alice.get(f"/api/v2/artifacts/{final_file['artifact_id']}/download").content == b"42",
        )
        events = alice.get("/api/v2/runs/" + handoff_id + "/events")
        check(
            "handoff_durable_replay",
            "event: workspace.checkpointed" in events.text and "event: workspace.resume_ready" in events.text,
        )
        check(
            "operations_metadata_only",
            all("input" not in r and "result" not in r for r in admin.get("/api/v2/admin/runs").json()["items"]),
        )
        check(
            "audit_no_raw_payloads", all("metadata" not in r for r in admin.get("/api/v2/admin/audit").json()["items"])
        )
        check("budget_has_actual_charge", float(alice.get("/api/v2/usage").json()["consumed"]) > 0)
        no_csrf = httpx.Client(base_url=origin, cookies=alice.cookies, timeout=10, trust_env=False)
        try:
            check(
                "csrf_required", no_csrf.post("/api/v2/projects", json={"name": "must-not-create"}).status_code == 403
            )
        finally:
            no_csrf.close()
        # Two users share a tool definition, never the definition publisher's personal token.
        alice_connections = alice.get("/api/v2/connections").json()["items"]
        bob_connections = bob.get("/api/v2/connections").json()["items"]
        admin_connections = admin.get("/api/v2/connections").json()["items"]
        admin_connections = [c for c in admin_connections if c["server_id"] == alice_connections[0]["server_id"]]
        check(
            "personal_mcp_connections_are_private",
            len(alice_connections) == len(bob_connections) == len(admin_connections) == 1
            and alice_connections[0]["owner_id"] == alice_me["user_id"]
            and bob_connections[0]["owner_id"] == bob_me["user_id"],
        )
        check(
            "credential_values_not_returned",
            all("secret" not in c and "token" not in c for c in alice_connections + bob_connections),
        )
        check(
            "admin_cannot_borrow_personal_mcp_identity",
            admin.post(
                f"/api/v2/connections/{alice_connections[0]['id']}/discover", json={"request_id": str(uuid4())}
            ).status_code
            == 404,
        )
        check(
            "bff_cookie_cannot_authorize_private_gateway",
            alice.get(info["connector_url"] + "/v1/mcp/status").status_code == 401,
        )
        mcp_agent = next(a for a in a_agents if a["name"] == "MCP 身份资料助手")
        mcp_runs = []
        for subject, client in (("alice", alice), ("bob", bob)):
            own_project = client.get("/api/v2/projects").json()["items"][0]
            session_response = client.post(
                "/api/v2/sessions",
                json={
                    "project_id": own_project["id"],
                    "agent_version_id": mcp_agent["id"],
                    "title": "MCP 个人身份验证 " + subject,
                },
            )
            check("mcp_session_created_" + subject, session_response.status_code == 201)
            mcp_session = session_response.json()
            submission = client.post(
                f"/api/v2/sessions/{mcp_session['id']}/runs",
                json={
                    "message": "读取我的合成资料",
                    "agent_version_id": mcp_agent["id"],
                    "expected_session_revision": 0,
                    "mode": "single",
                    "input_artifact_ids": [],
                },
                headers={"Idempotency-Key": "mcp-http-" + uuid4().hex},
            )
            check("mcp_run_accepted_" + subject, submission.status_code == 202)
            id = submission.json()["run_id"]
            mcp_runs.append(id)
            deadline = time.monotonic() + 60
            while True:
                mcp_run = client.get("/api/v2/runs/" + id).json()
                if mcp_run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Live MCP run did not finish within its verification window")
                time.sleep(0.25)
            check(
                "isolated_mcp_identity_used_" + subject,
                mcp_run["state"] == "succeeded" and ("**" + subject + "**") in mcp_run["result"]["answer"],
            )
        mcp_team = run_team(bob, mcp_session["id"], mcp_agent["id"], "mcp")
        check(
            "team_preserves_explicit_mcp_identity",
            "**bob**" in mcp_team["result"]["answer"] and "**alice**" not in mcp_team["result"]["answer"],
        )
        revoked = alice.delete("/api/v2/connections/" + alice_connections[0]["id"])
        check(
            "mcp_connection_revocation_is_durable", revoked.status_code == 200 and revoked.json()["state"] == "revoked"
        )
        check(
            "revoked_connection_blocks_derived_run_read",
            alice.get("/api/v2/runs/" + mcp_runs[0]).status_code in {403, 404},
        )
        check("other_identity_remains_usable", bob.get("/api/v2/runs/" + mcp_runs[1]).status_code == 200)
        oauth_runs = []
        oauth_connections = []
        for client, subject, catalog in [(alice, "alice", a_agents), (bob, "bob", b_agents)]:
            oauth_agent = next(a for a in catalog if a["name"] == "OAuth 身份资料助手")
            created = client.post(
                "/api/v2/connections",
                json={"server_id": info["oauth_fixture"]["server_id"], "name": "我的合成 OAuth 身份"},
            )
            check("oauth_connection_created_" + subject, created.status_code == 201)
            connection = created.json()
            start = client.post(
                f"/api/v2/connections/{connection['id']}/oauth",
                json={"expected_revision": 0, "request_id": str(uuid4())},
            )
            check(
                "oauth_intent_bound_" + subject,
                start.status_code == 201 and "access_token" not in start.text and "refresh_token" not in start.text,
            )
            authorize = start.json()["authorization_url"]
            check("oauth_approved_issuer_" + subject, authorize.startswith(issuer + "/oauth/authorize?"))
            page = client.get(authorize)
            ticket = re.search(r'name="request_id" value="([^"]+)"', page.text).group(1)
            consent = client.post(issuer + "/oauth/consent", data={"request_id": ticket, "subject": subject})
            callback = client.get(consent.headers["location"])
            check(
                "oauth_callback_verified_" + subject,
                callback.status_code == 303
                and "oauth=connected" in callback.headers["location"]
                and "code=" not in callback.headers["location"],
            )
            linked = next(c for c in client.get("/api/v2/connections").json()["items"] if c["id"] == connection["id"])
            check(
                "oauth_verified_account_" + subject,
                linked["state"] == "active"
                and linked["authorization"]["subject"] == subject
                and linked["credential_revision"] == 1,
            )
            oauth_connections.append(linked)
            own_project = client.get("/api/v2/projects").json()["items"][0]
            session = client.post(
                "/api/v2/sessions",
                json={
                    "project_id": own_project["id"],
                    "agent_version_id": oauth_agent["id"],
                    "title": "OAuth 身份验收",
                },
            ).json()
            created_run = client.post(
                f"/api/v2/sessions/{session['id']}/runs",
                json={
                    "message": "读取我授权的合成身份资料。",
                    "agent_version_id": oauth_agent["id"],
                    "expected_session_revision": 0,
                    "mode": "single",
                    "input_artifact_ids": [],
                },
                headers={"Idempotency-Key": "oauth-http-" + uuid4().hex},
            )
            check("oauth_run_accepted_" + subject, created_run.status_code == 202)
            id = created_run.json()["run_id"]
            deadline = time.monotonic() + 60
            while True:
                result = client.get("/api/v2/runs/" + id).json()
                if result["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("OAuth worker did not finish")
                time.sleep(0.25)
            check(
                "oauth_worker_uses_own_identity_" + subject,
                result["state"] == "succeeded" and ("**" + subject + "**") in result["result"]["answer"],
            )
            oauth_runs.append(id)
        stats = alice.get(issuer + "/oauth/verification").json()
        check(
            "oauth_refresh_not_identity_replacement",
            stats["refresh_count"] >= 3 and all(c["credential_revision"] == 1 for c in oauth_connections),
        )
        check("oauth_does_not_forward_platform_cookie", stats["gateway_forwarded_platform_cookie"] is False)
        check(
            "oauth_disconnect_immediately_durable",
            alice.delete("/api/v2/connections/" + oauth_connections[0]["id"]).status_code == 200,
        )
        deadline = time.monotonic() + 20
        while True:
            retired = next(
                c for c in alice.get("/api/v2/connections").json()["items"] if c["id"] == oauth_connections[0]["id"]
            )
            if retired["credential_cleanup"] == "confirmed":
                break
            if time.monotonic() > deadline:
                raise RuntimeError("OAuth upstream revocation did not complete")
            time.sleep(0.25)
        check(
            "oauth_remote_revocation_confirmed",
            alice.get(issuer + "/oauth/verification").json()["revocation_count"] >= 2,
        )
        check(
            "oauth_revocation_blocks_old_output", alice.get("/api/v2/runs/" + oauth_runs[0]).status_code in {403, 404}
        )
        check("oauth_other_account_not_revoked", bob.get("/api/v2/runs/" + oauth_runs[1]).status_code == 200)
        from preview_stdio import TOKENS as stdio_tokens
        import hashlib

        stdio_runs, stdio_input_runs, stdio_input_files = [], [], []
        for client, subject, catalog in [(alice, "alice", a_agents), (bob, "bob", b_agents)]:
            selected = next(a for a in catalog if a["name"] == "隔离进程资料助手")
            created = client.post(
                "/api/v2/connections",
                json={"server_id": info["stdio_fixture"]["server_id"], "name": "我的专属 stdio 身份"},
            )
            check("stdio_connection_created_" + subject, created.status_code == 201)
            connection = created.json()
            ticket = client.post(
                f"/api/v2/connections/{connection['id']}/credentials",
                json={"expected_revision": 0, "request_id": str(uuid4())},
            )
            check("stdio_credential_intent_" + subject, ticket.status_code == 201)
            stored = client.put(
                f"/api/v2/connections/{connection['id']}/credentials/{ticket.json()['binding_id']}",
                json={"secret": stdio_tokens[subject]},
            )
            check(
                "stdio_secret_stored_privately_" + subject,
                stored.status_code == 200 and stdio_tokens[subject] not in stored.text,
            )
            found = client.post(f"/api/v2/connections/{connection['id']}/discover", json={"request_id": str(uuid4())})
            if (
                found.status_code != 200
                or found.json().get("state") != "ready"
                or not found.json().get("result", {}).get("remote_session_closed")
            ):
                value = found.json()
                code = value.get("error_code") or value.get("error", {}).get("code")
                print(
                    "STDIO_DISCOVERY_DIAGNOSTIC",
                    {
                        "http_status": found.status_code,
                        "state": value.get("state"),
                        "error_code": code if isinstance(code, str) and re.fullmatch(r"[A-Z_]{1,64}", code) else None,
                        "remote_session_closed": bool((value.get("result") or {}).get("remote_session_closed")),
                    },
                )
            check(
                "stdio_actual_protocol_discovery_" + subject,
                found.status_code == 200
                and found.json()["state"] == "ready"
                and found.json()["result"]["transport"] == "stdio"
                and found.json()["result"]["remote_session_closed"],
            )
            own_project = client.get("/api/v2/projects").json()["items"][0]
            session = client.post(
                "/api/v2/sessions",
                json={
                    "project_id": own_project["id"],
                    "agent_version_id": selected["id"],
                    "title": "stdio 隔离执行验收",
                },
            ).json()
            accepted = client.post(
                f"/api/v2/sessions/{session['id']}/runs",
                json={
                    "message": "读取我的合成进程身份摘要。",
                    "agent_version_id": selected["id"],
                    "expected_session_revision": 0,
                    "mode": "single",
                    "input_artifact_ids": [],
                },
                headers={"Idempotency-Key": "stdio-http-" + uuid4().hex},
            )
            check("stdio_run_accepted_" + subject, accepted.status_code == 202)
            rid = accepted.json()["run_id"]
            deadline = time.monotonic() + 90
            while True:
                result = client.get("/api/v2/runs/" + rid).json()
                if result["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Stdio Run did not finish in the verification window")
                time.sleep(0.25)
            check(
                "stdio_worker_scoped_identity_" + subject,
                result["state"] == "succeeded"
                and hashlib.sha256(stdio_tokens[subject].encode()).hexdigest() in result["result"]["answer"],
            )
            check("stdio_process_cleanup_confirmed_" + subject, result["cleanup_state"] == "clean")
            events = client.get("/api/v2/runs/" + rid + "/events")
            check(
                "stdio_private_events_no_token_" + subject,
                "event: stdio.preparing" in events.text
                and "event: stdio.stopped" in events.text
                and stdio_tokens[subject] not in events.text,
            )
            stdio_runs.append(rid)
            data = ("stdio-private-" + subject + "\nvalue,73\n").encode("utf-8")
            prepared = client.post(
                f"/api/v2/projects/{own_project['id']}/uploads",
                json={"path": "stdio-input-" + subject + ".csv", "max_bytes": len(data)},
            )
            check("stdio_input_upload_intent_" + subject, prepared.status_code == 201)
            uploaded = client.put(
                prepared.json()["content_url"], content=data, headers={"Content-Type": "application/octet-stream"}
            )
            check("stdio_input_immutable_upload_" + subject, uploaded.status_code == 200)
            file = uploaded.json()
            result = run_stdio_attachment(client, own_project["id"], selected["id"], file["id"], True, subject)
            check(
                "stdio_input_bytes_reached_isolated_process_" + subject,
                "stdio-private-" + subject in result["result"]["answer"]
                and file["sha256"] in result["result"]["answer"],
            )
            original = client.get(f"/api/v2/artifacts/{file['id']}/download")
            check("stdio_input_original_unchanged_" + subject, original.status_code == 200 and original.content == data)
            stdio_input_runs.append(result["id"])
            stdio_input_files.append(file)
        check("stdio_other_user_cannot_read_run", bob.get("/api/v2/runs/" + stdio_runs[0]).status_code == 404)
        check(
            "stdio_other_user_cannot_read_input",
            bob.get(f"/api/v2/artifacts/{stdio_input_files[0]['id']}/download").status_code == 404,
        )
        check(
            "stdio_other_user_cannot_read_input_result",
            bob.get("/api/v2/runs/" + stdio_input_runs[0]).status_code == 404,
        )
        without_consent = run_stdio_attachment(
            alice,
            stdio_input_files[0]["project_id"],
            next(agent["id"] for agent in a_agents if agent["name"] == "隔离进程资料助手"),
            stdio_input_files[0]["id"],
            False,
            "without-consent",
        )
        check(
            "stdio_inputs_default_closed_without_run_consent",
            '"available": false' in without_consent["result"]["answer"]
            and "stdio-private-alice" not in without_consent["result"]["answer"],
        )
        knowledge = alice.get("/api/v2/knowledge").json()["items"]
        check(
            "department_knowledge_catalog", len(knowledge) == 1 and bob.get("/api/v2/knowledge").json()["items"] == []
        )
        kb = knowledge[0]
        documents = alice.get(f"/api/v2/knowledge/{kb['id']}/documents").json()["items"]
        check("restricted_document_not_listed", len(documents) == 1 and documents[0]["title"] == "销售报销规定")
        search = alice.post(
            f"/api/v2/knowledge/{kb['id']}/search", json={"query": "餐费报销", "request_id": str(uuid4()), "limit": 5}
        )
        check(
            "authorized_chinese_keyword_preview",
            search.status_code == 200
            and search.json()["retrieval_mode"] == "lexical"
            and len(search.json()["matches"]) == 1,
        )
        citation = search.json()["matches"][0]
        source = alice.get("/api/v2/knowledge/citations/" + citation["id"])
        check(
            "versioned_citation_and_source_location",
            source.status_code == 200
            and "200元" in source.json()["text"]
            and source.json()["location"]["kind"] == "lines",
        )
        check(
            "other_department_cannot_read_citation",
            bob.get("/api/v2/knowledge/citations/" + citation["id"]).status_code == 404,
        )
        original = alice.get(source.json()["download_url"])
        check(
            "knowledge_raw_attachment",
            original.status_code == 200
            and original.headers.get("content-disposition", "").startswith("attachment;")
            and "200元" in original.text,
        )
        knowledge_agent = next(a for a in a_agents if a["name"] == "知识库引用助手")
        knowledge_session_response = alice.post(
            "/api/v2/sessions",
            json={"project_id": project["id"], "agent_version_id": knowledge_agent["id"], "title": "知识库引用验证"},
        )
        check("knowledge_session_created", knowledge_session_response.status_code == 201)
        knowledge_session = knowledge_session_response.json()
        knowledge_run_response = alice.post(
            f"/api/v2/sessions/{knowledge_session['id']}/runs",
            json={
                "message": "餐费报销标准是什么？请给出文档依据。",
                "agent_version_id": knowledge_agent["id"],
                "expected_session_revision": 0,
                "input_artifact_ids": [],
                "mode": "single",
            },
            headers={"Idempotency-Key": "knowledge-http-" + uuid4().hex},
        )
        check("knowledge_run_accepted", knowledge_run_response.status_code == 202)
        knowledge_run_id = knowledge_run_response.json()["run_id"]
        deadline = time.monotonic() + 60
        while True:
            knowledge_run = alice.get("/api/v2/runs/" + knowledge_run_id).json()
            if knowledge_run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Knowledge Run did not complete in time")
            time.sleep(0.25)
        check(
            "durable_hybrid_retrieval_and_citations",
            knowledge_run["state"] == "succeeded"
            and "200元" in knowledge_run["result"]["answer"]
            and len(knowledge_run["result"]["citations"]) == 1,
        )
        knowledge_team = run_team(alice, knowledge_session["id"], knowledge_agent["id"], "knowledge")
        check(
            "team_preserves_knowledge_citation",
            "200元" in knowledge_team["result"]["answer"] and len(knowledge_team["result"]["citations"]) == 1,
        )
        admin_documents = admin.get(f"/api/v2/knowledge/{kb['id']}/documents").json()["items"]
        shared = next(d for d in admin_documents if d["id"] == documents[0]["id"])
        removed = admin.request(
            "DELETE", "/api/v2/knowledge/documents/" + shared["id"], json={"expected_revision": shared["revision"]}
        )
        check("knowledge_deletion_revokes_before_gc", removed.status_code == 200 and removed.json()["access_revoked"])
        check(
            "deleted_document_citation_is_not_repointed",
            alice.get("/api/v2/knowledge/citations/" + citation["id"]).status_code in {403, 404},
        )
        check(
            "deleted_knowledge_blocks_derived_run",
            alice.get("/api/v2/runs/" + knowledge_run_id).status_code in {403, 404},
        )
        check(
            "deleted_knowledge_blocks_team_steps",
            alice.get("/api/v2/runs/" + knowledge_team["id"]).status_code in {403, 404},
        )
        check(
            "deleted_knowledge_blocks_raw_download", alice.get(source.json()["download_url"]).status_code in {403, 404}
        )
        # Real HTTP admission -> separate validation queue -> private manager authority -> real Docker.
        schema = {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        package = {
            "name": "http-verified-skill",
            "version": "1.0.0",
            "description": "Synthetic end-to-end Skill package",
            "source": "owned-loopback-verification",
            "license": "Internal verification only",
            "instruction_path": "SKILL.md",
            "reference_paths": [],
            "files": [
                {"path": "SKILL.md", "content": "Use the approved http_skill_double helper for the supplied integer."},
                {
                    "path": "scripts/double.py",
                    "content": "import json\nfrom pathlib import Path\ndef run(payload):\n    result={'value':payload['value']*2}\n    Path('skill-result.json').write_text(json.dumps(result))\n    return result\n",
                },
            ],
            "entrypoints": [
                {
                    "name": "http_skill_double",
                    "path": "scripts/double.py",
                    "description": "Double a synthetic integer",
                    "input_schema": schema,
                    "output_schema": schema,
                    "tests": [{"input": {"value": 2}, "expected": {"value": 4}}],
                    "timeout_seconds": 10,
                }
            ],
        }
        created_skill = admin.post("/api/v2/admin/skills", json={"package": package, "sandbox_profile": "standard"})
        check("skill_private_draft_created", created_skill.status_code == 201)
        skill = created_skill.json()
        skill_path = "/api/v2/admin/skills/" + skill["id"]
        check("unassigned_reviewer_cannot_read_draft", reviewer.get(skill_path).status_code == 404)
        check(
            "member_cannot_publish_skill",
            alice.post("/api/v2/admin/skills", json={"package": package, "sandbox_profile": "standard"}).status_code
            == 403,
        )
        validation = admin.post(
            skill_path + "/validate",
            json={"expected_revision": skill["revision"], "reviewer_id": reviewer_me["user_id"]},
        )
        check("skill_validation_queued", validation.status_code == 202)
        deadline = time.monotonic() + 60
        while True:
            checked_skill = reviewer.get(skill_path).json()
            if checked_skill["state"] != "validating":
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Skill validation did not complete within its verification window")
            time.sleep(0.25)
        check(
            "real_isolated_skill_scan_and_test",
            checked_skill["state"] == "validated" and len(checked_skill["validations"][0]["results"]) == 2,
        )
        check("validation_cell_cleanup_confirmed", checked_skill["validations"][0]["cleanup_state"] == "confirmed")
        check(
            "skill_author_cannot_self_approve",
            admin.post(
                skill_path + "/review",
                json={
                    "expected_revision": checked_skill["revision"],
                    "decision": "approve",
                    "note": "must be rejected",
                },
            ).status_code
            == 403,
        )
        published = reviewer.post(
            skill_path + "/review",
            json={
                "expected_revision": checked_skill["revision"],
                "decision": "approve",
                "note": "Approved only this synthetic, isolated verification package",
            },
        )
        check(
            "distinct_reviewer_publishes_fixed_version",
            published.status_code == 200 and published.json()["state"] == "published",
        )
        visible_skills = {item["id"] for item in alice.get("/api/v2/skills").json()["items"]}
        check(
            "published_skill_not_implicitly_shared",
            skill["id"] not in visible_skills and info["dependency_fixture"]["skill_id"] in visible_skills,
        )
        model = admin.get("/api/v2/admin/models").json()["items"][0]
        skill_agent_response = admin.post(
            "/api/v2/admin/agents",
            json={
                "name": "HTTP Skill 验收助手",
                "version": "1.0",
                "instruction": "Synthetic Skill verification only",
                "model_id": model["id"],
                "skill_ids": [skill["id"]],
                "run_budget": "0.10",
                "max_rounds": 4,
            },
        )
        check("agent_binds_published_skill", skill_agent_response.status_code == 201)
        skill_agent = skill_agent_response.json()
        sales = next(d for d in admin.get("/api/v2/directory").json()["departments"] if d["name"] == "销售团队")
        grant = admin.put(
            f"/api/v2/resources/{skill_agent['id']}/grants",
            json={
                "subject_type": "department",
                "subject_id": sales["id"],
                "actions": ["agent.use", "agent.read"],
                "include_dependencies": True,
            },
        )
        check("department_skill_dependency_grants", grant.status_code == 200 and grant.json()["granted_resources"] == 4)
        check(
            "sales_can_read_shared_skill",
            alice.get(f"/api/v2/skills/{skill['id']}/file", params={"path": "SKILL.md"}).status_code == 200,
        )
        check(
            "finance_has_no_skill_content_bypass",
            bob.get(f"/api/v2/skills/{skill['id']}/file", params={"path": "SKILL.md"}).status_code == 404,
        )
        skill_session_response = alice.post(
            "/api/v2/sessions",
            json={
                "project_id": project["id"],
                "agent_version_id": skill_agent["id"],
                "title": "固定 Skill 的真实隔离执行",
            },
        )
        check("skill_session_created", skill_session_response.status_code == 201)
        skill_session = skill_session_response.json()
        skill_run_response = alice.post(
            f"/api/v2/sessions/{skill_session['id']}/runs",
            json={
                "agent_version_id": skill_agent["id"],
                "expected_session_revision": skill_session["revision"],
                "message": "Run the synthetic Skill",
                "mode": "single",
                "input_artifact_ids": [],
            },
            headers={"Idempotency-Key": "http-skill-run-" + uuid4().hex},
        )
        check("skill_run_accepted", skill_run_response.status_code == 202)
        skill_run_id = skill_run_response.json()["run_id"]
        deadline = time.monotonic() + 60
        while True:
            skill_run = alice.get("/api/v2/runs/" + skill_run_id).json()
            if skill_run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Skill execution did not complete within its verification window")
            time.sleep(0.25)
        check(
            "real_published_skill_execution",
            skill_run["state"] == "succeeded" and skill_run["cleanup_state"] == "clean",
        )
        skill_file = next(f for f in skill_run["result"]["artifacts"] if f["path"] == "skill-result.json")
        skill_download = alice.get(f"/api/v2/artifacts/{skill_file['artifact_id']}/download")
        check(
            "typed_skill_output_downloaded",
            skill_download.status_code == 200 and skill_download.json() == {"value": 42},
        )
        live_skill = admin.get(skill_path).json()
        disabled = admin.patch(
            f"/api/v2/resources/{skill['id']}/status",
            json={"expected_revision": live_skill["resource_revision"], "status": "disabled"},
        )
        check("skill_emergency_disable", disabled.status_code == 200)
        check(
            "disabled_skill_blocks_derived_run_replay",
            alice.get("/api/v2/runs/" + skill_run_id).status_code in {403, 404},
        )
        check(
            "disabled_skill_blocks_derived_download",
            alice.get(f"/api/v2/artifacts/{skill_file['artifact_id']}/download").status_code in {403, 404},
        )
        from verify_archive_http import verify_archives

        archive_results = verify_archives(admin, reviewer, bob, check)
        from verify_budget_http import verify_shared_budgets

        budget_result = verify_shared_budgets(admin, alice, bob, check)
        check(
            "logout_revokes_browser_session",
            alice.post("/auth/logout").status_code == 200 and alice.get("/api/v2/me").status_code == 401,
        )
        report = {
            "status": "passed",
            "verification_id": info["verification_id"],
            "checks": checks,
            "run_id": run_id,
            "skill_run_id": skill_run_id,
            "skill_id": skill["id"],
            "mcp_run_ids": mcp_runs,
            "knowledge_run_id": knowledge_run_id,
            "team_run_ids": [file_team["id"], mcp_team["id"], knowledge_team["id"]],
            "handoff_run_id": handoff_id,
            "oauth_run_ids": oauth_runs,
            "stdio_run_ids": stdio_runs,
            "stdio_input_run_ids": stdio_input_runs,
            "stdio_no_input_consent_run_id": without_consent["id"],
            "dependency_run_id": dependency_run_id,
            "skill_archive_imports": archive_results,
            "shared_budgets": budget_result,
            "model": "synthetic loopback fixture",
            "identity_provider": "synthetic signed OIDC with PKCE",
            "real_components": [
                "HTTP",
                "PostgreSQL",
                "API authorization",
                "Worker",
                "Docker Python",
                "artifact storage",
            ],
            "browser_visual_verified": False,
            "timestamp_epoch": time.time(),
        }
        write_report()
        print(f"{len(checks)} live HTTP assertions passed; real Docker output and cross-user privacy verified.")
        print("Visual browser inspection is separate and not claimed by this script.")
    except Exception as error:
        report.update(
            status="failed", failure_type=type(error).__name__, failed_check=failed_check, timestamp_epoch=time.time()
        )
        write_report()
        raise
    finally:
        for client in clients:
            client.close()


if __name__ == "__main__":
    main()
