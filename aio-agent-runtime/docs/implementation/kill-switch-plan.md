# 应急禁止开关（GOV-04）：实施计划

> 2026-10-29。承接 GOV-02 Slice C。对应 GOV-04.01–.06、GOVTEST-06、FR-31；不替代 GOV-05、OPS-08 或任何生产 Gate。

## 0. 现状（代码核对）

- 组织策略已有 `aio_organizations.denied_actions` 与 `policy_revision`，由 `policy/service.authorize()` 拒绝（`ORGANIZATION_POLICY_DENIED`）。它是全组织、无期限、无原因、无解除流程的动作黑名单，不能按用户/工具/模型/执行类定位，不会处理已排队或运行中的 Run。
- `resource.status=disabled` 可停用单个工具/模型/Agent 的**新**调用（`RESOURCE_DISABLED`），同样不处理在途 Run，也没有原因/期限/双人解除。
- Worker 每一步都在事务内重读 `current_facts` 并对 session/agent/project 做 `require_resource`（`ExecutionStore.locked`），模型/工具调用前分别 `current_model` / `current_tool`。因此把开关放进 `current_facts`，所有入口自动在权威状态上校验，不依赖缓存通知。
- 仓库里没有 Redis；计划 GOV-04.06 的「Redis 中断」不适用，替代为「无通知、仅靠 PG 权威状态」的用例。
- 没有平台级超级管理员角色，「全局」开关没有可授权的操作者；本增量只做组织内 scope，全局 scope 记为未做。

## 1. 必须成立的语义

1. **scope**：`organization`（全组织）、`user`（某成员发起的工作）、`tool` / `model` / `agent`（某资源）、`execution_class`（`python` / `mcp` / `knowledge` / `skill` 驱动类）。
2. **只由人设置**：只有 `org_admin` 可启用，原因码取封闭词表，附带的自由说明只存摘要；模型、Worker、工具结果无任何入口。
3. **启用即生效**：与 `policy_revision` 自增同事务；之后每个新 Run、模型调用、工具 plan/prepare/consume、审批决定都在自己的事务里读到它并拒绝（`KILL_SWITCH_ACTIVE`）。不依赖进程内缓存或通知。
4. **在途任务**：同一启用动作随后扫一遍本组织未终结的 Run，命中 scope 的转为 `cancel_requested`/`stopping`，由既有生命周期路径收尾：未派发的直接取消并退款，已派发且结果不明的进入 `recovery_required` 并保留 blocker（外部影响不被改判为未发生）。扫的过程失败不影响开关本身：后续每一步仍会被拒。
5. **只读与收尾不受影响**：读取、取消、核对、管理和解除开关本身不被开关拦截。
6. **解除需双人与证据**：解除者必须不同于启用者，需证据引用（只存摘要）。到期只让开关不再拦截**新**动作，绝不重新启动被它取消的历史任务。
7. **全部动作有审计**：启用/解除各一条同事务审计事实，封闭元数据。

## 2. 数据与迁移

`0016_kill_switches`，新表 `aio_kill_switches`（FORCE RLS、组织外键、runtime 只有 SELECT/INSERT 与解除列 UPDATE）：

`org_id, id, scope, target_id?, execution_class?, reason_code, note_digest, activated_by, activated_at, expires_at?, released_by?, released_at?, release_evidence_digest?, revision`

CHECK：scope 封闭集合；`target_id` 与 `execution_class` 恰好按 scope 出现；`released_by <> activated_by`；`expires_at > activated_at`。部分索引 `(org_id) WHERE released_at IS NULL`。

## 3. 证据清单

> 2026-10-29 进度：本节各项在真实 PG 上验证（`tests/platform/test_kill_switches.py` 10 项、`test_kill_switch_contracts.py` 16 项）。

- [x] v16 表、约束、RLS、runtime 最小权限；仅 org_admin 可启用/解除，双人解除，原因码封闭。
  **实际**：member/operator/auditor 启用 403；HTTP 无 CSRF 403、成员 403、管理员 201，列表不含说明正文；表 owner 直接写 `released_by = activated_by` 被 CHECK 拒绝；runtime 对 DELETE、改 scope/activated_by 均 `42501`；重复启用同一目标 409；管理员不能对自己启用 user 开关。
- [x] 各 scope 拒绝新 Run、模型调用、工具 plan/consume、审批决定；只读/取消/核对不受影响；无缓存。
  **实际**：组织开关后新 Run 403 `KILL_SWITCH_ACTIVE`，Run 详情与会话列表正常；工具开关在准入时拒绝（无模型调用）；用 admin 直接写入开关、不跑 sweep，另一个独立 `Database` 实例上的旧 Worker 下一次模型调用被拒；不 sweep 时审批决定被开关本身拒绝且审批仍为 pending。开关在确认访问权之后才判定（单元测试：无权者仍是 `RESOURCE_NOT_FOUND`）。
- [x] 启用后在途 Run：排队取消且预算退回；等待审批取消；已派发结果不明进入 recovery_required 且保留 blocker。
  **实际**：三种状态均有用例；已 consume 的 dispatch 变为 `unknown`、blocker 未解除，旧 Worker 之后的完成回报被拒。
- [x] 到期后新任务可准入，被取消的旧任务不复活；解除后同理。
- [x] 旧 Worker（启用前已领取）下一步被拒；并发启用与 Run 准入不产生「开关已生效但仍准入」。
  **实际**：两线程用 Barrier 同时启用与准入：要么准入被拒，要么准入成功的 Run 已被 sweep 取消。
- [x] 审计、OpenAPI、文档同步。
  **实际**：`kill_switch.activate/release` 封闭元数据，说明与证据只存摘要；OpenAPI 92 条路径，`generated.ts` 已重新生成，`tsc -b` 通过。

**未做**：平台级全局开关（无可授权的平台超级管理员）；向 Manager 主动下发撤销能力/停网络（依靠既有生命周期的 `run.cleanup_requested`）；`execution_class` 在工具调用时的检查只有单元测试，没有真实 PG 驱动夹具；Web 管理界面；事故演练（OPS-08）。
