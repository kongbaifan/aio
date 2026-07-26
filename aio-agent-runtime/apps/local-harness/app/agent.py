import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from .audit import AuditLogger
from .llm.base import AssistantTurn, ModelClient, TextDelta, Usage
from .models import AgentEvent
from .sessions import SessionStore
from .skills.registry import SkillRegistry
from .tools.registry import ToolRegistry


# 工具结果写入事件流时的截断上限，避免超长输出撑爆前端和审计日志。
TOOL_DETAIL_LIMIT = 2000

# 工具结果进入模型上下文时的截断上限。
# 这一层以前是没有的：sandbox 侧 read_file 允许 10MB、execute_python 输出允许 1MB、
# browser_snapshot 完全无上限，全量字符串会直接进 messages，而且会留在里面
# 参与之后的每一轮，token 成本按轮次翻倍，长会话必然撑爆 context。
TOOL_CONTEXT_LIMIT = 8000


def _truncate_for_model(output: str, limit: int) -> str:
    """按上限截断工具输出，并显式告知模型「这里被截断了」。

    不加说明的话模型会把截断处当成文件真正的结尾，进而给出错误结论。
    """
    if limit <= 0 or len(output) <= limit:
        return output
    return (
        output[:limit]
        + f"\n\n[输出已截断：完整内容共 {len(output)} 字符，此处只保留前 {limit} 字符。"
        f"需要后续内容请分段读取（如指定偏移量或先用命令过滤）。]"
    )


@dataclass
class StreamStart:
    """流式执行的首个信号：会话已就绪、Skill 已匹配，可先渲染。"""

    session_id: str
    matched: list[str] = field(default_factory=list)


@dataclass
class AnswerDelta:
    """最终答案的文本增量（打字机效果，仅新增片段，非累计）。"""

    text: str = ""


@dataclass
class ConfirmRequest:
    """请求人工确认某个破坏性/执行类工具调用。

    上层（SSE 端点）据此向前端弹窗；用户批准/拒绝后通过反向通道回传。
    """

    confirmation_id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


# 确认回调：给定一次 ConfirmRequest，返回用户是否批准执行。
# 返回 None 视为超时/连接断开，按拒绝处理。
Confirmer = Callable[[ConfirmRequest], Awaitable[bool]]


