# P2：持久任务、工具网关与沙箱闭环

> 父任务共 37 项：RUN-01～12、SBX-01～14、CAP-01/02/07、GOV-01/02/04/07、OPS-01/02、UI-04/06。全部待实施。这里只允许隔离测试；任何真实业务开放仍等待后续 Gate。

## 1. 进入条件和四条并行工作线

- 身份/资源/PG/SecretRef 的已实现入口通过 G1；新接口继续追加同一授权矩阵。
- 可销毁 Linux 节点、固定运行时、安全 profile 与出网目标已评审。
- 代码执行使用合成数据和测试凭据，禁止借真实财务/管理权限验证“能否执行”。

四条工作线：A 持久 Run/事件/审批；B manager/executor/工作区；C ToolGateway/Manifest/模型/审计/预算；D Run UI/审批 UI。A 与 B 先通过假适配器对齐协议，C 前置约束不能后补，D 使用真实事件语义。

本阶段最终闭环：`登录 → 幂等创建 Run → Worker 领取 → 当前授权 → 专属沙箱 → 工具执行 → 安全发布 → 终态/账本 → 销毁 → 断线后回放`。

## 2. RUN 任务卡

<a id="run-01"></a>

### RUN-01 — 不可伪造的 RunContext 与状态迁移

**位置/契约**：`APP/runtime/context.py,states.py`；RunContext 由 Principal/已获权资源/版本记录构造。

- [ ] **RUN-01.01** 实现 org/actor/project/session/run/attempt/generation/version/deadline/trace 字段并禁止额外授权字段。
- [ ] **RUN-01.02** 定义 queued/preparing/running/waiting_approval/persisting/cancel_requested/终态/待核对迁移表。
- [ ] **RUN-01.03** 对状态更新实施 expected_revision、有效 generation 和 actor/service 权限验证。
- [ ] **RUN-01.04** 分开排队 TTL、Run 总期限、工具 timeout、审批期限，使用权威时间/单调时长，不由客户端延长。
- [ ] **RUN-01.05** 定义终态不再执行新动作、清理状态独立追踪、unknown 不能假装 failed 后重试。
- [ ] **RUN-01.06** 用状态表驱动测试覆盖合法/非法边、乱序通知、重复终态和 stale generation。

**验收**：RUNTEST-03/05/15；服务端绑定无法被模型参数覆盖。**PR/回滚**：类型/状态机独立 PR；状态语义升级需兼容读取旧事件。

<a id="run-02"></a>

### RUN-02 — 幂等创建 Run 与会话顺序

**位置/契约**：`APP/runtime/service.py`、`APP/api/v2/runs.py`；POST 成功表示事务已持久化，不表示任务已执行。

- [ ] **RUN-02.01** 验证 Session/Project/Agent/model/input artifacts 当前权限与 revision，输入 ID 不足以授权。
- [ ] **RUN-02.02** 规范化请求摘要，幂等键按 org+actor+operation 范围保存；同键异体 409。
- [ ] **RUN-02.03** 锁定 Session 顺序和活跃任务规则，首版不允许两个活跃写 Run 混合对话。
- [ ] **RUN-02.04** 在同一事务创建 user message、Run、job、起始事件和预算预留/关联；失败全回滚。
- [ ] **RUN-02.05** 提交后返回 202/run_id/status URL，响应丢失可按幂等重试找回；不让 retry 参数绕开余额检查。
- [ ] **RUN-02.06** 测双击、并发同键/异键、旧 revision、跨项目 artifact、事务中途异常。

**验收**：RUNTEST-01/02/03/06、GOVTEST-01。**PR/回滚**：关闭新提交并保留已提交 Run；不删除记录后让客户端重建。

<a id="run-03"></a>

### RUN-03 — Job 领取、租约、generation 与公平队列

**位置/契约**：`APP/runtime/jobs.py,leases.py,dispatcher.py`、`run_worker.py`；PG 是队列事实，通知可丢。

- [ ] **RUN-03.01** 实现短事务 `SKIP LOCKED` 领取并原子更新 lease_owner/version/expiry，不在事务内等待模型。
- [ ] **RUN-03.02** 配置心跳与租约阈值，使用 DB 权威时间，心跳失败时停止新增副作用并进入受控收敛。
- [ ] **RUN-03.03** 按 org/user/profile/队列类型做准入和公平性，摄取 Job 不能绕过节点总预算。
- [ ] **RUN-03.04** 接管时递增 generation；Gateway/manager/事件/发布均拒绝旧代次，不只是 Worker 本地判断。
- [ ] **RUN-03.05** 定义可重入只读/未开始动作与不可自动重跑动作；失联外部写进入待核对。
- [ ] **RUN-03.06** 实现轮询兜底、not_before、重试退避和最多尝试次数，Redis 通知丢失不丢任务。
- [ ] **RUN-03.07** 测并发领取、停止心跳、旧 Worker 恢复、取消与领取竞争、队列过期。

**验收**：RUNTEST-04/05/18；没有端到端 exactly-once 的虚假承诺。**PR/回滚**：停止领取→排空/核对活跃 lease，不能启动旧版本双 Worker 同时执行。

<a id="run-04"></a>

### RUN-04 — 事务事件、Outbox 与有界内容

**位置/契约**：`APP/runtime/events.py,outbox.py`；event 先可靠写入再对订阅者宣布。

- [ ] **RUN-04.01** 实现 per-run sequence、schema_version、type 与 payload schema，序号不靠进程内计数器。
- [ ] **RUN-04.02** 状态/游标/必要事件同事务提交；大正文存受权引用，审计只记最小事实。
- [ ] **RUN-04.03** 合并模型 token 为有界增量事件，限制 chunk/队列/总量，不每 token 无界写事务。
- [ ] **RUN-04.04** 实现 Outbox lease、投递、消费者去重、重试和 dead-letter/告警，避免重复扣费或重复取消。
- [ ] **RUN-04.05** 定义 event snapshot、归档与保留策略；缓存淘汰不删除权威 Run 和费用事实。
- [ ] **RUN-04.06** 测提交前/后崩溃、事件重复、旧 generation 写事件、慢持久化与 Outbox 失联。

**验收**：RUNTEST-06/08/16/18；事件可追溯且无 Secret。**PR/回滚**：兼容 schema，关闭推送可临时改查询，不回退纯内存事件。

<a id="run-05"></a>

### RUN-05 — SSE 订阅、回放和撤权

**位置/契约**：`APP/api/v2/events.py`、`APP/runtime/subscriptions.py`；GET 订阅不创建或重跑任务。

