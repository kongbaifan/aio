# 同一 Run 内的持久 Team 编排契约

> 入口：`app/runtime/{team,team_contracts,execution,worker}.py`。Team 由 `0008_team` 引入，当前应用为 `0013_shared_budgets`。
> 这是已实现路径与明确限制，不是企业平台或 RUN-11 全部验收通过的声明。

## 1. Scope / Trigger

Team 是同一业务任务的 **规划 → 顺序步骤 → 汇总**，不是多人共享进程，也不是给每个步骤创建另一个用户、Run 或项目。

- 复用原 Run 的 actor、AgentVersion、固定 Manifest、MCP 连接版本、预算预留、截止时间、取消状态、租约和工作区单写约束。
- 同一有效 generation 内，有需要的步骤共用 `compute/main`；不按步骤创建常驻容器。
- 新 Run 使用独立 writer/cell，只能从获权的不可变项目版本/输入恢复文件；不能继续使用上一个 Run 的可变容器。
- 不在 API/Worker 主机执行业务 Python、安装依赖或解析用户文档；Team 没有新增宿主执行 fallback。
- v9 在安全审批边界提供私有文件检查点交接：旧 cell 销毁确认后，新代次校验来源/字节再恢复新环境。没有 ready 检查点的旧活动 cell 仍禁止直接采用；进程与内存不恢复。

## 2. Signatures / DB

```text
TeamPolicy(max_steps=4 [1..6], max_step_rounds=4 [1..16])
policy_for(manifest, required=False) -> TeamPolicy | None
parse_plan(raw_text, manifest) -> TeamPlan
TeamRuntime.initialize(c, run, handle, manifest, checkpoint) -> Checkpoint
TeamRuntime.cursor(c, run, manifest) -> verified stage/cursor/steps
TeamRuntime.allowed_tools(c, run, manifest) -> set[approved_alias]
TeamRuntime.metadata(c, run, manifest) -> team_stage + team_step_id
ExecutionStore.advance_team(handle, checkpoint_seq) -> bool advanced
TeamRuntime.publication(c, run, final_checkpoint) -> answer, result metadata, incomplete?
team_view(c, authorized_run) -> durable step projection
stop_team(c, run, terminal_state, reason, event_writer) -> no external calls
```

新增 `aio_run_teams`、`aio_run_steps` 两张表；模型事实增加 `team_stage/team_step_id`，工具事实增加 `team_step_id`。步骤及检查点外键包含 `org_id/run_id`，不能把另一组织或另一 Run 的步骤挂上来。新表继续 FORCE RLS，操作员需要刷新 runtime grants。

- `run_teams`：唯一 Run、stage、current_step、初始/规划 checkpoint 引用、完整计划与摘要。
- `run_steps`：Run 内唯一 ordinal、固定 definition/digest、state、输入/输出 checkpoint 序号、开始/结束全局轮次、结果与原因、时间。
- 计划/定义摘要在执行边界核对；模型和工具事实归属还需匹配当前 cursor，不能只比较工具别名。
- 旧 `schema_v1`～`schema_v7` 保留；`Checkpoint.schema_version=1` 的序列化和 digest **没有加默认字段**。新阶段另写 v1 checkpoint，不改变旧 hash。

状态：

```text
team: queued(投影) -> planning -> step -> synthesis -> completed
任一阶段 -> stopped
step: pending -> running -> succeeded | failed | denied
停止时: 当前步骤 -> failed | cancelled | timed_out | recovery_required
       未开始步骤 -> skipped
```

`completed` 只表示编排已收敛；若步骤失败/拒绝，Run 仍为 `failed`，不是业务成功。

## 3. Request / Response / Execution Contracts

### 3.1 管理员发布与用户发起

`POST /api/v2/admin/agents` 可提交：

```json
{"team":{"max_steps":2,"max_step_rounds":3},"max_rounds":8,"run_budget":"0.10"}
```

上例省略其余必填 Agent 字段。`team=null` 或省略表示未开放；旧 Agent 不自动获得 Team。发布时要求全局 `max_rounds >= max_steps + 2`，预算至少覆盖规划、每步一次模型调用和汇总的已发布费用上界。这只是最低准入，后续工具循环与 embedding 仍可能耗尽统一预算。

`RunCreate.mode=team` 仅对 `local-harness-v2` 且固定 AgentVersion 已启用的版本开放；不符合时在 Run/消息/预算写入前拒绝，不静默按 single 运行。

`/api/v2/me.capabilities.team=true` 表示引擎支持；具体会话的 `supported_modes` 决定是否显示入口。客户端不是授权来源。

