# 04. Run、审批、派发与故障恢复工程契约

> 关联 RUN-01～12、CAP-01、SBX-02/09/11、MCP-06。事务简称 TX 对应 [03 数据库配方](03-database-transactions.md)。

## 1. AgentRunner 的新职责边界

当前 `agent.py` 的循环、`main.py` 的 StreamingResponse、内存 ConfirmationRegistry 和 SessionStore 需要解耦成：

```text
API：验证请求 → TX-01 → 返回 Run ID
Worker：TX-02 → 加载 checkpoint → 驱动 EngineAdapter
EngineAdapter：模型回合 → 工具意图，不直接拥有系统执行权限
ToolGateway：当前授权/ActionSpec/审批/准入 → TX-03/05
Executor/远端 adapter：执行指定动作 → 结果证据
ResultCommitter：TX-06/08/09 → 更新游标/产物/用量
SSE：只读 RunEventStore，不启动或持有任务生命周期
Reconciler：过期 lease、未知效果、残留资源的事实核对
```

共享的是代码、无身份工具定义和受控服务；每 Run 的消息、游标、连接、语言内存、审批、工作区和费用独立。

## 2. Run 状态的精确定义

| 状态 | 可以做什么 | 不可以做什么 | 计算/资源处理 |
|---|---|---|---|
| queued | 等待领取、取消、过期 | 已产生业务副作用 | 不分配代码 cell |
| preparing | 绑定版本、取获权输入、分配所需 cell | 未授权地调用外部写 | 受准入和硬 deadline |
| running | 按委托和当前策略发新模型/工具 | 绕过 Gateway 或预算 | 同 Run 合法复用 cell |
| waiting_approval | 保存 checkpoint、展示获权审批、心跳 | 执行待批动作 | 期限内可保留 cell，计入配额 |
| persisting | 安全发布结果和用量事实 | 为补答案继续无限生成或改已批动作 | 停止/冻结相关 writer 后收集 |
| cancel_requested | 停新动作、请求停止、核对已发出动作 | UI 直接声称已停止/已撤销业务 | manager 外部停止 |
| recovery_required | 查询/核对/审计；被授权人终结 | 自动重试、继续原代码、释放所有业务阻断 | 释放或隔离计算；保留必要 blocker |
| succeeded/failed/cancelled/timed_out | 查询获权历史、另建有来源的新任务 | 再写入同一 Run 的新工具执行 | 异步核对清理，不能复用租过的 cell |

补充迁移：`waiting_approval → recovery_required` 用于环境/输入不再可安全恢复或副作用状态不明；不是强行恢复旧 Future。无外部影响且确认局部失败可以 failed，是否需人工核对根据事实而不是单一异常类决定。

`recovery_required` 保留 Session 未解决槽与必要资源 blocker；完成调查后转对应终态并显式解除 blocker，才能在同范围继续写。状态不可任意通过管理 PATCH 改成 succeeded。

## 3. Logical call 与 Dispatch 的区别

- **logical_call_id**：模型某个已提交完整回合中的一次逻辑工具动作。重复消费该回合应命中同一 ID。
- **action_digest**：此逻辑动作精确内容的摘要，同一 logical_call_id 不允许悄悄换参数。
- **dispatch_id**：一次受控派发尝试，可能有网络/进程失败。
- **external_operation_key**：送给下游的稳定业务幂等键。重试/换 Worker 时仍相同，不使用新的 generation 生成新业务操作。
- **generation**：限定“谁现在可以执行/推进状态”，不负责消除已发送的旧网络请求效果。

只有明确 not_sent 或下游有已验证的幂等/查询语义时才考虑重试。连接中断、请求超时、Worker 掉线都不能单独证明请求没到达。

## 4. ActionSpec v1 草案

```json
{
  "schema_version": 1,
  "canonicalization_version": "action-v1",
  "org_id": "uuid",
  "actor_user_id": "uuid",
  "run_id": "uuid",
  "logical_call_id": "call_0004",
  "tool_version_id": "uuid",
  "arguments_ref": {"object_id": "uuid", "sha256": "content-digest"},
  "resource_scope": {"system": "ticketing", "project_ids": ["project-A"], "max_rows": 1},
  "connection_id": "uuid",
  "credential_binding_revision": 4,
  "input_refs": [{"id": "uuid", "sha256": "input-digest"}],
  "entrypoint_digest": "approved-entrypoint-digest-or-null",
  "dependency_image_digest": "approved-image-digest-or-null",
  "network_profile_id": "restricted-profile",
  "data_policy_revision": 12,
  "approval_policy_id": "one-business-approver",
  "not_after": "2030-01-01T00:00:00Z"
}
```

