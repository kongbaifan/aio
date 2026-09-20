# 08. 确定性夹具与故障验收配方

> 本文是 40 个新增工程验收用例设计，全部未执行。它们细化原 119 个场景的关键并发/失效窗口，不替代原有矩阵，不是本项目当前通过的测试报告。

## 1. 共用夹具

| 夹具 ID | 内容 | 安全限制 |
|---|---|---|
| FX-ID | Org-A/B；Alice 销售、Bob 财务、Carol 双组、Operator 仅运维、Approver 限业务范围 | 合成身份，不用员工账号 |
| FX-PG | 临时 PG、迁移角色/应用角色/调度角色、可复用连接池、事务 barrier | 无生产 DSN，数据库可销毁 |
| FX-RUN | 固定 Session/模板/预算、确定性 fake model，完整回合及 logical_call IDs | 无真实模型费用 |
| FX-SINK | 假业务写服务，记录 request_count/effect_count/operation_key，支持丢响应/延迟/幂等 | 只写测试数据库/内存，不接真实工单/支付 |
| FX-CELL | 两 compute + 一个 connector/parser target，固定小配额、假 Secret marker、外部 manager | 专用 Linux 可销毁节点，无生产网 |
| FX-OBJ | quarantine/published 测试桶、immutable objects、失败注入、hash/ACL | 无共享用户文件，禁止公开桶 |
| FX-KB | 两部门同名文档及 marker，明确 ACL/epoch/索引版本，reranker/model spy | 文本合成，不调用真实第三方 |
| FX-WEB | 两独立浏览器上下文、可延迟响应/断开 SSE、记录请求与 DOM | 不使用个人浏览器 profile |
| FX-AUDIT | 可靠审计表、可失败外部 sink、字段级 Secret marker | 日志不得含真实 Token |

测试提供可控时间/随机种子/barrier，不用任意 sleep 祈祷竞争出现。真实 runtime 的时限允许容差但记录环境；不在共享开发机或生产节点运行耗尽样本。

每用例证据至少包含：case ID、任务 IDs、commit/image/config、fixture version、安排的 interleaving、SQL/调用计数/资源事实、断言、结果、原始证据位置。

## 2. Run、事务与审批（01–14）

<a id="ecase-01"></a>
### ECASE-01 — 并发同幂等键只创建一个 Run

- **任务/约束**：RUN-02.02/04、INV-11/12；原 RUNTEST-01/02。
- **Given**：FX-ID/PG/RUN，同 Alice、Session revision=8、余额充足、相同 key/body。
- **When**：两个独立数据库连接在 TX-01 幂等行处 barrier 后同时提交；再用同 key 不同 message 请求。
- **Then**：同体返回同 run_id；runs/jobs/initial user message/reservation 各一份；session revision=9；异体 409，行数不变。
- **证据**：事务结果、唯一索引、行数、响应；不得只断言 HTTP 202。

<a id="ecase-02"></a>
### ECASE-02 — 提交后丢响应不重建任务

- **任务/约束**：RUN-02.05、INV-11/12；原 RUNTEST-06。
- **Given**：FX-PG/RUN；故障 FP-02。
- **When**：TX-01 commit 成功后断开 HTTP 回复，客户端用原 key/body 重试。
- **Then**：找回原 run_id；没有第二条 Job、消息或预算；之后 Worker 只领取该逻辑任务。
- **证据**：commit 时间、两请求关联 ID、数据行/派发计数。

<a id="ecase-03"></a>
### ECASE-03 — Session 与预算竞争原子拒绝

- **任务/约束**：RUN-02.03/04、RUN-10.02、INV-11/25；原 RUNTEST-03、GOVTEST-01。
- **Given**：同 Session 两个不同 key，请求各需最后一份可用预算。
- **When**：事务同步竞争 Session/预算锁；另测 Session 不同但预算相同。
- **Then**：同 Session 最多一 unresolved Run；同预算不会两次预留；失败事务不留 user message/job/部分 reservation。
- **证据**：预算前后金额、行计数、唯一冲突/retryable 错误。