### 3.2 Planner 的有界输出

```json
{
  "schema_version":1,
  "steps":[
    {"title":"读取资料","task":"处理本任务已授权资料","tools":["python_compute"]},
    {"title":"核对结果","task":"只依据前一步实际结果说明结论","tools":[]}
  ]
}
```

- 严格 JSON，拒绝重复 key、非有限数、代码围栏、未知字段和旧自由字符串数组。
- 总输入 <= 65536 bytes；最多发布策略允许的步骤数（绝对上限 6）。title <=120 字符、task <=4000 字符且非空。
- 每步最多 64 个唯一、格式合法的 alias，必须是父 Manifest 的子集。未填 `tools` 等价于空子集，不是全部工具。
- Planner 不能指定模型、用户、Agent、凭据、网络、镜像、审批规则或追加 scope。非法计划会付清/保留已经发生的模型费用，然后停止，不补一个“兜底计划”继续干活。
- Planner/汇总向模型暴露的 tools 为 `[]`；即使模型仍返回 tool_calls，也在创建 dispatch 之前拒绝。

### 3.3 Checkpoint、计费与执行顺序

1. 原已获权历史先保存初始 v1 checkpoint；Planner 使用另一个 checkpoint，不丢失原上下文来源。
2. 完整模型回合及费用先在既有事务提交；随后计划/步骤状态迁移和新 checkpoint 原子提交。
3. 阶段切换可以重建 messages，但全局 `round` 只增不减。`model:{round}`、`turn:{round}:tool:{index}` 在步骤间不复用。
4. 新步骤收到原始 Agent 指令、获权历史和前序结果；任务/Skill/步骤答案都作为不可信数据，不能变成授权。
5. 已执行工具保存模型/工具事实与所属 step；审批后恢复使用同一 invocation/ActionSpec，不重新让模型生成参数。
6. 步骤达到轮数上限后保存失败状态；全局轮数预留后续步骤各一次调用和最终汇总。钱与时间仍是共享硬上限，不为汇总再开一次预算。
7. 只有最终汇总可以发布 assistant message 与产物；Manager 的控制授权也检查 synthesis 阶段，不能因为中间步骤已有 final checkpoint 就提前导出/终结共享工作区。步骤文字走 `team.output.delta`，最终汇总走 `answer.delta`。

前序结果提供给下一模型阶段时，每步 answer 按 UTF-8 截至 16384 bytes，并明确 `answer_truncated_for_context`。完整结果仍留在授权步骤投影/checkpoint。整体仍受既有 checkpoint 字节/消息上限；没有实现完整 token 预算或自动摘要策略。

### 3.4 来源、失败和停止

- 保留并逐次重新授权 `provenance_source_ids`、`capability_source_ids`、`capability_read_source_ids`、`mcp_source_refs`、`knowledge_source_refs`。阶段重建 messages **不得清空这些字段**。
- Step 输出/Team 投影与 Run、事件、最终答案使用相同当前授权；撤文档或连接后不能绕到步骤页读旧内容。
- 已确认未发送的工具失败、审批拒绝/过期、已确认非零 Python exit、MCP `is_error` 都不会被模型一句“成功”覆盖。
- 存在失败步骤时，汇总输入含真实状态，最终答复加平台状态说明，Run=`failed` / `TEAM_STEPS_INCOMPLETE`，保留已合法产生的输出。
- 外部响应丢失、已发送模型回合丢失、存活旧代次 cell：停止整条 Run，按既有账务/cleanup/blocker 规则核对。不带着 unknown 继续后续步骤或请求汇总。
- 取消/截止/撤权不额外发送一次“解释失败”的模型请求。已完成步骤保留，未开始步骤是 skipped。

## 4. Validation & Error Matrix