- [ ] **RUN-05.01** 每次订阅验证 Run/Session 可见性，绑定 Principal，禁止仅凭 run_id 获得内容。
- [ ] **RUN-05.02** 定义 Last-Event-ID/after_seq 的一致规则，冲突/未来/错误 Run 游标返回稳定错误。
- [ ] **RUN-05.03** 先回放持久事件再跟随新事件，避免历史和实时切换出现丢帧窗口。
- [ ] **RUN-05.04** 实现有界订阅缓冲、心跳、慢消费者断开、cursor 过期后的授权 snapshot 恢复。
- [ ] **RUN-05.05** 监听 auth/ACL revision 变化并在发送前维持有效授权，停用/过期后停止敏感输出。
- [ ] **RUN-05.06** 浏览器断开只取消订阅，不隐式取消 Run；取消通过独立 API。
- [ ] **RUN-05.07** 测重连、重复帧、API 重启、终态查询、慢客户端和撤权期间回放。

**验收**：RUNTEST-07/08、AUTH-09、UITEST-03。**PR/回滚**：可降级获权状态轮询；不能改为匿名 SSE 或自动重新提交任务。

<a id="run-06"></a>

### RUN-06 — EngineAdapter 与 LocalHarnessAdapter 边界

**位置/契约**：`APP/runtime/engines/base.py,local_harness.py`；适配器声明能力，不自带平台权限绕过。

- [ ] **RUN-06.01** 定义 validate/start/events/cancel/checkpoint/close 及能力集合，resume 非支持时明确拒绝。
- [ ] **RUN-06.02** 将现有 ModelClient/runner 与 HTTP 解耦，输入消息快照与 RunContext，不读写全局 Session 单例。
- [ ] **RUN-06.03** 建 fake adapter 固定产生文本、工具、审批、失败、取消事件，供 Worker/FE 独立开发。
- [ ] **RUN-06.04** 定义引擎事件到平台事件映射、完整回合提交边界、usage unknown 和 finish_reason。
- [ ] **RUN-06.05** 把模型/工具/秘密访问全部注入受控服务，adapter 不自行构造不受控 endpoint 或 subprocess。
- [ ] **RUN-06.06** 测 unsupported capability、提前结束、异常清理、取消与重复 close。

**验收**：同一 fake 流可用于 API/Worker/UI；引擎选择不更改 org/权限上限。**PR/回滚**：适配器开关关闭，不直接透传旧 runner 的 HTTP 路径。

<a id="run-07"></a>

### RUN-07 — AgentRunner 持久游标与工具调用重构

**位置/契约**：当前 `APP/agent.py`、`runtime/checkpoints.py`、ToolGateway 注入。

- [ ] **RUN-07.01** 移除全局 `self.tools` 中带身份的 client 绑定，按 Run 获取固定 Manifest 和权限上限。
- [ ] **RUN-07.02** 完整模型回合在发工具前保存 assistant/tool_calls/step/round 游标和来源，半截输出不当完成回合。
- [ ] **RUN-07.03** 按 logical_call_id 记录每个工具意图/结果，恢复时读取已保存调用，不重新问模型生成另一份写参数。
- [ ] **RUN-07.04** 工具结果、下一游标、usage/event 原子提交；大内容存引用，入模摘要有 token/字节预算。
- [ ] **RUN-07.05** waiting_approval 存 durable checkpoint，不依赖 HTTP Future；依赖进程内存的恢复标记为不可透明重入。
- [ ] **RUN-07.06** 每轮校验取消/期限/当前权限/预算；模型异常保留实际费用与不完整输出状态。
- [ ] **RUN-07.07** 在安全边界前后注入崩溃，验证不重复外部调用，旧 Session/工具回归不串上下文。

**验收**：RUNTEST-09/14/16、CAPTEST-02；当前 single 行为可复现且变为可解释的持久任务。**PR/回滚**：按 adapter 特性灰度，未知 checkpoint 版本拒绝执行而非从头重跑。

<a id="run-08"></a>

### RUN-08 — 持久审批与 ActionSpec 冻结

**位置/契约**：`APP/runtime/approvals.py,actions.py`、`APP/api/v2/approvals.py`；Approval 是具体动作授权，不是未来通行证。

- [ ] **RUN-08.01** 规范化参数并计算 action_digest，覆盖 tool_version、目标资源、连接身份/版本、脚本/输入/环境关键摘要。
- [ ] **RUN-08.02** 持久创建 pending/期限/可审批策略/最小业务摘要，写事件后释放长事务。
- [ ] **RUN-08.03** 决定 API 校验批准人、当前 Run、digest/revision、有效期与职责分离，使用 CAS 防竞争。
- [ ] **RUN-08.04** 执行前重新检查权限、动作摘要、取消、Secret revision，参数或脚本改变生成新 Approval。
- [ ] **RUN-08.05** 进程重启后根据 checkpoint 恢复等待；环境不可重建时使执行授权失效，保留原审批事实。
- [ ] **RUN-08.06** 实现拒绝、到期、禁用、取消和孤立审批清理，默认拒绝不以网页连接存在为依据。
- [ ] **RUN-08.07** 测双决定、过期、审批后改代码/输入、撤权、同一摘要跨 Run 重放与非授权人批准。

**验收**：RUNTEST-09～13、GOVTEST-05。**PR/回滚**：关闭新高风险调用，已 pending 状态明确保留/失效；不回退内存 Future 默认放行。

<a id="run-09"></a>

### RUN-09 — 取消、硬 deadline、未知结果与人工核对

**位置/契约**：`APP/runtime/cancellation.py,recovery.py`、cancel/reconcile API；取消不能等同撤销业务操作。

- [ ] **RUN-09.01** cancel 请求幂等更新状态，先禁止新模型/工具调用，再通知 Worker/manager 停止当前执行。
- [ ] **RUN-09.02** Worker soft deadline 与 manager 独立硬期限联动，控制进程崩溃仍能收回沙箱。
- [ ] **RUN-09.03** 分类 queued/approval/local execution/remote write/persisting 的停止策略，避免取消时误删已发布产物。
- [ ] **RUN-09.04** 对远端请求响应丢失记录 outcome_unknown，禁止普通 retry 直接重发；支持下游幂等键与结果查询。
- [ ] **RUN-09.05** 定义 reconcile 的证据、权限和可终结状态，人工不能随便把失败改成成功而不留证据。
- [ ] **RUN-09.06** 旧代次、清理失败、manager 不可达进入隔离/待核对，前端显示停止处理中而不是即刻成功取消。
- [ ] **RUN-09.07** 测各边界取消、外部超时成功、持久化失败、Worker/节点失联与重复核对。

**验收**：RUNTEST-14/15/16、SBXTEST-10/19。**PR/回滚**：保留未知事实，禁重试和新执行；恢复应用版本不回放副作用。

<a id="run-10"></a>

### RUN-10 — 最小预算准入与用量事实

**位置/契约**：`APP/billing/admission.py,reservations.py`、ModelClient usage 边界；完整财务对账在 GOV-03。