示例 UUID/digest/时间是说明值，不是可发送的真实请求。实际 JSON schema 对 null/optional/格式必须严格定义。

### 4.1 规范化规则

- JSON 入站拒绝重复 key、非法 Unicode、NaN/Infinity、超范围整数、超深结构和未允许字段。
- 使用固定、审查过的 canonical JSON 实现和版本，写 golden vectors；不能不同模块用不同 `json.dumps` 参数算摘要。
- 金额等精确小数按 schema 使用标准十进制字符串；不靠二进制浮点精度决定审批内容。
- opaque ID、脚本字节、文档内容、URL path 不任意 lowercase/trim/Unicode 归一化。业务规范化必须在生成摘要前明确并展示给用户。
- 对内容引用使用已验证 immutable digest；摘要不能只包含可被改写的文件路径。
- 摘要加入域分隔和版本，例如 hash(`aio-action-v1` + canonical bytes)，但摘要本身不是签名/授权，仍须当前身份和审批。

### 4.2 防审批后的输入替换

批准对象必须是不可变内容集合。执行前重新校验脚本、输入、工具和连接版本，必要时将已批准文件作为只读对象挂载到新的固定执行目标。

不能批准一个可写 `/workspace/do.py`，让另一个后台进程改它后继续执行。依赖可被 workspace 中同名模块覆盖时，必须约束 import/启动环境或承认任意代码语义未受批准限制。关键外部写应由固定 connector adapter 执行业务参数，而不是给任意计算代码高权限 Token 后靠一次“批准运行脚本”治理。

## 5. Checkpoint 内容与恢复算法

```text
checkpoint:
  engine_schema_version, run_id, generation_at_write
  completed_model_turn_id, step_ordinal, round_index
  message_refs_with_provenance
  assistant_turn_with_logical_calls
  next_logical_call_index, committed_call_results
  pending_approval_id?, action_digest?
  manifest/agent/model/workspace/input versions
  restartability: stateless|reconstructible|process_state_dependent|unknown
  usage_ledger_refs, checkpoint_digest
```

### 5.1 保存边界

1. 模型完整回合收到并验证后，在调工具前保存该回合和所有 logical call IDs。
2. 每个工具结果提交时，结果引用、调用状态、next cursor、usage/event 同 TX-06 提交。
3. 进入 waiting_approval 前保存动作与 checkpoint；用户决定从 PG 唤醒，不靠进程内 Future。
4. 模型只输出一半时标 partial/usage unknown，不能把重试文本直接接到旧半句冒充同一次完整结果。
5. 保存失败不推进游标，不重复副作用以重新获得输出。

### 5.2 Worker 接管

```text
claim new generation
→ 查所有尚未终结的 Invocation/Dispatch
→ 若存在已发出但不明效果：恢复为 recovery_required，先核对
→ 否则读取最后完整 checkpoint 并验证 schema/digest/权限/版本
→ 检查所需进程状态是否可重建
→ 可重建：创建新的执行目标/许可，继续已保存的逻辑调用
→ 不可重建：使执行许可失效，明确失败或待人工决定，新任务另建 Run
```

不要在接管时从最初用户 prompt 再跑整个 Agent，然后希望模型恰好选择同样步骤。

## 6. 派发状态机与不可避免的窗口

`prepared → dispatching → acknowledged/running → confirmed_success|confirmed_failure|unknown`

- prepared：授权/意图已提交，但实现约定禁止在转换 dispatching 前发送。
- dispatching：允许发送；此状态后崩溃可能是发出前或发出后，所以不能自动当 not_sent。
- acknowledged：接收方确认接到请求，不一定意味着业务效果完成。
- confirmed：来自可信协议/下游查询的结果；计算 stdout 内容不构成外部业务效果确认。
- unknown：保存不确定事实，阻止危险自动重试。

