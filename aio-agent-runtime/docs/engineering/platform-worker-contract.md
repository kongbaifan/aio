# Durable Worker Code Contract

## 1. Scope / Trigger

适用于 `app/runtime/{contracts,catalog,execution,model_client,worker}.py`、`run_worker.py` 和后续迁移。第一版平台底座之上增加可验证的后台模型/工具事务；真实 Python/Skill、只读 HTTP/隔离 stdio MCP 和知识检索已接入；可核对真实业务写和完整生产 Gate 仍待实现/验收。

## 2. Signatures

```text
WorkerSettings.from_env(env?) -> no browser/IdP credentials required
DurableWorker.run_once() -> no job | suspended | terminal | requires lifecycle reconciliation
ExecutionStore.load(handle) -> Run + fixed manifest + verified checkpoint
prepare_model_call(handle, checkpoint_seq, request_digest, max_charge)
start_model_call(handle, call_id) -> current approved model version
complete_model_call(handle, checkpoint_seq, call_id, turn, actual_charge?)
plan_tool(handle, checkpoint_seq) -> immutable Invocation/Approval
prepare_dispatch(handle, checkpoint_seq, invocation_id) -> prepared permit record
consume_dispatch(handle, dispatch_id) -> one-shot DispatchPermit
complete_dispatch(handle, checkpoint_seq, dispatch_id, output, outcome)
recover_due(org_id) -> expired/uncertain/safely requeued jobs
reconcile(principal, run_id, expected_revision, conclusion, evidence_ref)
record_late_model_usage(principal, call_id, amount, evidence_ref)
```

`WorkHandle` 只能从受信 Worker 领取记录建立，不由浏览器 JSON 提供；handle 关联原始 actor、服务 actor、代次、有效期。

## 3. Implemented Contracts

- `schema_v1`～`schema_v12` 是不可变迁移快照；v10 加入与原浏览器会话绑定的 OAuth 意图，v11 加入身份/Run/代次绑定的 stdio 租约，v12 加入 Skill 归档隔离导入。应用从 `db.schema` 导入，Alembic 升级到 `0013_shared_budgets`。旧读取器不认识新生命周期，未验证兼容前禁止混跑；Checkpoint v1 hash 不变。
- `mcp.http` 和 `mcp.stdio` 注册同一 `MCPDriver`，统一执行当前连接/工具授权与来源约束；finalize/suspend/cleanup 经 Gateway 停止 stdio。旧进程 lost 或停止未确认时保留核对/清理阻断，不静默开启新会话重放旧调用。见 [stdio 契约](platform-mcp-stdio-contract.md)。
- stdio 显式附件输入需要模板 opt-in 与固定在 Run input 中的 `allow_stdio_attachments=true`。Worker 不提供宿主/活动 compute workspace；仅由权限端冻结本次所选附件，Gateway 首开转交到独立 cell，来源/撤权仍使用同一 Run 事实。见 [附件契约](platform-mcp-stdio-input-contract.md)。
- 运行账号不是迁移 owner；新增表需要受控操作员调用 `grant_runtime_access` 授予权限。启动检查 revision、FORCE RLS、表 owner 和 SELECT 权限，不能匿名降级。
- model call / tool invocation / dispatch / checkpoint 是不同事实。完整模型回合先落盘，再调用工具；工具结果、下游游标、事件在同一事务提交。
- ActionSpec 和 Manifest 绑定已发布工具 digest、driver、risk、输入 schema、参数/资源范围；派发时重新检查当前用户、Project、Agent、Tool 和批准者资格。
- `prepared` 不产生外部调用；`consume_dispatch` 只能成功一次，变为 `dispatching` 后失败不能自动视为“没有发生”。
- 安全重试保留逻辑业务 operation key；旧 generation 不能执行/提交新状态。审批正常挂起/唤醒不消耗 crash recovery 次数。
- 审批等待落库并释放 Worker；决定后 Job 可再次领取，使用原已提交工具调用，不重新询问模型生成另一份写参数。
- 取消/租约失效时已发送工具/模型结果不明进入 `recovery_required`；未知工具影响或未确认停止的 cell 保留 durable blocker。
- 计算资源未核实销毁时，核对接口不得解除 blocker。人工确认某外部动作成功不等于整个 Agent 任务成功，原任务以明确需新建任务的结果终结，不静默续跑。
- 缺 usage 的模型调用保留费用 hold，已知费用只入账一次。迟到真实费用用有权限的追加 adjustment 核对，即使超过原估计也不丢账。
- `ChatModel` 不使用旧 `.env`/ModelRegistry/Shell Key 解析；endpoint origin 和 Secret 环境变量名必须由操作员单独 allowlist。
- 模型请求不自动重试。SSE 字节/帧/文本/工具参数有上限，拒绝重定向和压缩流，不回显 provider 原始错误体。
- Worker 配置与 Web BFF 分离，不要求 Worker 持有 OIDC client secret。生产数据库 TLS 和模型 HTTPS 仍强制。
- 缺少已注册执行器就失败，不运行本机 subprocess。CLI 根据显式 manager/storage 配置注册 sandbox.python/skill.python，按独立网关配置注册只读 mcp.http，并提供获权 knowledge.search。更多执行驱动尚未开放；没有配置就拒绝，不回落本机。真实 Python/产物链路见 [沙箱契约](platform-sandbox-contract.md)，不能把测试 EffectSink 当业务连接器。
- 当前 `local-harness-v2` 支持 single 与显式发布开放的顺序 Team；旧 Agent 没有 Team 策略则在准入拒绝。见 [Team 契约](platform-team-contract.md)。审批唤醒不采用旧 cell；使用已确认的 [文件检查点](platform-workspace-checkpoint-contract.md) 在新代次恢复。没有 ready 快照或旧 writer 未停止，仍在任何新动作前拒绝。