> 实现现状（2026-09-16 核查）：组织 / 部门共享预算部分已落到代码，实际路径是 `APP/billing/budgets.py`（不是本卡原先建议的 `admission.py,reservations.py`），配套迁移 `MIG/versions/0013_shared_budgets.py` 与 `HTEST/platform/{test_shared_budgets,test_shared_budget_contracts,test_shared_budget_migration,test_budget_lock_order}.py`。逐项子任务范围、剩余工作与 G2/G5 门禁状态不因此改变；完整范围见 [实现进度](../../../implementation/README.md)。

- [ ] **RUN-10.01** 定义 org/department/user/Run 层级硬上限、计价单位、价格版本和估算/真实/unknown 标记。
- [ ] **RUN-10.02** 事务预留任务费用，锁住相关预算行避免并发透支；创建失败原子释放。
- [ ] **RUN-10.03** 每次模型/embedding/重排计费动作前检查剩余预算和取消/截止，不仅限制 Agent 轮数。
- [ ] **RUN-10.04** 按稳定 call/request ID 记账，失败但已调用也保留费用可能性，不把缺 usage 当 0。
- [ ] **RUN-10.05** 完成/取消/失败的预留结算幂等，unknown 先保守占额并进入对账，不无限免费重试。
- [ ] **RUN-10.06** 测最后额度并发、重复 usage、上游错误、planner/summary 计费与 stale Worker 上报。

**验收**：GOVTEST-01/02，真实付费模型开放前最小预算闭环可用。**PR/回滚**：停止新计费调用、保留账本，不回退显示免费或忽略预留。

<a id="run-11"></a>

### RUN-11 — Team 编排统一 Run 与权限

**位置/契约**：当前 `APP/orchestrator.py`、run_steps；team 是同任务步骤，不是多用户共享机制。

- [ ] **RUN-11.01** 将计划、步骤、汇总关联同 run_id，每步保存序号、状态和输入输出引用。
- [ ] **RUN-11.02** Planner 只能使用 AgentVersion 允许的模型与能力，步骤不得自行扩大 Manifest 或凭据 scope。
- [ ] **RUN-11.03** 同一 Run 的本地步骤共享合法沙箱/工作副本，但同 Session 的其他 Run 不共享可变环境。
- [ ] **RUN-11.04** 步骤完成保存 checkpoint，失败/拒绝/超时明确传给汇总，不能把未执行步骤描述为完成。
- [ ] **RUN-11.05** 统一预算和取消；汇总调用也记账，不在任务超时后继续额外请求模型。
- [ ] **RUN-11.06** 测步骤间产物、审批、取消、错误汇总、重启游标与工具命名冲突。

**验收**：RUNTEST-17，旧 team 基础业务语义保留但权限不变宽。**PR/回滚**：可只开放 single，team 关闭不影响已完成数据。

<a id="run-12"></a>

### RUN-12 — Run 故障恢复集成门禁

**位置/契约**：`HTEST/integration/test_run_lifecycle.py,test_recovery.py`、假模型/可核对写服务。

- [ ] **RUN-12.01** 以状态图生成正常与非法迁移用例，固定消息/工具/费用事实期望。
- [ ] **RUN-12.02** 在提交、领取、模型回合、调用意图、审批、结果、终态各点注入退出/连接断开。
- [ ] **RUN-12.03** 用两个 Worker 实测租约接管、旧代次拒绝、重复事件与项目 CAS。
- [ ] **RUN-12.04** 测 API 与浏览器独立生命周期，页面重连不会重新执行任务。
- [ ] **RUN-12.05** 验证 unknown 必须核对，恢复不能重发不可幂等写，计费不能因错误丢失。
- [ ] **RUN-12.06** 形成 G3 证据：每类动作可重入/不可恢复/需核对的矩阵和剩余限制。

**验收**：RUNTEST-01～18 适用场景全部执行，不能只测 happy path。**PR/回滚**：门禁失败关闭相应执行/写能力，保留测试以防回归。
## 3. SBX 执行隔离任务卡

<a id="sbx-01"></a>

### SBX-01 — 节点安全与运行时能力基线

**位置/契约**：`INFRA/platform/execution-node/`；主机管理权限与业务代码分开。

- [ ] **SBX-01.01** 固定 Linux/kernel/runtime 版本及升级基线，确认 cgroup v2/namespace/安全模块实际可用。
- [ ] **SBX-01.02** 分控制/执行网络和账号，禁主机管理端口暴露给沙箱，执行节点不挂生产共享目录。
- [ ] **SBX-01.03** 设置最小管理代理身份、镜像仓库权限、审计与证书路径，普通 Web/Worker 无 Docker Socket。
- [ ] **SBX-01.04** 配置磁盘字节/inode 配额和节点保留水位，验证 rootless/userns 场景的 cgroup/网络限制是否真生效。
- [ ] **SBX-01.05** 确定时钟同步、node health、排空和失联处理；节点重启后先对账再接受新 Run。
- [ ] **SBX-01.06** 输出运行时 capability 报告，不支持硬限制的 backend 不作为任意代码执行节点。

**验收**：SBXTEST-05/09/14、OPSTEST-02。**PR/回滚**：以新节点/镜像替换，先排空；不取消防护恢复兼容。

<a id="sbx-02"></a>

### SBX-02 — Sandbox Manager 窄接口与幂等绑定

**位置/契约**：`SM/api.py,service.py,backends/`；内部 ensure/status/stop/destroy，不提供任意 host exec。

- [ ] **SBX-02.01** 定义不可由用户修改的 SandboxSpec：org/run/generation/profile/image digest/workspace lease/deadline。
- [ ] **SBX-02.02** 为 manager 请求实施服务身份验证、scope、replay/expiry 检查；客户端不能指定任意挂载/设备/capability。
- [ ] **SBX-02.03** 以 run+generation+profile 幂等创建，记录 backend resource ID 与标签，响应丢失可找回实例。
- [ ] **SBX-02.04** DockerBackend 使用固定安全模板和镜像白名单，参数解析不转成用户可控 shell 字符串。
- [ ] **SBX-02.05** 所有 status/exec/stop/destroy 对照当前 lease/generation，旧 Worker 不得管理新实例。
- [ ] **SBX-02.06** 处理创建部分成功、挂载失败、镜像缺失、健康检查超时，补偿回收精确资源而非模糊路径。
- [ ] **SBX-02.07** 测重入、重复创建、配置冲突、未授权 service、未知资源和 replay。

**验收**：SBXTEST-18/19、RUNTEST-05；坏输入不会触发任意宿主操作。**PR/回滚**：停新分配并继续对账已有资源，不遗弃孤儿。

<a id="sbx-03"></a>

### SBX-03 — 固定基础镜像和依赖层