BASE_SYSTEM_PROMPT = """你是一个本地 AI 工作助手。
你可以通过工具读取和修改 workspace 内文件、执行 Python、检查代码和查看运行时状态。
不要猜测工具结果，不要访问 workspace 之外的路径。
需要写文件或执行代码时，先选择最小必要操作；工具失败时解释原因并停止继续破坏性操作。

注意两类路径互不相通：
- read_file / write_file / list_files 操作的是 sandbox workspace，用 workspace 相对路径。
- read_skill / list_skill_files 读的是项目的 skill 文档目录，只读，用 skill 根相对路径。

任务落在某个 skill 的领域内时，先 read_skill 读它的 SKILL.md 再动手，按里面的命令和流程执行。

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
        tool_context_limit: int = TOOL_CONTEXT_LIMIT,
    ):
        self.tools = tools
        self.skills = skills
        self.sessions = sessions
        self.audit = audit
        self.max_rounds = max_rounds
        self.require_confirmation = require_confirmation
        self.tool_context_limit = tool_context_limit

    async def run_stream(
        self,
        message: str,
        model: ModelClient,
        session_id: str | None = None,
        *,
        provider: str = "",
        model_id: str = "",
        confirmer: Confirmer | None = None,
    ) -> AsyncIterator[StreamStart | AgentEvent]:
        """流式执行工具调用循环。

        先 yield 一个 StreamStart（会话与匹配到的 Skill），随后每产生一个
        AgentEvent（工具开始、工具结果、最终答案、错误）就立即 yield，供上层
        边执行边推送给前端。最终答案事件的 type 为 "result"、name 为 "answer"；
        超限或模型失败会 yield type="error" 的事件后结束。

        confirmer 存在时启用人工确认（human-in-the-loop）：遇到需确认的工具会
        先调用 confirmer 等待用户批准，批准才执行、拒绝则跳过。confirmer 为 None
        时回退到 require_confirmation 策略（直接拒绝），保持 run()/team/测试兼容。
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

        run_usage = Usage()
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
                # 这一轮的 token 数拿不到（上游中断前没上报），但至少要记一次调用，
                # 并把前几轮已经花掉的量带出去——否则 error 事件 payload 为空，
                # 上层的 run_usage 取不到值，整次请求的消耗在界面上显示为 0。
                run_usage = run_usage + Usage(calls=1)
                await self.sessions.add_usage(session, Usage(calls=1))
                await self.audit.write(
                    "agent.error",
                    {"session_id": session.id, "error": str(exc), "usage": run_usage.to_dict()},
                )
                yield AgentEvent(
                    type="error",
                    name="model",
                    status="error",
                    detail=f"模型调用失败：{exc}",
                    payload={"usage": run_usage.to_dict()},
                )
                return
            if turn is None:
                turn = AssistantTurn()
            run_usage = run_usage + turn.usage
            await self.sessions.add_usage(session, turn.usage)

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
                if turn.finish_reason == "length":
                    # 上游因 max_tokens 截断。不说的话，半截答案和正常完成
                    # 在界面上完全一样，用户会把它当成完整结论。
                    answer += "\n\n> ⚠ 回答因达到长度上限被截断，内容可能不完整。"
                await self.sessions.append(session, {"role": "assistant", "content": answer})
                await self.audit.write(
                    "agent.finish",
                    {
                        "session_id": session.id,
                        "rounds": round_number + 1,
                        "usage": run_usage.to_dict(),
                    },
                )
                # streamed=True 表示文本已逐字发出，前端据此定稿即可，不必整段重绘。
                yield AgentEvent(
                    type="result",
                    name="answer",
                    status="success",
                    detail=answer,
                    payload={"streamed": streamed_text, "usage": run_usage.to_dict()},
                )
                return

            for call in turn.tool_calls:
                yield AgentEvent(
                    type="tool",
                    name=call.name,
                    status="running",
                    detail="模型请求执行工具",
                    payload={"arguments": call.arguments},
                    call_id=call.id,
                )
                if self.require_confirmation and self.tools.requires_confirmation(call.name):
                    # 有 confirmer（交互式路径）：弹窗询问用户，批准才执行。
                    # 无 confirmer（run()/team/测试）：保持原有的直接拒绝行为，向后兼容。
                    approved = False
                    if confirmer is not None:
                        confirmation_id = uuid.uuid4().hex[:12]
                        yield ConfirmRequest(
                            confirmation_id=confirmation_id,
                            tool=call.name,
                            arguments=call.arguments,
                        )
                        try:
                            approved = await confirmer(
                                ConfirmRequest(
                                    confirmation_id=confirmation_id,
                                    tool=call.name,
                                    arguments=call.arguments,
                                )
                            )
                        except Exception:
                            approved = False
                    if not approved:
                        reason = (
                            "用户拒绝了该操作。" if confirmer is not None
                            else f"工具 {call.name} 需要人工确认，已被策略拒绝执行。"
                        )
                        output = json.dumps({"error": reason}, ensure_ascii=False)
                        messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": output})
                        await self.audit.write(
                            "tool.blocked",
                            {"session_id": session.id, "tool": call.name, "arguments": call.arguments},
                        )
                        yield AgentEvent(
                            type="tool",
                            name=call.name,
                            status="blocked",
                            detail=output[:TOOL_DETAIL_LIMIT],
                            call_id=call.id,
                        )
                        continue
                    await self.audit.write(
                        "tool.approved",
                        {"session_id": session.id, "tool": call.name, "arguments": call.arguments},
                    )
                try:
                    output = await self.tools.execute(call.name, call.arguments)
                    status = "success"
                except Exception as exc:
                    output = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    status = "error"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": _truncate_for_model(output, self.tool_context_limit),
                    }
                )
                await self.audit.write(
                    "tool.call",
                    {"session_id": session.id, "tool": call.name, "status": status, "arguments": call.arguments},
                )
                yield AgentEvent(
                    type="tool",
                    name=call.name,
                    status=status,
                    detail=output[:TOOL_DETAIL_LIMIT],
                    call_id=call.id,
                )

        message_id = uuid.uuid4().hex[:8]
        error = f"工具调用超过 {self.max_rounds} 轮限制（trace={message_id}）。"
        await self.audit.write(
            "agent.error",
            {"session_id": session.id, "error": error, "usage": run_usage.to_dict()},
        )
        # 超轮次是最费 token 的一种结束方式，usage 更不能丢。
        yield AgentEvent(
            type="error",
            name="agent",
            status="error",
            detail=error,
            payload={"usage": run_usage.to_dict()},
        )

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
