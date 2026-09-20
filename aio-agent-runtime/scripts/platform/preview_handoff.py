"""Explicit finite-preview fixture: a synthetic R2 receipt, never a real business write."""

import json
from decimal import Decimal
from uuid import UUID

MARKER = "[FILESYSTEM_HANDOFF_FIXTURE]"


class SyntheticApprovalDriver:
    def __init__(self):
        self.operations = {}

    async def execute(self, permit):
        return self.operations.setdefault(
            permit.operation_key,
            {
                "accepted": permit.arguments["value"],
                "fixture": "synthetic receipt; no external business write",
            },
        )


def seed(admin, principal, model_id, python_tool, department_id, reviewer_id):
    from app.admin.contracts import AgentCreate, GrantCreate
    from app.db.provisioning import provision_tool
    from app.platform_settings import DeploymentMode

    if admin.settings.mode is not DeploymentMode.TEST:
        raise RuntimeError("Synthetic approval fixtures require platform-test mode")
    with admin.transaction(principal, write=True) as c:
        receipt = provision_tool(
            c,
            org_id=principal.org_id,
            owner_id=principal.user_id,
            name="approval_record",
            driver="preview.approval",
            risk="R2",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            config={
                "description": "合成审批回执，不执行真实业务写入。",
                "timeout_seconds": 30,
                "approver_user_ids": [str(reviewer_id)],
                "resource_scope": {"fixture": "no-business-write"},
            },
        )
    agent = admin.create_agent(
        principal,
        AgentCreate(
            name="审批文件协作助手",
            version="1.0",
            instruction=MARKER + " 使用真实文件检查点验证计算、审批和新代次恢复；R2 仅为合成回执。",
            model_id=UUID(str(model_id)),
            tool_ids=(UUID(str(python_tool)), UUID(receipt["id"])),
            run_budget=Decimal("0.10"),
            max_rounds=10,
            team={"max_steps": 2, "max_step_rounds": 4},
        ),
    )
    admin.set_grants(
        principal,
        agent["id"],
        GrantCreate(
            subject_type="department",
            subject_id=department_id,
            actions=("agent.read", "agent.use"),
            include_dependencies=True,
        ),
    )
    return {"agent_id": str(agent["id"])}


def turn(messages):
    if not any(m.get("role") == "system" and str(m.get("content", "")).startswith(MARKER) for m in messages):
        return None
    stage = next(
        (
            m["content"].splitlines()[0]
            for m in messages
            if m.get("role") == "system" and str(m.get("content", "")).startswith("TEAM_STAGE: ")
        ),
        None,
    )
    if stage is None:
        return None
    if stage == "TEAM_STAGE: planning":
        return {
            "content": json.dumps(
                {
                    "schema_version": 1,
                    "steps": [
                        {
                            "title": "生成待审批文件",
                            "task": "在隔离环境生成 handoff.txt，内容为41。",
                            "tools": ["python_compute"],
                        },
                        {
                            "title": "审批后读取文件",
                            "task": "取得合成审批回执后，在新环境读取原文件并生成42。",
                            "tools": ["approval_record", "python_compute"],
                        },
                    ],
                },
                ensure_ascii=False,
            )
        }
    if stage == "TEAM_STAGE: synthesis":
        return {
            "content": "文件检查点验证完成：审批后恢复的是文件，新环境生成了 handoff-result.txt（42）。合成回执未执行真实业务写入。"
        }
    data = next(
        json.loads(m["content"])
        for m in reversed(messages)
        if m.get("role") == "user" and '"current_step":' in m.get("content", "")
    )
    executed = [m.get("name") for m in messages if m.get("role") == "tool"]
    if data["current_step"] == 1:
        if executed:
            return {"content": "已在隔离工作区生成 handoff.txt（41），尚未执行需要审批的步骤。"}
        return {
            "tool": "python_compute",
            "arguments": {"code": "from pathlib import Path; Path('handoff.txt').write_text('41')"},
        }
    if "approval_record" not in executed:
        return {"tool": "approval_record", "arguments": {"value": 42}}
    if "python_compute" not in executed:
        return {
            "tool": "python_compute",
            "arguments": {
                "code": "from pathlib import Path; n=int(Path('handoff.txt').read_text()); assert n==41; Path('handoff-result.txt').write_text(str(n+1))"
            },
        }
    return {"content": "合成审批已确认；新代次已读取检查点中的文件并生成 handoff-result.txt（42）。"}