**位置/契约**：`INFRA/images/base,standard,parser/`；镜像 digest 固定且运行目录只读。

- [ ] **SBX-03.01** 从 FND-06 准入清单确定最少系统/语言依赖，使用固定基础镜像和可复现锁定方式。
- [ ] **SBX-03.02** 创建非 root runner、只读 `/opt/runtime` 与 Skill 挂载点，禁止 chown 整个运行时给用户代码。
- [ ] **SBX-03.03** 划分 workspace/HOME/tmp/output 可写受限卷；不把 `.env`、浏览器 Cookie、开发缓存打进镜像。
- [ ] **SBX-03.04** 预装批准的分析/parser 包和字体；系统更新仅在 CI 构建，不由 Run 安装。
- [ ] **SBX-03.05** 生成 SBOM、镜像 digest、依赖版本和扫描记录，交 OPS-01 做签名准入。
- [ ] **SBX-03.06** 在 read-only root/cap_drop/非 root 条件跑 smoke，缺写目录显式补 profile 不放开整根。

**验收**：SBXTEST-05/16、OPSTEST-04。**PR/回滚**：固定上一 digest，对新 Run 生效；运行中任务不偷偷换镜像。

<a id="sbx-04"></a>

### SBX-04 — 私有执行协议与进程生命周期

**位置/契约**：`EX/protocol.py,processes.py,files.py`；manager 通过固定私有通道调用。

- [ ] **SBX-04.01** 定义 execution_id、run/generation、程序/参数、固定 cwd、deadline、stdin/output 限制与退出原因。
- [ ] **SBX-04.02** 实现进程组/cgroup 范围启动和停止，所有子孙进程跟随执行单元，不能只 kill 外层 Shell。
- [ ] **SBX-04.03** stdout/stderr 流式有界读取，限制 chunk、缓冲、累计日志和持续洪水，处理无换行/二进制/UTF-8。
- [ ] **SBX-04.04** 用户 stdout 与可信控制帧分通道/严格封装，打印伪造 JSON 不能冒充 approval/result/control 消息。
- [ ] **SBX-04.05** 文件操作限定获权目录，用安全句柄/no-follow/等效机制防路径和 TOCTOU，执行端不接任意宿主路径。
- [ ] **SBX-04.06** 处理启动失败、取消、timeout、OOM、runner 被杀、控制通道断开；最终状态由外部 manager 核对。
- [ ] **SBX-04.07** 协议兼容与模糊/畸形输入测试，超大代码/stdin/结果拒绝而不耗尽控制服务内存。

**验收**：SBXTEST-04/07/08/10/11/12；语言运行时不是独立安全边界。**PR/回滚**：撤销该 executor profile，不在 Harness 宿主替代运行。

<a id="sbx-05"></a>

### SBX-05 — Python/Node 适配与私有依赖

**位置/契约**：`EX/python_exec.py,node_exec.py`、现有 `services/node-repl` 适配；Node vm 仅在 OS 沙箱内部使用。

- [ ] **SBX-05.01** Python 执行统一走 executor，保留输出/错误/超时语义，移除控制服务直接 subprocess 路径。
- [ ] **SBX-05.02** Node REPL session ID 从 binding 生成，模型不能指定别人的 session 或任意 cwd。
- [ ] **SBX-05.03** 每 Run 私有 HOME、`.venv`、node_modules、REPL 状态；依赖安装同受网络/时间/CPU/磁盘限制。
- [ ] **SBX-05.04** 配置子进程 env allowlist，禁控制 Secret；明确 JS process/require 不提供 OS 安全保证。
- [ ] **SBX-05.05** 定义 session reset/崩溃/timeout 的 checkpoint 语义，内存丢失不能伪装已恢复。
- [ ] **SBX-05.06** 测两个并发 Run 的变量、文件、依赖、HOME 与 env，以及旧 session_id 的调用拒绝。

**验收**：SBXTEST-01/03/04/10/16；同 Run 可保持状态，不跨 Run 复用可写环境。**PR/回滚**：分别关闭 Python/Node 能力，不回退共享 REPL。

<a id="sbx-06"></a>

### SBX-06 — 浏览器执行与 Profile 隔离

**位置/契约**：`EX/browser.py`、browser 镜像；当前 `APP/clients/browser.py` 在平台模式不可直接启动 CLI。

- [ ] **SBX-06.01** 选定浏览器/驱动版本和镜像，验证非 root、seccomp/namespace 与共享内存兼容。
- [ ] **SBX-06.02** Profile、Cookie、下载、缓存、会话控制句柄按 Run 隔离，禁止默认用户浏览器目录挂载。
- [ ] **SBX-06.03** 将 open/snapshot/download 等映射到获权 executor，URL/重定向/子资源同时受出口策略。
- [ ] **SBX-06.04** 明确登录凭据/交互授权方式，不把公司所有网站账号交给同一浏览器实例。
- [ ] **SBX-06.05** 对截图和下载产物应用数据来源/权限/扫描政策，截图可能含 PII，不原样写通用日志。
- [ ] **SBX-06.06** 停止整个浏览器进程树并销毁 Profile；测 crash、下载未完成、页面恶意脚本和 cookie 残留。
- [ ] **SBX-06.07** 若需取消浏览器自身安全保护才能运行，暂停该 profile 评审或更换隔离方案，不作为默认修复。

**验收**：SBXTEST-04/10/14/20、UITEST-06。**PR/回滚**：禁 browser profile，保留已授权产物；不在控制节点调用旧 CLI。

<a id="sbx-07"></a>

### SBX-07 — CPU/内存/PID/磁盘/并发准入

**位置/契约**：`SM/profiles.py,admission.py`、节点卷/quota 配置；profile 声明必须映射真实硬限制。

- [ ] **SBX-07.01** 固定 parser/standard/browser/heavy 资源规格与启用权限，用户不能任意上调 limits。
- [ ] **SBX-07.02** 设置 cgroup CPU/memory/pids，限制所有可写卷/tmpfs/日志，验证 tmpfs 计入内存。
- [ ] **SBX-07.03** 实现字节/inode 硬配额或经验证等效后端，named volume/定期清理不等于硬限额。
- [ ] **SBX-07.04** 按节点保留余量、profile 峰值和 org/user 并发做原子准入，解析池也计算在总量内。
- [ ] **SBX-07.05** 配置磁盘/内存/PID 水位和排空，新任务排队或拒绝，不能等根盘满再处理。
- [ ] **SBX-07.06** 处理资源预留但创建失败、租约过期、重复释放与节点失联，保持调度账本和实际资源可对账。
- [ ] **SBX-07.07** 测受控 CPU/OOM/PID/输出/磁盘压力及公平排队，确认只影响目标任务。