<a id="ecase-04"></a>
### ECASE-04 — 租约接管后旧 Worker 不能推进

- **任务/约束**：RUN-03.04、SBX-02.05、INV-13；原 RUNTEST-04/05。
- **Given**：Worker A 持 generation=1；测试时钟让 lease 到期，B 接管 generation=2。
- **When**：恢复 A，尝试 exec、append business event、publish workspace；B 执行合法动作。
- **Then**：A 的新动作全部拒绝；B 正常；旧结果只能作为隔离核对证据，不改变 B 游标。
- **证据**：所有边界收到的 generation、拒绝原因与有效 lease 唯一性。

<a id="ecase-05"></a>
### ECASE-05 — 纯 DB 事务重试不夹带外部 IO

- **任务/约束**：DAT-06、RUN-03/10、INV-16/12。
- **Given**：FX-PG/RUN/SINK，明确事务函数与外部 dispatcher 边界。
- **When**：注入 deadlock/serialization 类暂时性错误，让纯 DB 事务重试；监视 HTTP/模型/runtime adapter 调用。
- **Then**：事务重试期间外部调用计数为 0；最多重试批准次数；事务成功后一个逻辑派发，不在 retry wrapper 内重复副作用。
- **证据**：锁顺序、错误/重试次数、adapter spy；锁超时不解除唯一约束。

<a id="ecase-06"></a>
### ECASE-06 — 审批并发决定只有一个生效

- **任务/约束**：RUN-08.03、INV-15；原 RUNTEST-10/12。
- **Given**：FX-ID/PG，pending Approval revision=3，两个合法请求一个 approve 一个 reject。
- **When**：在 CAS 前 barrier 同时提交，再重传胜出决定。
- **Then**：仅一个 terminal decision；冲突 409；同决定重传返回同事实；审计保留实际决定者。
- **证据**：Approval revision、audit、Invocation 后续状态，非授权审批人始终拒绝。

<a id="ecase-07"></a>
### ECASE-07 — 审批后替换内容被阻止

- **任务/约束**：RUN-08.01/04、CAP-05、INV-15/21；原 RUNTEST-11。
- **Given**：已批准脚本/输入/工具/连接 revision 的 ActionSpec。
- **When**：分别替换脚本字节、输入对象、依赖版本、参数、连接身份；尝试用旧批准执行。
- **Then**：ACTION_CHANGED/invalidated；FX-SINK effect_count=0；不得仅重新 hash 后覆盖原 ActionSpec。
- **证据**：旧/新 digest、拒绝原因；每种变更独立用例，不只测参数字符串。

<a id="ecase-08"></a>
### ECASE-08 — 待审批重启且进程状态丢失

- **任务/约束**：RUN-07.05、RUN-08.05、INV-14/15；原 RUNTEST-09。
- **Given**：pending Approval 和 checkpoint 已存；分别建立 reconstructible 与 process_state_dependent 两类动作。
- **When**：重启 Worker 并销毁旧 cell，用户批准原动作。
- **Then**：可重建且摘要/权限仍有效的动作按新绑定恢复；不可重建者执行许可失效并明确核对/失败，不凭旧 Future 继续。
- **证据**：checkpoint、restartability、cell 绑定、审批事实和实际 dispatch_count。

<a id="ecase-09"></a>
### ECASE-09 — prepared 与 dispatching 中断语义不同

- **任务/约束**：RUN-09、MCP-06.03/04、INV-12/14/26。
- **Given**：FX-SINK；分别停在 prepared commit 后和 dispatching commit 后。
- **When**：进程退出后恢复。
- **Then**：prepared 且契约证明未发送可继续同逻辑动作；dispatching 不知道是否已发必须查询/去重或 unknown，不盲换新业务键。
- **证据**：状态时间线、网络 spy、operation_key；不以异常名字推断 not_sent。

<a id="ecase-10"></a>
### ECASE-10 — 下游已成功但回复丢失