## 4. Validation & Error Matrix

| 场景 | 行为 |
|---|---|
| 旧/过期 lease、错误服务 actor | STALE_GENERATION / WORKER_IDENTITY_INVALID |
| 固定 Manifest/工具/模型版本变化或撤权 | 停止，不替换成另一个工具/账号 |
| 模型预算参数低于已发布 max_call_charge | MODEL_COST_POLICY_CHANGED，不发请求 |
| 模型已 started 后流丢失 | 未知结果/费用保持，不自动重发 |
| 重复消费 dispatch | DISPATCH_ALREADY_CONSUMED，只有一次 permit |
| 已知工具结果写成功、checkpoint 写失败 | 同事务全回滚，保留 executing/不确定事实供核对 |
| 只 prepared、未发送时 Worker 丢失 | 新代次可从同 checkpoint 恢复；旧 permit 作 not_sent |
| 已 dispatching 时 Worker 丢失 | recovery_required，不普通重排 |
| 对应执行器未安装 | TOOL_EXECUTOR_UNAVAILABLE，dispatch 不消费，不走宿主命令 |
| cell 仍 leased/未清理就核对解除阻断 | CLEANUP_UNCONFIRMED |
| 原发起人自核对/无 reconcile Grant | 403/404，必须不同的获权核对者 |
| 账单实际金额未知 | held_unknown，不记免费 |
| 相同账单凭据重复提交 | 幂等；不同金额/证据冲突 |

## 5. Good / Base / Bad Cases

- Good：模型第一轮→工具→模型汇总成功，消息/结果/费用/最终事件持久化，重启后查询一致。
- Base：审批等待结束一个 Worker lease；另一 Worker 在新 generation 执行已保存调用，未重复第一轮模型请求。
- Bad：下游已写成功但回复丢失。正确结果是 unknown 和 blocker，不是异常后重试一个新 operation key。
- Bad：进程可能仍在 cell 里运行时清除项目阻断。必须先经外部 manager 确认停止，不以内部 runner 自报为凭据。

## 6. Tests Required

- `test_worker_contracts.py`：真实解析分片 UTF-8/CRLF SSE、工具参数聚合、缺 DONE、错误/重定向、未知 usage、credential allowlist、checkpoint 规范。
- `test_execution_integration.py`：真实 PG 上 Worker/model-tool-model、审批挂起跨 Worker 恢复、拒绝审批、一次性派发、结果/游标原子回滚、租约过期、未知写核对、费用 hold/迟到 adjustment、未清理 cell 阻断、审批 API 权限、迁移 v1→v2。
- `test_run_lock_order.py`：真实 PG 队列资源/Run/Job 繁忙跳过、候选 savepoint 完整释放、当前条件重验、控制入口与系统清理锁序、非繁忙数据库错误传播。算法与已复现的旧锁环见 [生命周期锁序契约](platform-stdio-lock-order.md)。
- 外部模型/工具为显式注入的合成服务或 httpx MockTransport；这证明后台状态协议，不证明外部供应商兼容或真实不可信代码隔离。
- 真沙箱、MCP/KB、Team 的增量测试见各自契约；本套件不替代进程快照、全量交接故障矩阵、真实公司目录/Secret 管理、长稳与 HA Gate，不能宣布全部平台完成。

## 7. Wrong vs Correct

```text
Wrong: model timeout -> restart prompt and retry every tool
Correct: persisted model turn + checkpoint + stable operation key; dispatching uncertainty requires reconciliation

Wrong: unresolved effect -> free all project constraints
Correct: release/clean compute safely, preserve durable blocker until trusted cleanup and authorized evidence

Wrong: unknown usage -> 0 cost -> release full reservation
Correct: held_unknown -> append-only verified adjustment -> release matching hold

Wrong: same model endpoint -> shared Secret/header client
Correct: approved immutable definition + per-creation permitted credential scope; no global legacy Key fallback
```