| 条件 | 服务端行为 |
|---|---|
| Agent 未开放 Team | `TEAM_NOT_ENABLED`，没有新预留/消息/Job |
| 未安装引擎/未知模式 | `ENGINE_MODE_UNAVAILABLE` |
| 发布全局轮数不足 | 请求校验失败；坏持久策略为 `TEAM_POLICY_INVALID` |
| 发布预算不足以覆盖最低调用次数 | `AGENT_BUDGET_INVALID` |
| Planner 增权/非法 JSON/超限 | `TEAM_PLAN_INVALID`，不执行兜底步骤 |
| Planner 或汇总请求工具 | `TEAM_STAGE_TOOLS_FORBIDDEN` |
| Step 请求父权限内但步骤子集外的工具 | `TEAM_TOOL_NOT_ALLOWED`，不签发 permit |
| 相同 provider call ID 跨步骤重复 | 全局 logical ID 不同，不混淆 ActionSpec/费用 |
| 修改计划/定义/游标 | `TEAM_STATE_CORRUPT` 或原 checkpoint 完整性错误 |
| 旧 worker/旧 checkpoint 提交 | 原 `STALE_GENERATION` / `CHECKPOINT_CONFLICT` |
| 启动另一步的 prepared model call | `MODEL_CALL_CONFLICT` |
| 达到步骤/global 分配轮次 | `TEAM_STEP_ROUND_LIMIT`，真实失败状态进入汇总 |
| 钱/截止不足，连汇总也不允许 | `RUN_BUDGET_EXCEEDED` / `RUN_DEADLINE_EXCEEDED`，不再外发 |
| 审批后新代次仍有旧可变 cell 或未完成文件检查点 | `PROCESS_STATE_LOST` / checkpoint 错误 → recovery；只有完整 ready 交接可恢复 |

## 5. Good / Base / Bad

- **Good**：步骤 1 在一个无网 cell 写中间文件；步骤 2 在同代次同 Run 读取它；最终一次发布。下一个 Run 使用另一 cell，前一次附件字节不变。
- **Base**：两步纯文字，Planner/两步/汇总共四次已记账请求；审批前未分配 cell 的任务可按持久 cursor 换 Worker 恢复。
- **Bad**：上一代已经做过计算，等待审批后直接拿旧 cell ID 给新 Worker 使用。必须使用完整文件检查点和新的执行绑定；仍未停止或没有检查点时先阻断。
- **Bad**：模型输出“所有步骤成功”，但步骤 1 被拒绝。以数据库状态和平台说明为准，Run 不能改成 succeeded。

## 6. Tests / Assertion Points

- `test_team_contracts.py`：严格计划、工具子集/冲突、策略/字节/步骤边界、布尔版本拒绝、旧 checkpoint digest 不变。
- `test_team_integration.py`：真实 PG 上单 Run 多步骤、费用和唯一逻辑 ID、审批释放/恢复/拒绝/过期、完成 checkpoint 后重启、取消/截止、预算包括汇总、unknown usage hold、代次/归属/定义校验、来源继承与撤权、RLS/复合 FK。
- `test_sandbox_pipeline.py` Team 场景验证同代次文件共享、控制授权及缺交接 hook 时阻断；`test_workspace_handoff.py` 另验证真实文件跨审批/换代次恢复、多次快照、故障和引用 GC。两类证据不能混为“任意进程透明恢复”。
- `web/platform/tests/team.test.tsx`：管理配置、版本级模式开关、网络丢响应保留同一 mode/key、步骤状态、长 SSE 中刷新投影、禁止内部输出混入最终草稿、撤权清空投影。
- `verify_workbench_http.py`：真实 HTTP/OIDC/PG/Worker/Docker 的 compute/MCP/KB Team 路径；供应商及业务数据仍是显式合成的，不是公司真实 UAT。

## 7. Wrong vs Correct

```text
Wrong: add team_stage="single" to Checkpoint v1 and recompute old checkpoint hashes
Correct: preserve v1 bytes, store stage in new tables, keep global round monotonic

Wrong: hide unapproved tools in UI, but dispatch from the full parent manifest
Correct: model exposure + planning + permit consumption all require the committed step subset

Wrong: clear source arrays when starting another step to reduce context size
Correct: keep provenance, reauthorize it, only bound the textual projection

Wrong: every exception -> failed step -> continue to synthesis
Correct: known results can be summarized; unknown side effects stop the whole Run
```

## 8. v9 文件交接及其明确边界

原计划的内部文件检查点、隔离导出、来源/配额绑定、停止确认、新代次恢复和引用 GC 已落地。审批在导出时到达也必须结束旧代次；完整 ready 之后 Worker 丢失可恢复，不重跑已完成步骤。详见 [工作区文件检查点契约](platform-workspace-checkpoint-contract.md)。

这些能力只针对有界文件与安全审批边界。半完成导出、活跃的无检查点旧进程、未知外部效果仍保留阻断；Node/浏览器内存、跨节点对象存储、全量故障矩阵和 HA 不因此完成。

HTTP OAuth 与隔离无网络 stdio 已分别落地，Team 不绕开其连接身份和生命周期约束。完整平台还包括更多 OAuth 扩展、stdio 受控联网/更多运行时、可核对业务写、Skill 完整包生命周期、外部知识源/OCR、企业治理/HA 与公司验收；不能从本增量宣布“做完”。