- **任务/约束**：MCP-06、RUN-09.04、INV-12/14；原 MCPTEST-11、RUNTEST-14。
- **Given**：FX-SINK 收到操作后 effect_count=1，但主动丢弃响应。
- **When**：dispatcher timeout、Worker 重启、客户端点 retry。
- **Then**：支持幂等/查询时确认原结果，effect_count 仍为 1；无可核对能力时 recovery_required，普通 retry 被拒。
- **证据**：request_count 可大于 1，但同业务 key effect_count=1；不支持幂等分支不自动重发。

<a id="ecase-11"></a>
### ECASE-11 — 旧代次迟到结果不污染新游标

- **任务/约束**：RUN-03/07、GOV-03、INV-13/25。
- **Given**：旧 dispatch 已获准并可能收费，generation 已更新；延迟结果随后返回。
- **When**：旧 Worker 尝试提交 result/usage/next cursor。
- **Then**：不能推进新游标；可由受限 reconciler 去重保存该旧 dispatch 的费用/下游确认事实，不能简单丢实际账单。
- **证据**：业务状态不变、隔离证据与 ledger 仅一次，无新工具调用。

<a id="ecase-12"></a>
### ECASE-12 — 取消未知写时保留阻断但释放计算

- **任务/约束**：RUN-09、SBX-11、INV-14/18；原 RUNTEST-15。
- **Given**：一个外部写效果未知的 Run，占 Session/project 写范围并有 compute cell。
- **When**：用户取消、manager 确认 cell 销毁，再向相同 Session/受影响业务范围提交写任务。
- **Then**：Run 为 recovery_required，计算配额释放但 durable blocker 生效，新写被拒；核对后显式解除，不自动重跑旧任务。
- **证据**：runtime resources=0、blocker 未解除、Session 槽/新请求错误、核对审计。

<a id="ecase-13"></a>
### ECASE-13 — 产物上传成功但发布失败

- **任务/约束**：SBX-10、RUN-07、INV-18/19；原 RUNTEST-16。
- **Given**：FX-OBJ 已有 candidate；在 TX-08 head CAS/DB commit 处注入失败。
- **When**：用户查询 Run/文件/下载，随后安全重试发布。
- **Then**：第一次不是 succeeded，candidate 不公开；重试仍校验权限/head，只发布一次；孤儿按明确策略清理。
- **证据**：对象 key/scan 状态、Artifact 记录/ACL、workspace head、下载拒绝。

<a id="ecase-14"></a>
### ECASE-14 — 恢复使用已提交逻辑调用而非重问模型

- **任务/约束**：RUN-07.02/03/04、INV-12/17；原 RUNTEST-14/17。
- **Given**：fake model 一完整回合含两工具，第一个结果提交后在游标边界故障。
- **When**：恢复最新 checkpoint；fake model spy 会在重问时生成不同参数以暴露错误实现。
- **Then**：已确认调用不重发，下一调用使用原已提交参数；不能从原 prompt 重跑所有步骤。
- **证据**：model call count、logical_call IDs、下游 effect count、游标和事件序号。

## 3. 身份、事件与执行边界（15–27）

<a id="ecase-15"></a>
### ECASE-15 — 连接池在异常后不串组织

- **任务/约束**：DAT-06、IAM-06、INV-02/03；原 AUTH-07/08。
- **Given**：FX-PG pool_size=1，Alice 和 Org-B 用户各有 marker 行。
- **When**：A 事务设置 org 后异常/取消/rollback，B 借同连接查询；另测无上下文事务。
- **Then**：B 只见 B，空上下文不见业务行；跨 org 写 FK/RLS 拒绝。
- **证据**：连接复用 ID、事务本地设置和实际结果，不只 mock Repository。

<a id="ecase-16"></a>
### ECASE-16 — GUC RLS 的威胁边界负控制

- **任务/约束**：IAM-06、INV-03/30。
- **Given**：隔离 FX-PG 使用基于 trusted app.org_id 的 RLS，无真实数据。
- **When**：分别验证普通 API 不能设身份/执行任意 SQL；由测试管理员模拟“应用 DB 凭据失陷”直接设置另一 org 上下文。
- **Then**：API 路径必须拒绝伪造；测试记录 GUC 模式可能允许持该数据库角色的人改变上下文，不把此模式宣称为抵御任意 SQL 的安全隔离。
- **证据**：数据库角色/策略、API 拒绝、明确剩余风险；若业务要求抵御凭据失陷则该架构 no-go 或采用更强数据域。