**验收**：SBXTEST-06/07/08/09、OPSTEST-02；对不支持的限制诚实拒绝 profile。**PR/回滚**：降并发/关 profile，不降低隔离要求。

<a id="sbx-08"></a>

### SBX-08 — 默认拒绝网络与可信出口

**位置/契约**：执行节点网络策略、`SM/network_profiles.py`、受控 egress/DNS；应用 proxy env 不是唯一防线。

- [ ] **SBX-08.01** 明确 sandbox→管理面/其他 sandbox/metadata/数据库全部拒绝，只允许必要限定代理。
- [ ] **SBX-08.02** 对 DNS、IPv4/IPv6、端口、loopback/link-local、内网管理网段定义同一策略。
- [ ] **SBX-08.03** 包下载/业务访问按 profile/连接器允许端点；远端 IP 校验覆盖实际连接与每次重定向。
- [ ] **SBX-08.04** 内网业务经专用代理或精确批准连接，不能开放整个公司网段方便测试。
- [ ] **SBX-08.05** 对 MCP resource link、浏览器子资源、parser 外链、管理员测试连接统一出口，不留旁路。
- [ ] **SBX-08.06** 记录最小目标/决策/调用关联，避免 URL query/token 泄漏；允许域名不代表允许任意数据外发。
- [ ] **SBX-08.07** 测 DNS rebinding、IPv6 表示、重定向、直连绕过 proxy env、跨沙箱和控制网访问。

**验收**：SBXTEST-14/15、MCPTEST-04；真实节点策略测试而非只校验字符串。**PR/回滚**：退回更窄白名单/无网 profile，禁止临时全放通。

<a id="sbx-09"></a>

### SBX-09 — 工作区版本、单写者与 CAS 发布

**位置/契约**：`APP/workspaces/versions.py,leases.py`、`SM/workspace.py`；持久项目数据与 Run 私有副本分开。

- [ ] **SBX-09.01** 定义不可变版本 manifest/hash、head pointer、数据来源和项目配额。
- [ ] **SBX-09.02** 原子获得 project/workspace 写 lease，绑定 run/generation/base_version；只读任务读提交版本。
- [ ] **SBX-09.03** 从固定版本构建 Run 工作副本，精确挂载当前获权输入；不挂全用户父目录。
- [ ] **SBX-09.04** 公共 Skill/输入只读、用户输出独立；排除私人凭据/依赖缓存被自动变成项目数据。
- [ ] **SBX-09.05** 发布使用 expected head_version CAS，旧 lease/权限变化/冲突拒绝覆盖，保留受限候选结果。
- [ ] **SBX-09.06** 租约续期/取消/失联与 manager generation 一致，不能两个沙箱同时写同一已发布目录。
- [ ] **SBX-09.07** 测同项目双 Run、同名跨用户文件、撤权、快照缺失、旧代次恢复和版本冲突。

**验收**：SBXTEST-01/11/12/17；数据持久化不是把容器长期保留。**PR/回滚**：保留旧版本指针和候选，不盲目删除/覆盖目录。

<a id="sbx-10"></a>

### SBX-10 — 安全产物收集、扫描与原子发布

**位置/契约**：`APP/workspaces/artifacts.py`、受控 collector、对象存储；不相信沙箱自报路径/hash/大小。

- [ ] **SBX-10.01** 执行停止/冻结后收集候选，避免用户代码在检查与读取之间替换文件。
- [ ] **SBX-10.02** 安全遍历获权卷，拒绝逃逸链接、设备/特殊文件、超数量/大小/层级产物。
- [ ] **SBX-10.03** 检测类型/hash/来源标签，将候选写到不可变 quarantine 对象，不直接给下载链接。
- [ ] **SBX-10.04** 扫描/预览在隔离 parser，HTML/SVG/Office 不在平台同域执行；结果发布前明确状态。
- [ ] **SBX-10.05** PG 事务创建 Artifact/WorkspaceVersion、ACL、来源与 head CAS，失败时对象是可清理孤儿而非公开半结果。
- [ ] **SBX-10.06** 下载/分享再次授权，敏感即时撤回走代理；长期 Secret、Cookie、`.venv` 不默认发布。
- [ ] **SBX-10.07** 测产物 race、对象存储失败、扫描失败、错误 MIME、重复发布与分享来源限制。

**验收**：SBXTEST-11/12/13、RUNTEST-16、GOVTEST-11。**PR/回滚**：停止发布但保留受控候选，不能把未扫描文件公开来“恢复下载”。

<a id="sbx-11"></a>

### SBX-11 — 取消、TTL、Reaper 和节点隔离

**位置/契约**：`SM/reconciler.py,lifecycle.py`；权威 lease 与实际资源双向对账。

- [ ] **SBX-11.01** 实现 requested/provisioning/ready/leased/destroying/destroyed/failed/quarantined 状态及幂等停止接口。
- [ ] **SBX-11.02** manager 硬 deadline 独立于 Worker/浏览器连接，超时撤销执行能力并停止全部进程。
- [ ] **SBX-11.03** 扫描 DB 有实例无、实例有有效 lease 无、Run 已终态仍有卷/进程的差异。
- [ ] **SBX-11.04** 按精确 backend ID/generation 销毁，校验挂载和目标归属；无确认不得标 destroyed。
- [ ] **SBX-11.05** 重试超过阈值隔离节点、停止新调度并告警；失败容器不能清空目录后回池。
- [ ] **SBX-11.06** 区分短期隔离保留用于排障与正常销毁，保留必须撤网/撤凭据/到期清理。
- [ ] **SBX-11.07** 测响应丢失、manager 重启、节点重启、Worker 离线、重复 stop/destroy 与孤儿卷。

**验收**：SBXTEST-18/19/20、OPSTEST-03；不能让资源逐日累积。**PR/回滚**：保留独立清理代理职责，服务回退时仍可收敛现有资源。

<a id="sbx-12"></a>

### SBX-12 — Run capability 与最小凭据注入

**位置/契约**：`SM/identity.py`、`APP/execution/capabilities.py`；capability 限定 org/run/generation/工具/资源/期限。

- [ ] **SBX-12.01** 建立 capability 签发/校验、issuer/aud/expiry/jti 与在线 lease/撤权版本检查。
- [ ] **SBX-12.02** 沙箱默认不含模型/数据库/云管理长期 Key；远程能力优先由受控 Gateway 代调用。
- [ ] **SBX-12.03** stdio MCP 必须拿凭据时仅注入其最小短期 scope，承认该进程及同单元代码可读，不假装 env 是秘密隔离。
- [ ] **SBX-12.04** 固定注入方式/可读身份/文件权限/生命周期，禁止 Secret 写进镜像、workspace、控制帧和诊断包。
- [ ] **SBX-12.05** Run 结束/用户停用/Secret 轮换后撤销 capability 和连接池，旧签名未过期也不能继续获权。
- [ ] **SBX-12.06** 测 token 跨 Run 重放、错误 aud、旧 generation、过期、管理网访问和日志脱敏。