| 故障窗口 ID | 中断位置 | 恢复依据 | 禁止行为 |
|---|---|---|---|
| FP-01 | TX-01 提交前 | 没有新 Run，按幂等键重试纯提交 | 预先执行工具 |
| FP-02 | Run 已提交、202 未送达 | 按同 key 查原 Run | 换 key 重建 |
| FP-03 | 领取 lease 后、创建 cell 前 | 新代次/manager 幂等查询 | 直接在控制机执行 |
| FP-04 | cell 已创建、manager 回复丢失 | run/generation/slot 找原实例 | 重复建无法追踪实例 |
| FP-05 | 模型部分输出、完整回合未存 | partial + unknown usage，安全新尝试明确标记 | 拼接成假完成回合 |
| FP-06 | 审批 pending 时 Worker 退出 | PG ActionSpec/checkpoint | 自动批准或丢掉待办 |
| FP-07 | approved 后脚本/输入/连接改变 | 摘要和当前版本不符→失效 | 沿用旧批准 |
| FP-08 | dispatching 后未知是否发出 | 接收方去重/查询或人工核对 | 自动产生新业务键重发 |
| FP-09 | 下游成功、回复/结果落盘失败 | 稳定 key/下游记录核对 | 按普通网络失败重试 |
| FP-10 | 结果已存、游标事务未提交 | 唯一调用记录/同 TX 检查 | 再次产生副作用 |
| FP-11 | 候选文件上传、发布事务失败 | 候选仍不公开，重试发布/CAS | 直接返回全桶链接 |
| FP-12 | Run 终态、清理消息丢失 | DB+runtime Reaper 对账 | 把未销毁资源回池 |

## 7. 同一动作的重复请求响应

| 已有事实 | 相同 logical_call_id + 相同摘要 | 相同 ID + 不同摘要 |
|---|---|---|
| planned/authorized | 返回已有状态，可继续原工作 | 409 ACTION_CONFLICT |
| waiting_approval | 返回已有审批 ID | 409，不修改待批内容 |
| executing | 返回 in_progress，不新增派发 | 409 |
| confirmed success/failure | 返回获权已有结果 | 409 |
| unknown | 返回需要核对，禁止普通重试 | 409 + 阻断 |

网络请求重传的幂等不是新业务动作的授权。即使已有结果，当前用户失去权限后也不能通过重放旧幂等键继续读取内容。

## 8. 取消与期限的可证明条件

- cancel 受权后先阻止新模型/工具动作；再请求 manager 停止本地进程/connector，外部服务 cancel 仅在其支持时使用。
- 只有收到外部 manager 的受控资源状态并核对进程树，才可把本地执行停止作为已确认事实。
- 如果下游写无法确认是否完成，Run 必须 recovery_required，不能因为 deadline 到了就标 timed_out 并释放所有业务 blocker。
- 凭据/审批到期早于 Run deadline 时，以更早期限限制动作，不在后台偷偷刷新成更广 scope。
- 审批等待可保留已租 cell 但继续计费/计配额；到硬期限必须销毁/隔离，不为等待 UI 无限续租。

## 9. 恢复策略按工具类别区分

| 类别 | 自动重试条件 | 需要核对/拒绝条件 |
|---|---|---|
| 纯数据库 metadata 查询 | 当前权限有效、短 DB 事务无副作用 | 连接身份/数据范围不明 |
| KB 检索/远程只读 | 确认该工具语义只读、截止/预算允许 | 供应商标注不可信，实际可能写/收费 |
| 本地计算 | 无外部凭据/副作用，固定输入，可重新开始并标新 attempt | 依赖不可恢复进程/可变工作区，或已发外部调用 |
| 业务幂等写 | 下游已验证稳定键/有效期/结果查询 | key 超期、参数变更、查询无法核对 |
| 非幂等写 | 明确证明未发送，或人工批准新动作 | 一切发送状态不明 |
| 产物发布 | 固定候选 + 当前权限 + head CAS | 来源变更/扫描失败/旧 writer lease |

工具风险分类是平台审核结果，不只看 MCP annotations。错误处理库不得对全部 POST 自动重试。

## 10. 关键集成验收

本模块至少用 ECASE-01～14 覆盖提交/领取/审批/派发/结果/取消窗口，并保持原 RUNTEST suite。验证的是数据库行、dispatch 次数、下游 effect counter、有效 lease、费用事实与 UI 终态，不是只检查接口返回 200。