<a id="ecase-17"></a>
### ECASE-17 — Logout 与离职撤权区别

- **任务/约束**：IAM-02/03/08、INV-01/04。
- **Given**：Alice 有运行中的授权 Run 和浏览器会话。
- **When**：普通 logout 后观察后台，再将成员标停用并提交。
- **Then**：logout 关闭浏览器访问但按批准默认 Run 可继续；停用后新工具/模型授权拒绝并触发停止/核对；不能因 Cookie 到期永久授权或误取消所有后台工作。
- **证据**：auth_session、membership revision、Run delegation、实际后续调用。

<a id="ecase-18"></a>
### ECASE-18 — 撤权后不能靠旧幂等键读取结果

- **任务/约束**：IAM-08、RUN-02、INV-02/04/12；原 AUTH-09。
- **Given**：Alice 曾创建成功 Run，保存 key；资源或成员权限随后撤销。
- **When**：用旧 key/body 重放 POST、读 status/events/download。
- **Then**：先当前授权再幂等结果返回；所有敏感读取拒绝，不因历史请求成功而泄露正文。
- **证据**：决策时间/撤权 commit 顺序、响应 payload 无 marker。

<a id="ecase-19"></a>
### ECASE-19 — SSE 历史/实时交界无丢失且有界

- **任务/约束**：RUN-04/05、UI-04、INV-17；原 RUNTEST-07/08。
- **Given**：已有 seq 1..20，客户端 after=10，通知服务可丢消息。
- **When**：在历史读取与订阅注册间提交 seq21，重复投递 seq20，并让客户端短暂慢读；之后用原游标重连。
- **Then**：最终获权事件 11..21 各呈现一次；PG 轮询补通知缺口；缓冲超限可断开但不能丢终态或重跑任务。
- **证据**：DB seq、发送/呈现列表、最大缓冲、model/dispatch count 不增加。

<a id="ecase-20"></a>
### ECASE-20 — stdout 不能伪造管理事件

- **任务/约束**：SBX-04、INV-06/07；原 SBXTEST-04/08。
- **Given**：FX-CELL 代码只打印看起来像 approval/lease/destroyed 的 JSON/事件文本。
- **When**：文本经 stdout/stderr 返回。
- **Then**：它只出现在不可信 output 数据中，不能改变 Approval/Run/lease/配额或触发工具；外部 manager 核实的状态保持真实。
- **证据**：控制通道与数据输出 schema、数据库前后状态和资源清单。

<a id="ecase-21"></a>
### ECASE-21 — 创建 cell 后丢回复仍能幂等找回

- **任务/约束**：SBX-02/11、INV-07/13；原 SBXTEST-18。
- **Given**：ensure_target 的固定 org/run/generation/slot/profile；运行时创建已完成。
- **When**：丢 manager 回复并重传；再用同键不同镜像/输入摘要请求。
- **Then**：同 spec 返回同 backend ID，一份容量预留；异 spec 冲突拒绝；终结后一个资源被准确清理。
- **证据**：runtime create count、resource IDs、reservations 和实际卷/网络数量。

<a id="ecase-22"></a>
### ECASE-22 — 任意计算代码看不到连接器凭据

- **任务/约束**：SBX-12、MCP-05、INV-05/08/22。
- **Given**：FX-CELL 中 compute 与 credentialed connector 独立权限域，Secret 仅为合成 marker。
- **When**：计算代码尝试通过共享文件、env、进程/IPC/网络路径读取 marker 或绕过 Gateway 调业务 endpoint。
- **Then**：不可读/不可直连；合法获权 MCP 调用可完成；如果选择同域导致可读取，测试明确判该 profile 不满足强审批边界。
- **证据**：mount/network/UID/PID 配置、marker 不出现、Gateway 与 FX-SINK 计数。

<a id="ecase-23"></a>
### ECASE-23 — 字节与 inode 硬配额不是清理脚本