**验收**：AUTH-06/09、SBXTEST-03、GOVTEST-04。**PR/回滚**：能力读取失败即拒绝，不下发全局 Token 应急。

<a id="sbx-13"></a>

### SBX-13 — 真实执行隔离与资源滥用验收

**位置/契约**：`services/sandbox-manager/tests/integration/`、专用 Linux runner；合成数据与无害目标。

- [ ] **SBX-13.01** 固定实际镜像/内核/网络/profile 和受控测试夹具，记录宿主保护文件前后 hash。
- [ ] **SBX-13.02** 两用户并发验证文件、变量、依赖、HOME、Cookie、网络和 Secret 不共享。
- [ ] **SBX-13.03** 逐执行器跑 Python/Node/browser/parser/stdio 路径；未实现的执行器保持关闭并列出后补门禁。
- [ ] **SBX-13.04** 在外层配额内测试 CPU/OOM/PID/磁盘/inode/输出压力和进程树停止，避免伤害测试节点外资源。
- [ ] **SBX-13.05** 测路径/race/产物/网络绕过、模板特权参数拒绝和控制进程无直接执行旁路。
- [ ] **SBX-13.06** 注入创建/销毁/manager/节点故障，对账容器、卷、进程、凭据和账本一致性。
- [ ] **SBX-13.07** 输出 G2 的按 executor/profile 证据和不支持项，不把 Python 通过扩展成“所有执行器安全”。

**验收**：SBXTEST-01～20 的适用项目全部通过；新增 stdio/parser adapter 后重跑差量。**PR/回滚**：未通过 profile 不能注册或被直接 API 调用。

<a id="sbx-14"></a>

### SBX-14 — 更强隔离运行时准入

**位置/契约**：`SM/backends/` 与安全域选择 ADR；不是要求第一版同时实现所有候选。

- [ ] **SBX-14.01** 根据 G0 的代码信任与数据等级选择一个优先候选（增强容器/微 VM 等），固定威胁模型和目标。
- [ ] **SBX-14.02** 确认主机虚拟化/namespace/文件/网络与磁盘限制是否支持，不为兼容取消核心防护。
- [ ] **SBX-14.03** 在同一 SandboxBackend 契约适配 create/exec/stop/destroy/status，不让业务代码依赖运行时私有参数。
- [ ] **SBX-14.04** 用真实依赖验证 pandas/原生包、浏览器、Office/parser、stdio MCP 和资源清理。
- [ ] **SBX-14.05** 对比启动、资源、吞吐、剩余风险和运维成本，重跑对应 G2 suite。
- [ ] **SBX-14.06** 给每个信任级别出允许 profile/禁止能力矩阵；未通过可保留可信模板试点，任意来源代码继续关闭。

**验收**：有 go/no-go 和可复现证据，而非根据产品名称宣称更安全。**PR/回滚**：高风险任务不能自动降级到更弱 backend，必须拒绝/排队。
## 4. CAP：不能后补的网关与能力上限

<a id="cap-01"></a>

### CAP-01 — 统一 ToolGateway 与执行路由

**位置/契约**：`APP/tools/gateway.py`、当前 `tools/registry.py`；`invoke(context, alias, args, logical_call_id)` 是所有工具入口。

- [ ] **CAP-01.01** Registry 只注册固定 schema/无身份 handler 定义，不保留跨用户可变 client 或任意 getattr/import 执行能力。
- [ ] **CAP-01.02** 校验 alias→版本映射、参数 schema/额外字段/大小和 Run 当前状态，模型不能选择凭据或沙箱 URL。
- [ ] **CAP-01.03** 每次调用求当前权限∩Manifest 上限∩连接资源 scope∩数据/预算策略，隐藏工具之外还要真正拒绝直接调用。
- [ ] **CAP-01.04** 根据风险接 RUN-08 审批与稳定 ActionSpec，执行前持久意图；低风险沙箱内计算按策略自动允许。
- [ ] **CAP-01.05** 将本地执行路由 manager，远程 MCP/KB 路由各受控 adapter，调用方不自行开命令进程。
- [ ] **CAP-01.06** 统一结果/错误/截断/费用/审计，重试必须按工具幂等和外部可核对能力判断。
- [ ] **CAP-01.07** 从 API、team、MCP Server、管理测试、直接调用分别验证未授权请求被拒。

**验收**：CAPTEST-02/06/09/10、RUNTEST-14；审批 hook 未接入时高风险默认拒绝。**PR/回滚**：关闭特定工具；不能恢复旧 client 旁路。

<a id="cap-02"></a>

### CAP-02 — 能力版本、ManifestSnapshot 和命名映射

**位置/契约**：`APP/capabilities/registry.py,resolver.py,manifests.py`；P2 先内置种子能力，P3 完整导入/发布。

- [ ] **CAP-02.01** 定义 capability/version/status/scope/required dependencies/schema_digest，与 resources/grants 关联。
- [ ] **CAP-02.02** 解析用户、项目、AgentVersion、组织数据策略允许集，验证依赖版本和启用状态。
- [ ] **CAP-02.03** 为每个 Run 保存固定版本、alias 映射、schema/策略摘要，避免同名部门工具误指连接。
- [ ] **CAP-02.04** 提供授权目录分页/搜索，长目录按需加载；不能先把全公司名称给模型再过滤。
- [ ] **CAP-02.05** Snapshot 是权限上限不是永久通行证，撤权/禁用后 Gateway 仍拒绝下一调用。
- [ ] **CAP-02.06** 建只读测试种子 Agent/内置文件计算能力，供 P2 闭环，不开放管理员任意配置执行命令。
- [ ] **CAP-02.07** 测命名冲突、旧版本、依赖缺失、未知工具、scope 改变与权限缓存失效。

**验收**：CAPTEST-01/02/03/04/08；数据约束与 Run version refs 一致。**PR/回滚**：指针回滚影响新 Run，禁止在执行中换版本。

<a id="cap-07"></a>

### CAP-07 — 封闭所有 legacy 和调试旁路

**位置/契约**：当前 `APP/main.py`、`mcp_server.py`、`clients/browser.py`、Sandbox HTTP/WS 暴露配置。

