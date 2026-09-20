# 生命周期回执与 Worker 的 PostgreSQL 锁顺序

## 1. 根因与证据

类别：跨层契约、隐式外键锁与并发覆盖缺口。

真实 PG 回归出现：两个 MCP invocation 均 `succeeded`，Gateway effect 也均为 `done`，但最终 Run 为 `failed / CONTROL_AUTHORIZATION_DENIED`。继续记录受限诊断后，底层明确为 PostgreSQL **40P01 / DeadlockDetected**，失败语句是停止回执中的 `UPDATE aio_runs SET next_event_seq = ...`，并非工具执行失败或“用户没有凭据”。

Worker 使用 `resources → Run` 顺序；旧 `StdioAuthority.authorize` 先锁 Run，再更新 stdio/Run 状态及事件。事件计数是同一事务内对 Run 的再次更新，相关外键检查会访问资源父行。当另一个 Worker 已持有资源锁、正在等待 Run 时，形成反向等待。只看显式的 Run 锁，无法证明随后 UPDATE/外键不会申请其他锁。

新增确定性测试先持有当前 Run 的 resource 行，启动真实停止回执连接，观察其 `pg_stat_activity.wait_event_type=Lock`，然后尝试 Worker 下一步的 `Run FOR UPDATE NOWAIT`：**旧实现稳定失败**，而统一锁序后该锁可立即获得，随后回执完成。

## 2. 修复契约

```text
lock_resource_rows(connection, org_id: UUID, ids: list[UUID]) -> None
  SELECT resource IDs WHERE org_id=:org AND id IN (...) ORDER BY id FOR UPDATE

lock_run_resources(connection, org_id: UUID, run_id: UUID) -> None
  organization FOR SHARE
  -> read immutable Run resource references within the verified organization
  -> lock_resource_rows(Run/Project/Session/Agent)
  does NOT authorize business access or acquire the Run row lock

Run-scoped lifecycle transaction:
  organization FOR SHARE
  -> referenced resources (Run/Project/Session/Agent), stable UUID order
  -> Run FOR UPDATE (or discovery target lock)
  -> exact stdio lease FOR UPDATE
  -> lifecycle mutation + Run revision/event/outbox
```

- `PlatformService._lock_resources` 与 stdio 回调共用同一资源锁原语，避免复制代码后锁序漂移。
- 组织共享锁先于资源锁，兼容现有授权共享锁，并与存储额度/组织变更的排他锁保持一致顺序。
- stdio 回执、`WorkspaceCheckpointStore.mark_acknowledged`、`SandboxCoordinator.observed` 与检查点 GC 复用 `lock_run_resources`。GC 原有组织排他锁不被降级；Run 的四个资源引用在创建后不可变，不将此锁前缀用于修改引用的事务。
- 资源锁函数**不授予权限**，没有伪造用户 Principal。进入回调仍需服务身份、固定 spec/digest、当前节点/代次等原有检查；执行仍需当前业务授权。
- stopped/stop/status 等清理事实可以在组织/用户失权后处理；结构性锁不检查 active/use 权限，不把撤权变成清理死锁。
- 不提高数据库 lock_timeout、不吞掉死锁、不重跑已经发出的业务 RPC，也不把“外部进程确实停了”直接冒充“PG 回执已经提交”。

## 3. 为什么不能只重试或改测试假设

最初聚合错误只显示 `CONTROL_AUTHORIZATION_DENIED`，导致正常授权/资源压力看起来像可能原因；单次重新运行也可能通过。扩充诊断到 operation、SQLSTATE、错误类型和参数隐藏后的 SQL 才定位真正锁环。

正确修复是锁序一致性，而不是延长超时、忽略失败、降低断言或重新调用 tools/call。保留安全诊断，尤其不能记录原始参数、凭据、工具结果或文档内容。

## 4. 验证矩阵

| 条件 | 必须满足 |
|---|---|
| 资源先被另一个控制事务占用 | 回执等待资源，尚未持有 Run 锁 |
| 观察到真实 PG 锁等待后，另一个事务锁 Run | NOWAIT 成功，不形成反向依赖 |
| 资源事务释放 | 回执完成；stdio lease=destroyed、close_reason=requested |
| 组织已经停用 | 相同清理过程仍可完成，但不恢复业务授权 |
| 错误 spec/节点/代次 | 原拒绝路径保持，不能靠锁原语获得权限 |
| 常规两次 MCP 调用后结束 | 已成功工具不因停止事件的锁环被改判整体失败 |

测试：`test_stdio_stop_receipt_locks_resources_before_run_to_avoid_worker_deadlock` 使用实际 Docker 停止事实、真实 PG 双连接和真实锁等待，不通过固定 sleep 猜测并发时序。另重复执行原附件/不同输入策略的完整路径，再执行平台与 HTTP 全量回归。