- **任务/约束**：SBX-07、INV-09；原 SBXTEST-09。
- **Given**：专用节点小容量测试卷、独立 inode 上限与宿主保护水位。
- **When**：用有外层上限的受控写入分别逼近 bytes/inodes 限制，观测 HOME/tmp/output/日志所有可写路径。
- **Then**：每路径都受有效配额；超限只失败当前 target，控制面/另用户仍可用；named volume 若无硬限制不能标通过。
- **证据**：实际 quota/cgroup 配置、使用曲线、异常码、宿主余量；禁止真实共享盘耗尽。

<a id="ecase-24"></a>
### ECASE-24 — 重定向/DNS/IPv6 不绕过出口

- **任务/约束**：SBX-08、MCP-04、INV-10；原 SBXTEST-14/15。
- **Given**：模拟 resolver/proxy 和受控地址目标，允许 endpoint 会重定向到拒绝网段。
- **When**：测试初次 DNS、重绑定、IPv6/映射地址、直连忽略 proxy env、MCP metadata/resource link。
- **Then**：实际连接处拒绝不允许目标；不访问生产管理网/metadata；合法目标仍按明确范围通过。
- **证据**：代理与节点层流量记录、DNS 决策、connection attempts，不能只看 URL 检查函数。

<a id="ecase-25"></a>
### ECASE-25 — 内部 runner 故障不能假释放资源

- **任务/约束**：SBX-04/11、INV-07/09；原 SBXTEST-10/19。
- **Given**：FX-CELL 有受控短期子进程，runner 提前退出/错误声称已停止，外部 runtime 仍可见资源。
- **When**：cancel/destroy 发生，manager 核对真实进程树。
- **Then**：未核实前不标 destroyed、不释放节点容量、不回池；确认全树停止后才清理计数；失败隔离节点。
- **证据**：外部 runtime 资源快照、cleanup state、capacity ledger 和告警。

<a id="ecase-26"></a>
### ECASE-26 — 归档与产物的链接竞争

- **任务/约束**：CAP-03、SBX-10、INV-19/20；原 SBXTEST-11/12/13。
- **Given**：仅测试目录中的绝对/越界/链接/特殊文件归档和一个可控替换链接的 writer。
- **When**：扫描/收集在校验与读取之间遭遇替换；另测压缩比/文件数上限。
- **Then**：不读写保护目录、不发布逃逸对象；writer 先停止或安全文件句柄阻止 race；异常有界。
- **证据**：保护文件 hash、collector 读取目标、拒绝原因和产物集合。

<a id="ecase-27"></a>
### ECASE-27 — 旧 writer 不能覆盖新 Workspace head

- **任务/约束**：SBX-09/10、INV-13/19；原 SBXTEST-17。
- **Given**：A 基于 head V1，lease 失效；B 获新 lease 发布 V2。
- **When**：恢复 A 并用旧 base/generation 发布自己的 candidate。
- **Then**：A CAS/lease 校验失败，head 保持 V2；候选不公开覆盖，B 结果与配额正确。
- **证据**：writer lease、version lineage、Artifact 可见性和 revision。

## 4. 能力、数据、运维与界面（28–40）

<a id="ecase-28"></a>
### ECASE-28 — 受限来源不能通过新报告洗掉权限

- **任务/约束**：GOV-01/06、SBX-10、INV-24；原 GOVTEST-11。
- **Given**：Carol 同时可见销售/财务资料，报告来源含两者；Alice 只可见销售。
- **When**：Carol 试图把报告分享给 Alice/全部门，模型同时声称“已脱敏”。
- **Then**：未有批准解除限制时拒绝扩大分享；自己的获权读取正常；产物/摘要保留来源策略。
- **证据**：source refs、derived policy、grant 决策、下游下载不含财务 marker。

<a id="ecase-29"></a>
### ECASE-29 — 删除与旧索引 Job 发布竞争