- [ ] **CAP-07.01** 逐项列出 `/api/chat*`、`/api/files*`、MCP Server、Shell WS、浏览器 CLI、Node 和管理员测试路径。
- [ ] **CAP-07.02** 生产只注册 v2 或将兼容入口翻译到同一 Principal/Run/Gateway，不保留全局 Token 旁路。
- [ ] **CAP-07.03** 封闭原始执行端口对员工/公网访问，反代和网络同时落实，不仅前端移除按钮。
- [ ] **CAP-07.04** 配置读取在安全校验之后，阻止旧 provider `!shell`、任意 baseUrl 被用户配置触发。
- [ ] **CAP-07.05** 管理测试/debug 也创建获权测试 Run，不能以管理员身份共享执行用户脚本。
- [ ] **CAP-07.06** 通过路由枚举、静态调用点审查和直接 HTTP/WS/MCP 请求证明每条入口关闭或受控。

**验收**：CAPTEST-09、SBXTEST-04、MCPTEST-12、OPSTEST-01。**PR/回滚**：开发模式可保留原行为，生产回滚不重新开放旧端口。

## 5. GOV：前置数据、审计、模型与紧急禁止

<a id="gov-01"></a>

### GOV-01 — 数据分级、来源和外发策略

**位置/契约**：`APP/policy/data.py`、provenance/derived policy；模型、工具和 Artifact 共用同一来源约束。

- [ ] **GOV-01.01** 固定数据级别及允许模型/embedding/reranker/连接器端点，未知级别按保守规则处理。
- [ ] **GOV-01.02** 输入文件/知识/MCP 结果记录来源与当前 ACL revision，RunContext 绑定允许处理级别。
- [ ] **GOV-01.03** 每次外发前校验目标和最小内容，返回更高敏数据不能偷偷切不合规模型或降低标签。
- [ ] **GOV-01.04** 回答、摘要、产物继承来源限制；多来源难以合并时保持私有或需人工解除限制。
- [ ] **GOV-01.05** 分享/下载/重用上下文均校验派生策略，不把 owner 身份当作可无限公开的权限。
- [ ] **GOV-01.06** 测受限数据生成报告、模型 fallback、旧摘要、工具输出假称公开和未知来源。

**验收**：GOVTEST-03/11、KBTEST-05/08 的统一基础。**PR/回滚**：采用更保守策略/停止外发，不删来源标记绕开检查。

<a id="gov-02"></a>

### GOV-02 — 持久审计、脱敏与高风险失败策略

**位置/契约**：`APP/observability/audit.py,redaction.py`、审计表/Outbox；替换仅 JSONL 且写失败继续的生产行为。

- [ ] **GOV-02.01** 定义 actor/service_actor/org/run/action/resource/policy/decision/outcome/trace 字段，正文与元数据分存。
- [ ] **GOV-02.02** 外部写的意图/审批/调用状态在执行前可靠保存；数据库/审计不可写即拒绝新高风险动作。
- [ ] **GOV-02.03** Outbox 向归档/日志系统投递可重试，事实在 PG；普通监控故障不等于必须中断所有只读请求。
- [ ] **GOV-02.04** schema 级标记 Secret/敏感参数，统一覆盖 header/query/body/env/异常链，不只靠密钥前缀正则。
- [ ] **GOV-02.05** 限制审计查询/导出/支持读取权限，访问审计自身也留痕，禁止普通运维默认读正文。
- [ ] **GOV-02.06** 测高风险意图落盘失败、归档中断、重复投递、脱敏边界、跨组织审计列表。

**验收**：GOVTEST-04/05、OPSTEST-11。**PR/回滚**：保留权威审计表，不以关闭审计“恢复写工具”。

<a id="gov-04"></a>

### GOV-04 — 应急开关与全链路禁用

**位置/契约**：`APP/policy/kill_switches.py`、admin API、Worker/manager 钩子；范围可到 org/user/model/capability/profile。

- [ ] **GOV-04.01** 定义开关 scope、reason、expiry、操作者、审批/强认证与审计，不能由模型设置。
- [ ] **GOV-04.02** 原子修改 policy revision，阻止新 Run/新工具/新模型调用，缓存通知丢失仍校验权威状态。
- [ ] **GOV-04.03** 对已排队/待审批/运行中任务分别失效、取消或待核对，保留已发生外部影响。
- [ ] **GOV-04.04** 联动 manager 撤销 capability、停网络/进程，清理失败隔离节点。
- [ ] **GOV-04.05** 解除禁用需明确批准和健康/安全证据，不能到期就自动重新启动历史副作用任务。
- [ ] **GOV-04.06** 测多实例、旧 Worker、Redis 中断、开关竞争和恢复后新任务准入。

**验收**：GOVTEST-06、AUTH-09；不是前端灰按钮。**PR/回滚**：应急控制保守保留，回滚应用不能删除禁用事实。

<a id="gov-07"></a>

### GOV-07 — 受控模型配置与凭据作用域

**位置/契约**：`APP/llm/`、`APP/capabilities/models.py`、模型版本管理；复用兼容层而非复制旧全局配置。

- [ ] **GOV-07.01** 保存批准 endpoint/model/compat/SecretBinding/data policy 的不可变版本，普通用户只能选获权版本 ID。
- [ ] **GOV-07.02** 在配置解析前拒绝 Shell key、任意字面量入库和未批准 base URL；旧 `.env` 只保留本地模式。
- [ ] **GOV-07.03** client cache 按 org/connection/credential revision/model version 分区，Secret 轮换关闭旧池。
- [ ] **GOV-07.04** 在主模型、planner、summary、embedding/reranker 调用前统一检查数据/预算/取消/权限。
- [ ] **GOV-07.05** 对流 usage、finish_reason、限流重试、错误脱敏和中途断流适配各 Provider，重试不越过总 deadline。
- [ ] **GOV-07.06** 模型列表不泄漏其他部门配置/内部路径；自动 fallback 仅限同等获准数据策略的明确版本。
- [ ] **GOV-07.07** 测 endpoint 变化、Key 串用、缓存身份混用、缺 usage、超长工具 schema 和拒绝执行配置命令。

**验收**：GOVTEST-02/03/04、MCPTEST-12。**PR/回滚**：切回已批准模型版本或暂停，不能换公共管理员 Key。

## 6. OPS：最小可信发布与环境配置

<a id="ops-01"></a>

### OPS-01 — 镜像构建、SBOM、签名与准入

**位置/契约**：根 CI、`INFRA/images/`、镜像准入规则；构建身份不进入业务容器。

- [ ] **OPS-01.01** 按锁文件和固定 base digest 构建控制/执行镜像，保留可追溯构建参数与来源 commit。
- [ ] **OPS-01.02** 生成 SBOM、漏洞/许可证检查，例外有风险批准和截止时间，不把所有告警忽略。
- [ ] **OPS-01.03** 可信构建完成才签名/发布 digest，运行时按批准清单校验，不拉可变 latest 执行。
- [ ] **OPS-01.04** 限制 CI Secret 和 self-hosted runner 权限，不执行未经信任 PR 的任意代码并附生产凭据。
- [ ] **OPS-01.05** 建镜像促晋/撤回/保留策略，保留活跃/可回滚 Run 依赖的版本，禁止清理仍引用的层。
- [ ] **OPS-01.06** 测未签名/摘要不符/被撤回镜像被拒；依赖更新触发相关 executor 回归。