## 5. 系统性预防

1. 审查所有后台回调、GC/ack 和结束事件：显式锁顺序与隐式 FK 锁都要纳入分析。
2. 针对生命周期写入复用规范锁序，不把只读授权查询误认为已获得了正确写锁。
3. 并发测试观察具体 backend 的真实等待，再执行对端下一步锁操作；避免仅靠循环概率发现死锁。
4. 区分工具效果、进程清理和数据库回执三个事实；一个事实成功不证明其他事实已确认。

```text
Wrong: lock Run first; event/revision updates cannot need any other row
Correct: lock organization/resources in the existing Writer order before Run and lifecycle rows
```

本修复只证明所覆盖的锁环被消除，不替代全部故障、并发容量、HA 和生产安全 Gate。

## 6. 2026-09-13 扩展：检查点 ack 与 compute 停止观察

**触发**：HTTP 审批文件交接曾在 ready 后以 `EXECUTION_FAILED` 终止；该次旧诊断未保留异常类型，不能事后声称已直接取得其 SQLSTATE。继续审查同类生命周期路径，发现检查点 ack 仍采用 Run-first 锁序。

**独立确定性证据**：真正运行计算并导出/销毁旧 Docker cell，故意只丢失 PG ack，保留 `ready / manager_acknowledged=false`；另一个真实 PG 事务先持有 Run 的资源行，启动 ack 后观察具体 backend 进入 `Lock` 等待。旧实现使持锁事务的下一步 `Run FOR UPDATE NOWAIT` 稳定报 `LockNotAvailable`，证明此处同样存在反向依赖，不是单纯测试等待不足。失败证据保存在 `var/verification/workspace-lock-before.xml`。

修复后，ack 在尚未占住 Run 前等待资源；释放对端事务后，确认 ack 并清空已退役 spec。compute 的 `observed(destroyed)` 同样遵守结构性锁序，但**不能代替**检查点 ack、不能清空未经该流程确认的 spec。两种回执都覆盖正常组织和已停用组织。

| Good / Base / Bad | 约束与断言 |
|---|---|
| Good：真实旧 cell 已停止，等待 PG ack | 资源先锁；Run NOWAIT 成功；ack 持久化，spec 清空 |
| Base：组织已停用 | 同样完成结构性清理，不恢复身份、Grant 或业务调用 |
| Base：只观察到 compute 已停止 | 更新自己的清理事实，不伪造另一个流程的 ack |
| Bad：先锁 Run 再写事件/外键 | 确定性测试拒绝该顺序，不增加 lock timeout 或重放动作 |

`tests/lock_fixtures.py::resource_before_run` 统一真实锁等待测试机制；`test_workspace_receipt_lock_order.py` 与原 stdio 测试共用它。新增回执、原 stdio、完整新代次文件恢复和诊断测试组成的 **12 项回归连续两轮通过**，见 `workspace-lock-after-1.xml` / `workspace-lock-after-2.xml`；这不代替后续完整平台/HTTP 回归。

## 7. 合成预览的安全失败证据

`scripts/platform/preview_diagnostics.py` 仅包装有限寿命的合成验证栈。最多记录 100 条、每条最多 12 个项目代码帧，保留异常类型、受限 SQLSTATE/HTTP 状态、固定路由名；不格式化原异常、SQL、源码行、局部变量、凭据、提示词或文件正文。它不吞掉异常、不更改生产 Worker 或 Manager 响应、不拦截取消，也不重试外部操作。

HTTP 验证开始即把报告状态写为 `running`，失败记录当前 verification ID、已通过检查名、失败检查名和异常类型；不得继续留下旧 `passed` 报告充当本次成功。纯测试验证了脱敏、记录上限、取消语义、原 Manager 503 响应和旧成功证据失效。Docker API 异常与 PG 锁环是不同证据，不能只凭聚合错误互相归因。

## 8. 队列领取与控制入口的系统性修复

继续审查发现，不能只让回执遵循资源优先，而保留另一个 Run-first 写入口。真实 PG 已分别复现：

1. `claim_next` 仅在 Run 上 `SKIP LOCKED`；资源或 Job 被占用时仍在持有 Run 后等待。资源用例的 PG CONTEXT 明确显示 `aio_resources ... FOR KEY SHARE`，发生在 `UPDATE aio_runs SET next_event_seq=...`。证明外键锁不能只从 UPDATE 的表名判断。见 `run-lock-before.xml`。
2. `cancel_run` 在事件写入时出现相同反向锁依赖，旧实现的对端 `Run FOR UPDATE NOWAIT` 稳定失败。见 `run-mutation-lock-before.xml`。