- **任务/约束**：KB-02/07、INV-24；原 KBTEST-09/14。
- **Given**：document epoch=7，旧 Job 已完成 embedding 尚未 publish。
- **When**：删除事务提交 epoch=8，再允许旧 Job 发布；重放重复完成通知。
- **Then**：文档不回 ready，检索/引用拒绝，候选索引待清理；重复通知不降低 epoch。
- **证据**：PG document/job/index 状态和模型/检索 spy 无 marker。

<a id="ecase-30"></a>
### ECASE-30 — 未授权最相似文档不进入重排/模型

- **任务/约束**：KB-05/06、INV-23；原 KBTEST-03/04/05/13。
- **Given**：未授权财务文档与查询向量最相似，授权销售文档相似度较低；模型/reranker spy 记录输入。
- **When**：Alice 做向量+关键词检索并读取引用，重复相同查询测试缓存。
- **Then**：只有获权内容进入应用结果/重排/模型/缓存；低召回可以明确无答案，不能放宽 ACL；猜未授权 citation ID 仍拒绝。
- **证据**：实际 SQL 授权过滤、候选/spy/日志 marker 检查、返回引用集合。

<a id="ecase-31"></a>
### ECASE-31 — 远端 schema/风险变化不能自动扩权

- **任务/约束**：CAP-02、MCP-04、INV-04/21/22；原 MCPTEST-05/06。
- **Given**：批准的只读工具版本；远端下一次 discovery 新增写工具或改变已有 schema 并标 readOnly=true。
- **When**：客户端刷新目录，模型试图调用新动作。
- **Then**：变化进入待审核，新能力不加入有效 Manifest；平台风险不被远端注解覆盖。
- **证据**：旧/新 schema digest、alias 映射、Gateway deny、FX-SINK effect_count=0。

<a id="ecase-32"></a>
### ECASE-32 — 凭据刷新晚于撤销不能复活连接

- **任务/约束**：MCP-02/03、IAM-07/08、INV-04/05/22；原 MCPTEST-03/10。
- **Given**：connection revision=4，refresh 请求被延迟。
- **When**：用户撤销 revision=5 并关闭池，然后返回旧 refresh 成功结果；再尝试调用。
- **Then**：旧结果 CAS 不可覆盖撤销；Token 不重新启用、池不复活；新调用拒绝。
- **证据**：Secret binding revision/connection state、refresh lock、pool 数量和审计。

<a id="ecase-33"></a>
### ECASE-33 — 诊断和错误不泄漏 Secret/越权正文

- **任务/约束**：IAM-07、GOV-02/05、INV-05/27；原 GOVTEST-04/07。
- **Given**：合成 Secret marker 分别嵌在 header/query/env/嵌套异常/工具结果，Operator 默认无正文 grant。
- **When**：触发失败、SSE error、审计查询、诊断包导出；再授予限定字段/时间 grant。
- **Then**：无 grant 只见元数据；有 grant 也不输出 Secret；到期停止新读，访问自身有审计。
- **证据**：各出口内容检查/权限日志，图片/截图按内容权限处理而非宣称正则已脱敏。

<a id="ecase-34"></a>
### ECASE-34 — 审计事实不可写时不产生高风险效果

- **任务/约束**：GOV-02、MCP-06、INV-26；原 GOVTEST-05。
- **Given**：已获准写请求，分别让 PG 意图写失败、外部日志归档失败。
- **When**：尝试派发。
- **Then**：PG 意图失败时 dispatch/effect_count=0；仅外部归档失败但 PG/Outbox 可靠时按策略继续且有告警，不混淆两种故障。
- **证据**：事务 rollback、Outbox backlog、adapter spy 和明确错误。

<a id="ecase-35"></a>
### ECASE-35 — 未知费用、重复账单和超预留调整

- **任务/约束**：RUN-10、GOV-03、INV-25；原 GOVTEST-01/02。
- **Given**：模型部分输出断开无 usage，保守预留未释放；稍后账单实际金额超过估计。
- **When**：重复送同 provider request 的 usage，再送受控调整记录。
- **Then**：unknown 不记免费；同事实只入账一次；调整追加并形成 overage/debt，阻止新超额调用但不丢真实账单。
- **证据**：Ledger 唯一键、原预留/结算/调整、currency/price_version 与 UI 标记。