**验收**：OPSTEST-04/12、SBXTEST-05。**PR/回滚**：退回批准 digest，不改旧 digest 内容。

<a id="ops-02"></a>

### OPS-02 — 平台环境、反代与生产校验

**位置/契约**：`compose.platform.yaml`、`INFRA/platform/`、`APP/platform_settings.py`；开发 Compose 不是生产 HA 证明。

- [ ] **OPS-02.01** 分控制 API、Worker、manager、数据库、对象存储、代理的身份/网络/Secret，默认不发布 executor 管理端口。
- [ ] **OPS-02.02** 配置 TLS、Cookie/CORS/CSRF、反代流超时/缓冲，SSE 可重连且不泄漏 query Token。
- [ ] **OPS-02.03** production 启动验证 SSO、RLS 角色、Secret、profile、manager、日志/配额；缺失 fail closed。
- [ ] **OPS-02.04** 关闭旧共享 Sandbox/WS/模型 Shell/匿名路由与默认口令，不因依赖失败降级 localhost 执行。
- [ ] **OPS-02.05** 定义迁移先行、API/Worker 兼容版本、停领任务/排空和 manager reaper 独立职责。
- [ ] **OPS-02.06** 用测试环境部署一条真 Worker+沙箱任务，验证反代、网络、身份和保留数据配置。
- [ ] **OPS-02.07** 环境说明只给 SecretRef/变量名，禁止把实际密钥、证书私钥或用户数据作为示例提交。

**验收**：OPSTEST-01/03/09、CAPTEST-09。**PR/回滚**：服务维护或旧兼容版本；绝不开放 legacy 给生产用户作为回退。

## 7. UI：运行轨迹与审批交互

<a id="ui-04"></a>

### UI-04 — 持久 Run 视图与恢复

**位置/契约**：`WEB/features/runs/`；P2 可通过固定测试 Agent 进入，完整 Agent 目录在 UI-03。

- [ ] **UI-04.01** POST 使用稳定幂等键和 session revision，双击/网络重试不创建第二个 Run。
- [ ] **UI-04.02** 以 run_id+seq 去重事件，区分增量文本、工具、审批、产物、错误和终态。
- [ ] **UI-04.03** 刷新先查询 Run/snapshot 再回放缺失事件，游标过期不能盲目从头发起任务。
- [ ] **UI-04.04** 展示排队/准备/执行/待批/保存/停止中/待核对，不能将 HTTP 200 SSE 当执行成功。
- [ ] **UI-04.05** 停止按钮调用后端 cancel 并等待确认，明确外部副作用不能自动撤销；unknown 禁普通重试按钮。
- [ ] **UI-04.06** 断线只重连订阅、退出清理客户端状态；重连/错误 UI 不泄漏上一用户消息。
- [ ] **UI-04.07** 用固定事件流和真实后端测试重复帧/缺帧/终态/慢流/权限撤销。

**验收**：UITEST-02/03/07、RUNTEST-07/08/15。**PR/回滚**：降级获权状态查询，不使用旧聊天 API 重新执行。

<a id="ui-06"></a>

### UI-06 — 审批中心与业务影响说明

**位置/契约**：`WEB/features/approvals/`；UI 不决定实际审批资格。

- [ ] **UI-06.01** 列出“待我审批/我发起/已处理”，后端分页和字段 scope 决定可见内容。
- [ ] **UI-06.02** 展示系统、动作、资源数量、数据影响、连接身份、到期；原始参数放受限可展开详情。
- [ ] **UI-06.03** 提交 approval_id/digest/revision/决定，防重复点击但仍依赖服务端 CAS。
- [ ] **UI-06.04** 处理到期/撤权/Run 取消/参数变化/已被别人处理，旧弹窗不得继续表现为可批准。
- [ ] **UI-06.05** 刷新或换设备从持久审批恢复，页面关闭不等于批准/拒绝；对高风险动作解释双人策略。
- [ ] **UI-06.06** 测焦点/键盘、快速重复操作、后台重启、越权 API、敏感参数可见性。

**验收**：UITEST-04/08、RUNTEST-09～13。**PR/回滚**：关闭可交互写能力而非自动批准待决请求。

## 8. 可合并切片与联调顺序

| 切片 | 内容 | 放行到下一切片前检查 |
|---|---|---|
| P2-A | RUN-01/02/03/04/06、CAP-01/02 接口、GOV-01/02/07 最小策略 | fake 流带真实身份/账本/事件，production 无执行旁路 |
| P2-B | SBX-01/02/03/04/07/08/09、OPS-01/02 | 单测试 Run 可创建、执行、保留产物引用，不暴露管理面 |
| P2-C | SBX-05/06/10/11/12、RUN-07/08/09/10/11、CAP-07 | 所有已开放执行器/审批/预算/取消统一路径 |
| P2-D | UI-04/06、GOV-04、RUN-12/SBX-13/14 | G2/G3 实测、无未确认旁路和不明写自动重试 |

这些是联调批次，不应把一批的数十文件塞进一个 PR。每个父任务卡已给局部回滚，改变接口的 PR 必须与调用方契约测试一起合并。

## 9. 阶段验证脚本与 G2/G3 交接

1. Alice/Bob 同时生成同名文件，确保 API/卷/语言状态/产物隔离。
2. Alice 任务中断网页→重连→继续显示；只发生一个 Run。
3. 待审批时重启 API/Worker，可恢复的动作继续等待，不可重建的明确失效。
4. 批准后修改脚本或输入被拒，旧 generation 操作 manager/发布也被拒。
5. 模拟写服务已成功但断开响应，界面显示待核对，不允许直接再写一次。
6. 在专用节点执行有界资源压力和取消，进程树/卷可清理，Bob 与控制面不受影响。
7. 禁用某 Skill/profile/用户，下一工具动作被拒，已有清理仍可进行。
8. 确认预算、审计、镜像/模型/Manifest/工作区版本可关联同一 Run。

退出必须明确：已验证 executor/profile、尚未接入 parser/stdio 的门禁、恢复限制和剩余风险。交 P3 的不是一个“可随便调用的 execute URL”，而是已带身份、配额、版本、审批与审计的 ToolGateway/RunExecutor 契约。

## 工程契约补充

同 Run 的 compute、持凭据 connector、parser 可使用不同权限 cell，target_slot 成为租约幂等键的一部分。资源/进程/销毁由外部 manager 核对；未知副作用保留 blocker 而不无限保留容器。 详见 [工程契约索引](../engineering/README.md)；任务 ID 和原有子任务顺序保持不变。