### 队列契约

```text
try_lock_run_resources(connection, org_id, run_id) -> bool
  inner SAVEPOINT
    organization FOR SHARE NOWAIT
    immutable Run resource refs, UUID-ordered FOR UPDATE NOWAIT
  missing / SQLSTATE 55P03 -> rollback all prefix locks, return false
  40P01 / connection failure / other errors -> rollback and propagate
  true -> locks retained in caller transaction; not yet a claimed Run

PlatformService.claim_next(org_id, worker_id) -> Run | None
  non-locking bounded scan of at most 50 eligible candidates
  per candidate outer SAVEPOINT:
    try_lock_run_resources
    re-read current state / queue expiry / original Run deadline / not_before
    Run SKIP LOCKED -> Job SKIP LOCKED
    missing or busy -> rollback ALL candidate locks, try next candidate
    success -> generation / attempt / Run / Job / preparing event in one commit
```

多行资源锁使用 `NOWAIT + SAVEPOINT`，而不是对资源集合逐行 `SKIP LOCKED`：后者可能让两个领取者各拿到一部分资源，导致两者都无法取得完整集合。只把该前缀里的 **55P03** 当作“候选繁忙”，不吞掉 **40P01** 或连接故障，不自动重试任何已派发业务动作。返回 None 是本轮没有取得工作，不是任务成功/失败或费用结算。

### 控制与恢复契约

- 取消在 Budget/Run 之前取得核心资源锁，并复核当前取消权限；通用有锁 Run 读取同样在锁后复核读取权限。
- 审批从已获权 Approval 获得 Run 引用；核心资源锁之后复核并锁定 Approval 权限，再进入 Run/Job/Invocation/Approval 状态变更。结构性锁不授予私人 Run/Session 读取能力。
- 心跳、内部状态变化和动作规划使用同一前缀；系统 abort/recovery 在组织被停用时仍可先锁组织再清理。
- 未知效果核对、费用核对在 Budget/Run 之前锁定核心资源并复核当前核对权限；不同人员、当前版本、清理确认与 append-only 费用约束不变。
- 仅当所有候选锁和当前条件都满足才提交一次新 generation。控制事务中仍没有网络调用、安装、用户脚本或归档解析。

### 验证矩阵

| 输入/并发情形 | 必须满足 |
|---|---|
| 首候选的资源 / Run / Job 被占用 | 不反向等待；领取下一合法候选；首候选 generation 仍为 0 |
| 跳过候选但领取事务尚未结束 | 第三连接 NOWAIT 可锁该候选非争用 Session 资源；Job 忙时连旧 Run 锁也释放 |
| 组织排他锁被占用 | 返回 None，不拿资源或修改任务；释放后可领取 |
| 只读扫描后取消 / 推迟 / 排队过期 | 重新检查当前条件并跳过；不领取旧快照 |
| 两个领取者同时看见同一任务 | 至多一份持久 claim；无部分资源集合分裂 |
| 系统停止遇组织锁，含组织已停用 | 先等组织，尚未占有资源；随后安全停止且不重新授权业务 |
| 前缀出现死锁或基础设施错误 | 原错误继续抛出，不伪装为队列空闲；savepoint 释放已持有的锁 |
| 取消 / 状态变化 / 规划 / 审批 | 与 Worker 的资源→Run 顺序一致，原授权与状态约束继续通过 |

测试：`test_run_lock_order.py`、既有真实 PG 竞争/审批/恢复/费用套件，以及完整 Docker/HTTP 文件交接。50 候选是有界调度扫描，不等于已完成多租户公平队列、容量基准、全量故障矩阵或 HA。

并发集成测试也必须遵循队列接口：`run_once()` 返回 None 只表示这一轮未领取，不代表“该用户的任务完成或失败”。两用户 MCP 用例改为真实 `DurableWorker.serve()` 持续处理，并用上游双请求 barrier 强制真实 RPC 重叠；仍严格验证两个 Run 都成功、每个用户仅产生一次自己的 effect、不同凭据/数据不交叉，以及私有读取/绑定拒绝。不是忽略失败的业务结果或重放 RPC。

部署时需暂停接单并排空/更新旧 API、Worker 与回调实例，不能让旧 Run-first 代码长期与新锁序混用。这是应用代码协议变更，不需要新数据库迁移，也不代表混合版本滚动升级已经验收。

真实 HTTP 复验还定位并确定性复现了另一类独立故障：Docker 对象在检查与删除之间已经消失。其所属校验、404 后的独立不存在确认与非 404 错误传播见 [Docker 并发清理契约](platform-docker-cleanup-contract.md)，不能把它与 PG 死锁混为一谈。