<a id="ecase-36"></a>
### ECASE-36 — 恢复旧备份不会复活已撤权数据

- **任务/约束**：OPS-03、KB-07、GOV-06、INV-29；原 OPSTEST-06、GOVTEST-10。
- **Given**：旧备份含 active 用户和文档，权威后续 tombstone/离职/禁用日志在独立受控来源。
- **When**：恢复到无出网无自动 Worker 的环境，再同步当前撤权；另测无法取得当前事实。
- **Then**：已撤权内容不开放，旧 active Run 不自动执行；无法确认时服务/受影响资源保持隔离。
- **证据**：恢复点、删除/身份重放、ACL 查询、dispatch_count=0、实际 RPO/RTO。

<a id="ecase-37"></a>
### ECASE-37 — 不兼容 checkpoint 不自动从头执行

- **任务/约束**：RUN-06/07、OPS-07、INV-14/21/29。
- **Given**：checkpoint schema 来自不支持的引擎/版本，历史含已发生的写调用。
- **When**：新/旧 Worker 尝试接管。
- **Then**：明确 unsupported/recovery_required，保持旧事实与 blocker；不能丢 checkpoint 从最初消息重跑。
- **证据**：兼容矩阵、错误、历史 effect_count 不增加。

<a id="ecase-38"></a>
### ECASE-38 — 切换用户后的迟到响应不可显示

- **任务/约束**：UI-02/03/04、INV-01/02；原 UITEST-01。
- **Given**：Alice 的请求被延迟，浏览器 logout 后登录 Bob；同样测试项目切换。
- **When**：释放 Alice 旧响应/旧 SSE 帧到前端。
- **Then**：client_context/view epoch 不匹配而丢弃，不写 Bob 缓存/DOM；后端旧订阅也停止新增获权读取。
- **证据**：两个上下文的请求/缓存/DOM marker；不是只断言 AbortController 调过。

<a id="ecase-39"></a>
### ECASE-39 — 生产缺依赖不能降到共享宿主

- **任务/约束**：FND-05、OPS-02、CAP-07、INV-06/28；原 OPSTEST-01。
- **Given**：production 模式分别缺 SSO/安全 profile/manager/正确 DB role/Secret resolver。
- **When**：启动或提交任务，并直接请求旧 chat/file/WS/MCP 调试路径。
- **Then**：启动拒绝或对应能力关闭；无控制侧 subprocess/旧全局 Token 放行；原端口关闭或受相同授权。
- **证据**：启动诊断、路由/网络探测、adapter spy，错误不输出密钥配置。

<a id="ecase-40"></a>
### ECASE-40 — 模型配置在旧 Shell 解析前被拒绝

- **任务/约束**：IAM-07.04、GOV-07.02、INV-05/06/28；原 MCPTEST-12。
- **Given**：production 用户配置包含 `apiKey` 的命令形式或未批准 base URL；subprocess/网络调用用 spy 而非执行。
- **When**：创建/读取模型配置、初始化 ModelService、测试连接。
- **Then**：配置校验先拒绝；subprocess 和未批准 endpoint 调用计数均为 0；不能执行后再报不安全。
- **证据**：构造/校验调用顺序、spy、错误和审计；legacy-local 的明确兼容分支单独测试不进入生产。

## 5. 用例执行纪律与判定

- 每个 Then 是多维断言：HTTP/数据库/外部计数/资源/可见内容，不以单个 200/异常字符串代替。
- 时间竞争使用 barrier 和可控故障点，不靠长 sleep；运行时资源测量保留必要容差并记录。
- fail、blocked_by_environment、unsupported_profile、not_run 分开；不能把 skip 汇总为 pass。
- 错误恢复中故意注入的失败是预期，但业务副作用/数据泄露的断言不能被重试掩盖。
- 这些新增用例覆盖深层契约；原 119 项中的常规格式/浏览器/业务质量等仍要执行，不能以本文件较少的用例替代。
- 所有证据初始为空；真正执行时才填写 actual_result/observed_counts/run_at/commit/image，规划生成不能填成通过。
