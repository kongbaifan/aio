"""Synthetic team responses for the finite HTTP preview, never a production planner."""

import json


def content(messages):
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
    # Stage input is emitted by the actual durable state machine; this fixture supplies
    # deterministic model output only. It does not authorize tools or synthesize credentials.
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        try:
            data = json.loads(message["content"])
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and any(key in data for key in ("approved_aliases", "current_step", "steps")):
            break
    else:
        raise RuntimeError("Synthetic team stage has no bounded platform context")
    if stage == "TEAM_STAGE: planning":
        steps = [
            {
                "title": "处理已授权资料",
                "task": "仅使用已批准的工具完成输入资料处理。",
                "tools": data["approved_aliases"][:1],
            }
        ]
        if data["max_steps"] > 1:
            steps.append({"title": "核对前一步结果", "task": "按服务端保存的结果记录结论，不调用新工具。", "tools": []})
        return json.dumps({"schema_version": 1, "steps": steps}, ensure_ascii=False)
    if stage == "TEAM_STAGE: step":
        if data["current_step"] == 1:
            return None  # The regular fixture emits a tool call and then its evidenced result.
        return "合成核对步骤，沿用先前结果与引用：\n\n" + "\n\n".join(
            f"步骤 {step['ordinal']} [{step['state']}]：{step['result'].get('answer', '')}"
            for step in data["previous_steps"]
        )
    if stage == "TEAM_STAGE: synthesis":
        return "## 多步骤任务合成汇总\n\n" + "\n\n".join(
            f"步骤 {step['ordinal']} [{step['state']}]：{step['result'].get('answer', '')}" for step in data["steps"]
        )
    raise RuntimeError("Unknown synthetic team stage")
