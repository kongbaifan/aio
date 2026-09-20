"""Live synthetic-identity HTTP checks for real shared budget admission and settlement."""

from decimal import Decimal
import time
from uuid import uuid4


def verify_shared_budgets(admin, employee, other_employee, check):
    endpoint = "/api/v2/admin/shared-budgets"

    def pools():
        response = admin.get(endpoint)
        if response.status_code != 200:
            raise RuntimeError("Shared budget summary unavailable in the owned fixture")
        return {row["department_id"]: row for row in response.json()["items"]}

    def set_limit(row, amount):
        path = "/organization" if row["scope"] == "organization" else "/departments/" + row["department_id"]
        return admin.put(
            endpoint + path,
            json={"expected_revision": row["revision"], "hard_limit": str(amount) if amount is not None else None},
        )

    before = pools()
    check("shared_budget_organization_and_departments_listed", None in before and len(before) >= 3)
    check("shared_budget_member_financial_summary_denied", employee.get(endpoint).status_code == 403)
    check("shared_budget_other_member_financial_summary_denied", other_employee.get(endpoint).status_code == 403)
    department = employee.get("/api/v2/me").json()["departments"][0]["id"]
    other_department = other_employee.get("/api/v2/me").json()["departments"][0]["id"]
    agents = employee.get("/api/v2/agents").json()["items"]
    agent = next(item for item in agents if item["name"] == "文字整理助手")
    project = employee.post("/api/v2/projects", json={"name": "共享预算实际准入验证"})
    check("shared_budget_private_project_created", project.status_code == 201)
    session = employee.post(
        "/api/v2/sessions",
        json={"project_id": project.json()["id"], "agent_version_id": agent["id"], "title": "共享预算受控任务"},
    )
    check("shared_budget_private_session_created", session.status_code == 201)
    path = "/api/v2/sessions/" + session.json()["id"] + "/runs"
    body = {
        "agent_version_id": agent["id"],
        "expected_session_revision": session.json()["revision"],
        "message": "Synthetic shared budget verification",
        "mode": "single",
        "input_artifact_ids": [],
    }
    key = {"Idempotency-Key": "shared-budget-http-" + uuid4().hex}
    def committed(row):
        return Decimal(row["consumed"]) + Decimal(row["reserved"])

    # Pool amounts are decimal strings whose scale differs before and after a pool row exists
    # ("0" for a not-yet-created pool, "0.000000" once stored), so compare the actual amounts.
    def amount(row, field):
        return Decimal(row[field])

    check(
        "shared_budget_org_cap_set_without_reset", set_limit(before[None], committed(before[None])).status_code == 200
    )
    denied = employee.post(path, json=body, headers=key)
    check(
        "shared_budget_org_blocks_paid_run",
        denied.status_code == 429 and denied.json()["error"]["code"] == "SHARED_BUDGET_EXCEEDED",
    )
    check(
        "shared_budget_denial_preserves_session_revision",
        employee.get(path.removesuffix("/runs")).json()["revision"] == session.json()["revision"],
    )
    check(
        "shared_budget_org_limit_increased",
        set_limit(pools()[None], committed(before[None]) + Decimal("1")).status_code == 200,
    )
    check(
        "shared_budget_department_cap_set",
        set_limit(pools()[department], committed(before[department])).status_code == 200,
    )
    denied = employee.post(path, json=body, headers=key)
    check(
        "shared_budget_department_blocks_paid_run",
        denied.status_code == 429 and denied.json()["error"]["code"] == "SHARED_BUDGET_EXCEEDED",
    )
    check(
        "shared_budget_department_capacity_added",
        set_limit(pools()[department], committed(before[department]) + Decimal("0.1")).status_code == 200,
    )
    own_before = employee.get("/api/v2/usage").json()
    accepted = employee.post(path, json=body, headers=key)
    check("shared_budget_approved_admission", accepted.status_code == 202)
    run_id = accepted.json()["run_id"]
    deadline = time.monotonic() + 45
    while True:
        run = employee.get("/api/v2/runs/" + run_id).json()
        if run["state"] in {"succeeded", "failed", "cancelled", "timed_out", "recovery_required"}:
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Shared budget synthetic Run exceeded its fixed verification deadline")
        time.sleep(0.2)
    check("shared_budget_worker_run_succeeded", run["state"] == "succeeded" and run["cleanup_state"] == "clean")
    after = pools()
    charge = Decimal(employee.get("/api/v2/usage").json()["consumed"]) - Decimal(own_before["consumed"])
    check(
        "shared_budget_real_charge_projected_to_org",
        charge > 0 and Decimal(after[None]["consumed"]) - Decimal(before[None]["consumed"]) == charge,
    )
    check(
        "shared_budget_same_charge_projected_to_department",
        Decimal(after[department]["consumed"]) - Decimal(before[department]["consumed"]) == charge,
    )
    check(
        "shared_budget_unrelated_department_unchanged",
        amount(after[other_department], "consumed") == amount(before[other_department], "consumed")
        and amount(after[other_department], "reserved") == amount(before[other_department], "reserved"),
    )
    check(
        "shared_budget_run_reservation_released",
        amount(after[None], "reserved") == amount(before[None], "reserved")
        and amount(after[department], "reserved") == amount(before[department], "reserved"),
    )
    replay = employee.post(path, json=body, headers=key)
    check("shared_budget_stable_idempotent_run", replay.status_code == 202 and replay.json()["run_id"] == run_id)
    check("shared_budget_no_repeated_charge", amount(pools()[None], "consumed") == amount(after[None], "consumed"))
    check("shared_budget_cannot_erase_consumption", set_limit(after[None], Decimal(0)).status_code == 409)
    check("shared_budget_stale_revision_rejected", set_limit(before[None], Decimal("10")).status_code == 409)
    for target, label in ((None, "organization"), (department, "department")):
        check("shared_budget_remove_cap_" + label, set_limit(after[target], None).status_code == 200)
    retained = pools()
    check(
        "shared_budget_removal_preserves_financial_facts",
        all(
            retained[target]["hard_limit"] is None
            and amount(retained[target], "consumed") == amount(after[target], "consumed")
            and amount(retained[target], "reserved") == amount(after[target], "reserved")
            for target in (None, department)
        ),
    )
    return {"run_id": run_id, "department_id": department, "charge": str(charge), "currency": "USD"}
