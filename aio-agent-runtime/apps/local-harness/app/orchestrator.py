import json
import logging
from typing import AsyncIterator

from .agent import AgentRunner, AnswerDelta, ConfirmRequest, Confirmer, StreamStart
from .llm.base import ModelClient, Usage
from .models import AgentEvent
from .sessions import SessionStore


logger = logging.getLogger(__name__)


class Orchestrator:
    """轻量团队模式：规划、执行和汇总由确定性代码串联。"""

    def __init__(self, runner: AgentRunner, sessions: SessionStore, max_steps: int = 4):
        self.runner = runner
        self.sessions = sessions
        self.max_steps = max_steps

    async def run_stream(
        self,
        message: str,
        model: ModelClient,
        session_id: str | None,
        mode: str,
        *,
        provider: str = "",
        model_id: str = "",
        confirmer: Confirmer | None = None,
    ) -> AsyncIterator[StreamStart | AnswerDelta | ConfirmRequest | AgentEvent]:
        """流式执行；single 模式直接透传给 AgentRunner，team 模式逐步执行并汇总。

        confirmer 一路透传到子步骤，因此 team 模式下的破坏性工具同样会弹确认框，
        而不是像以前那样因为拿不到 confirmer 被直接判为拒绝。
        """
        if mode != "team":
            async for item in self.runner.run_stream(
                message,
                model,
                session_id,
                provider=provider,
                model_id=model_id,
                confirmer=confirmer,
            ):
                yield item
            return

        parent = await self.sessions.get_or_create(
            session_id,
            message,
            provider=provider,
            model=model_id,
        )
        matched = [item.name for item in self.runner.skills.match(message)]
        yield StreamStart(session_id=parent.id, matched=matched)
        await self.sessions.append(parent, {"role": "user", "content": message})

        # 进 team 之前先快照会话累计量。子步骤会把各自的消耗直接加到共享会话上，
        # 所以「本次消耗」只能靠前后差值切出来——直接上报 parent.usage 的话，
        # 在已有会话上跑 team 会把之前所有轮次的消耗算成这一次的。
        # Usage 是 frozen dataclass，这里持有的是旧值，不会被后续累加改写。
        usage_before = parent.usage

        yield AgentEvent(type="plan", name="planner", status="running", detail="正在拆分任务")
        steps, plan_usage = await self._plan(message, model)
        await self.sessions.add_usage(parent, plan_usage)
        yield AgentEvent(type="plan", name="planner", status="success", detail="；".join(steps))

        # 子步骤自己会把消耗累加到共享会话上，这里只额外记规划和汇总两次调用。
        overhead = plan_usage
        answers: list[str] = []
        for index, step in enumerate(steps, start=1):
            step_answer = ""
            # 传 parent.id 让每一步共享同一个会话：第 2 步能看到第 1 步做了什么、
            # 生成了哪些文件，不必依赖最后的汇总来缝合上下文。
            async for item in self.runner.run_stream(
                f"这是团队模式的第 {index} 步，只处理下面的子任务：\n{step}",
                model,
                parent.id,
                provider=provider,
                model_id=model_id,
                confirmer=confirmer,
            ):
                if isinstance(item, StreamStart):
                    continue  # 子步骤的会话信号不外发，会话 id 以 parent 为准
                if isinstance(item, AnswerDelta):
                    # 子步骤答案改由 step 事件整段给出，避免多段打字机在同一气泡里互相覆盖。
                    continue
                if isinstance(item, ConfirmRequest):
                    yield item
                    continue
                if item.type in {"result", "error"}:
                    step_answer = item.detail
                    # 子步骤终态一律记为 result，type="error" 留给整个流程失败；
                    # 失败信息通过 status 传递，前端照常标红。
                    yield AgentEvent(
                        type="result",
                        name=f"step-{index}",
                        status=item.status,
                        detail=item.detail,
                        payload={"step": index, "total": len(steps)},
                    )
                    continue
                yield item
            answers.append(step_answer)

        summary, summary_usage = await self._summarize(answers, model)
        await self.sessions.add_usage(parent, summary_usage)
        overhead = overhead + summary_usage
        await self.sessions.append(parent, {"role": "assistant", "content": summary})
        yield AgentEvent(
            type="result",
            name="answer",
            status="success",
            detail=summary,
            payload={
                "streamed": False,
                # 本次 team 运行的消耗 = 会话累计的前后差值（规划 + 各子步骤 + 汇总）。
                "usage": (parent.usage - usage_before).to_dict(),
                "planner_usage": overhead.to_dict(),
            },
        )

    async def run(
        self,
        message: str,
        model: ModelClient,
        session_id: str | None,
        mode: str,
        *,
        provider: str = "",
        model_id: str = "",
    ) -> tuple[str, str, list[AgentEvent], list[str]]:
        """非流式入口：消费 run_stream 并聚合成最终四元组。

        没有 confirmer，需要确认的工具会被直接拒绝——非流式接口没有回传通道。
        """
        events: list[AgentEvent] = []
        session_out = session_id or ""
        matched: list[str] = []
        answer = "任务已完成，但没有产生最终回答。"
        async for item in self.run_stream(
            message,
            model,
            session_id,
            mode,
            provider=provider,
            model_id=model_id,
        ):
            if isinstance(item, StreamStart):
                session_out = item.session_id
                matched = item.matched
                continue
            if isinstance(item, (AnswerDelta, ConfirmRequest)):
                continue
            events.append(item)
            if item.type == "error" or (item.type == "result" and item.name == "answer"):
                answer = item.detail
        return answer, session_out, events, matched

    @staticmethod
    async def _complete(model: ModelClient, system: str, user: str) -> tuple[str, Usage]:
        """调 complete 并尽量拿到 usage。

        complete_with_usage 是可选实现（测试里的 fake model 通常只有 complete），
        缺失时退回 complete，消耗记为一次未上报的调用。
        """
        with_usage = getattr(model, "complete_with_usage", None)
        if with_usage is not None:
            return await with_usage(system, user)
        return await model.complete(system, user), Usage(calls=1)

    async def _plan(self, message: str, model: ModelClient) -> tuple[list[str], Usage]:
        usage = Usage()
        try:
            raw_plan, usage = await self._complete(
                model,
                "请把用户任务拆成最多 4 个可以顺序执行的短步骤，只返回 JSON：{\"steps\":[\"步骤\"]}。",
                message,
            )
            parsed = json.loads(raw_plan)
            steps = [str(step) for step in parsed.get("steps", [])][: self.max_steps]
        except Exception:
            logger.warning("团队模式规划失败，回退为单步执行", exc_info=True)
            steps = []
        return steps or [message], usage

    async def _summarize(self, answers: list[str], model: ModelClient) -> tuple[str, Usage]:
        summary = "\n\n".join(
            f"步骤 {index}：{answer}" for index, answer in enumerate(answers, start=1)
        )
        if len(answers) <= 1:
            return summary, Usage()
        try:
            return await self._complete(
                model,
                "请用中文汇总多个执行步骤，保留文件名、结果和失败信息，不要编造。",
                summary,
            )
        except Exception:
            logger.warning("团队模式汇总失败，返回未汇总的分步结果", exc_info=True)
            return summary, Usage()
