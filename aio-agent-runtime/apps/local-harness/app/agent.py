import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from .audit import AuditLogger
from .llm.base import AssistantTurn, ModelClient, TextDelta
from .models import AgentEvent
from .sessions import SessionStore
from .skills.registry import SkillRegistry
from .tools.registry import ToolRegistry


# 工具结果写入事件流时的截断上限，避免超长输出撑爆前端和审计日志。
TOOL_DETAIL_LIMIT = 2000


@dataclass
class StreamStart:
    """流式执行的首个信号：会话已就绪、Skill 已匹配，可先渲染。"""

    session_id: str
    matched: list[str] = field(default_factory=list)


@dataclass
class AnswerDelta:
    """最终答案的文本增量（打字机效果，仅新增片段，非累计）。"""

    text: str = ""


BASE_SYSTEM_PROMPT = """你是一个本地 AI 工作助手。
你可以通过工具读取和修改 workspace 内文件、执行 Python、检查代码和查看运行时状态。
所有文件路径都必须是 workspace 相对路径；不要猜测工具结果，不要访问 workspace 之外的路径。
需要写文件或执行代码时，先选择最小必要操作；工具失败时解释原因并停止继续破坏性操作。
最终回答要用中文，简洁说明做了什么、结果是什么、生成了哪些文件以及仍存在的风险。
"""


class AgentRunner:
    """实现单 Agent 的确定性工具调用循环。"""

    def __init__(
        self,
        tools: ToolRegistry,
        skills: SkillRegistry,
        sessions: SessionStore,
        audit: AuditLogger,
        max_rounds: int = 8,
        require_confirmation: bool = False,
    ):
        self.tools = tools
        self.skills = skills
        self.sessions = sessions
        self.audit = audit
        self.max_rounds = max_rounds
        self.require_confirmation = require_confirmation

    async def run_stream(
        self,
        message: str,
        model: ModelClient,
        session_id: str | None = None,
        *,
        provider: str = "",
        model_id: str = "",
    ) -> AsyncIterator[StreamStart | AgentEvent]:
        """流式执行工具调用循环。

        先 yield 一个 StreamStart（会话与匹配到的 Skill），随后每产生一个
        AgentEvent（工具开始、工具结果、最终答案、错误）就立即 yield，供上层
        边执行边推送给前端。最终答案事件的 type 为 "result"、name 为 "answer"；
        超限或模型失败会 yield type="error" 的事件后结束。
        """
        session = await self.sessions.get_or_create(
            session_id,
            message,
            provider=provider,
            model=model_id,
        )
        matches = self.skills.match(message)
        matched_names = [item.name for item in matches]
        await self.sessions.append(session, {"role": "user", "content": message})
        yield StreamStart(session_id=session.id, matched=matched_names)

        system_prompt = BASE_SYSTEM_PROMPT
        skill_context = self.skills.context(matches)
        if skill_context:
            system_prompt += "\n\n" + skill_context

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        messages.extend(session.messages)
        await self.audit.write(
            "agent.start",
            {
                "session_id": session.id,
                "message": message,
                "provider": session.provider,
                "model": session.model,
            },
        )

        for round_number in range(self.max_rounds):
            # 流式拉取本轮响应：先透传文本增量（AnswerDelta），最后拿到聚合好的
            # AssistantTurn 再判断这一轮是要调工具还是给最终答案。
            turn: AssistantTurn | None = None
            streamed_text = False
            try:
                async for chunk in model.respond_stream(messages, self.tools.schemas()):
                    if isinstance(chunk, TextDelta):
                        if chunk.text:
                            streamed_text = True
                            yield AnswerDelta(text=chunk.text)
                    else:
                        turn = chunk
            except Exception as exc:
                await self.audit.write("agent.error", {"session_id": session.id, "error": str(exc)})
                yield AgentEvent(type="error", name="model", status="error", detail=f"模型调用失败：{exc}")
                return
            if turn is None:
                turn = AssistantTurn()

            assistant_message: dict[str, Any] = {"role": "assistant", "content": turn.content or ""}
            if turn.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                    }
                    for call in turn.tool_calls
                ]
            messages.append(assistant_message)
            if not turn.tool_calls:
                answer = turn.content or "任务已完成，但模型没有返回文字说明。"
                await self.sessions.append(session, {"role": "assistant", "content": answer})
                await self.audit.write("agent.finish", {"session_id": session.id, "rounds": round_number + 1})
                # streamed=True 表示文本已逐字发出，前端据此定稿即可，不必整段重绘。
                yield AgentEvent(
                    type="result",
                    name="answer",
                    status="success",
                    detail=answer,
                    payload={"streamed": streamed_text},
                )
                return

            for call in turn.tool_calls:
                yield AgentEvent(
                    type="tool",
                    name=call.name,
                    status="running",
                    detail="模型请求执行工具",
                    payload={"arguments": call.arguments},
                )
                if self.require_confirmation and self.tools.requires_confirmation(call.name):
                    output = json.dumps(
                        {"error": f"工具 {call.name} 需要人工确认，已被策略拒绝执行。"},
                        ensure_ascii=False,
                    )
                    messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": output})
                    await self.audit.write(
                        "tool.blocked",
                        {"session_id": session.id, "tool": call.name, "arguments": call.arguments},
                    )
                    yield AgentEvent(type="tool", name=call.name, status="blocked", detail=output[:TOOL_DETAIL_LIMIT])
                    continue
                try:
                    output = await self.tools.execute(call.name, call.arguments)
                    status = "success"
                except Exception as exc:
                    output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    status = "error"
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": output})
                await self.audit.write(
                    "tool.call",
                    {"session_id": session.id, "tool": call.name, "status": status, "arguments": call.arguments},
                )
                yield AgentEvent(type="tool", name=call.name, status=status, detail=output[:TOOL_DETAIL_LIMIT])

        message_id = uuid.uuid4().hex[:8]
        error = f"工具调用超过 {self.max_rounds} 轮限制（trace={message_id}）。"
        yield AgentEvent(type="error", name="agent", status="error", detail=error)

    async def run(
        self,
        message: str,
        model: ModelClient,
        session_id: str | None = None,
        *,
        provider: str = "",
        model_id: str = "",
    ) -> tuple[str, str, list[AgentEvent], list[str]]:
        """非流式入口：消费 run_stream 并聚合成最终四元组。

        团队模式（orchestrator）和现有测试仍依赖这个签名。最终答案取自
        type="result" / type="error" 事件的 detail。
        """
        events: list[AgentEvent] = []
        session_id_out = session_id or ""
        matched: list[str] = []
        answer = "任务已完成，但没有产生最终回答。"
        async for item in self.run_stream(
            message,
            model,
            session_id,
            provider=provider,
            model_id=model_id,
        ):
            if isinstance(item, StreamStart):
                session_id_out = item.session_id
                matched = item.matched
                continue
            if isinstance(item, AnswerDelta):
                # 非流式聚合不关心文本增量；最终答案取自 result 事件。
                continue
            events.append(item)
            if item.type in {"result", "error"}:
                answer = item.detail
        return answer, session_id_out, events, matched
