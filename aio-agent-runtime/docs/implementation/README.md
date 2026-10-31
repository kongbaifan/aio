# 企业 Agent 平台：实际实现与验证进度

> 状态：实施中，目标尚未完成。规划范围仍是企业多部门平台，不缩减为这一轮基础代码。  
> 2026-10-25 后续增量（Slice B）：审计归档投递 relay 已达 v15 / 61 表 / 90 路径，完整平台套件 599 tests、0 failures、0 skipped；只验收 fake sink，真实归档适配器与 relay 进程接入未做。
> 2026-10-25 后续增量：[持久审计与结构化元数据（GOV-02 Slice A）](audit-redaction-plan.md) 已达 v14 / 61 表 / 90 路径，在注入全部镜像的完整平台套件（583 tests、0 failures、0 skipped）中通过；outbox 归档投递与统一出口脱敏（Slice B/C）未做。本轮验证在用户提供的远程 Linux 主机（Docker 29、Python 3.13）上执行，不是本机或 CI；见第 3 节。
> 2026-09-16 后续增量：[组织 / 部门共享预算](shared-budget-plan.md) 已达 v13 / 61 表 / 90 路径，并在注入全部镜像的完整平台套件（500 tests、0 failures、0 skipped）与两套独立干净栈的真实 HTTP 中通过；模型 / IdP 仍为合成，公司真实接入、浏览器视觉验收与全部生产 Gate 均未通过。下方归档增量的历史统计属于上一已核验结果，不代表本增量范围。
> 2026-09-14：[Skill 归档隔离导入](skill-archive-plan.md) 已完成本增量的真实 Docker/PG/HTTP 与 Web 单元验证；该增量完成时为 v12 / 59 表 / 87 条 API 路径，已被上面的预算增量取代。浏览器、公司提供方和全部生产 Gate 仍未通过。
> 基线提交：`1164d95`；规划文件是设计快照，本目录只记录当前代码能够证明的事实。没有把 110 父任务或 718 子任务整体标为完成。

## 1. 当前已落到代码的范围

- 显式 `HARNESS_MODE`：legacy-local / platform-test / platform-production。
- 平台入口在读取 legacy dotenv/模型目录之前校验；直接构造旧运行时/模型服务和命令式密钥解析也有模式护栏。
- 配置值严格校验，敏感值不出现在配置 repr/错误；生产要求 HTTPS 与 PostgreSQL verify-full TLS。
- 不可变 Principal、当前 facts 的默认拒绝授权、用户级资源 Grant、组织策略与数据等级上限。
- OIDC code + PKCE + state/浏览器绑定/nonce/签名/issuer/audience 校验；只允许已由管理员预登记的账户。
- Opaque BFF Cookie 仅存 hash，CSRF/Origin 校验；logout 不擅自取消后台任务，成员停用阻止后续访问。
- v1～v14 保持不可变迁移快照；当前为 `0015_audit_archive`、61 张 PostgreSQL 表，包括部门、Skill、MCP/OAuth/stdio 租约、知识库、同 Run 的 Team 计划/步骤及共享预算池/分配；继续使用 FORCE RLS、复合组织外键和独立 runtime/迁移账号。
- 私有 Project/Session/Agent 读取与创建；共享 Project 不公开私人 Session；上级 Project 撤权也影响列表/详情。
- Run、消息、Job、ManifestSnapshot、预算预留、起始事件和幂等响应在同一事务提交。
- 同 Session 未解决任务唯一约束；同用户两个 Session 并发不能透支最后一份预算。
- 数据库租约领取/心跳、generation 校验、取消排队任务的幂等预算释放。
- 严格 JSON + RFC 8785 摘要、固定 ActionSpec、持久审批、双人职责分离、过期审批先落盘再报错。
- 按 Run 授权的 SSE 事件回放；可重连读取 PG，不依赖内存消息队列；logout/撤权时停止新读取。
- 隔离的 v2 API 没有挂载旧 chat/file/terminal/MCP/debug 执行旁路。
- 可重复运行的一次性 PostgreSQL 测试脚本及独立 CI job；只绑回环地址，不挂业务数据，结束校验标签后清理。
- 独立 `run_worker.py` 与 `DurableWorker`：后台执行 single 和显式开放的顺序 Team，完整模型回合→获权工具→后续模型→最终回答持久化，不依附 HTTP 连接。
- Worker 的配置与 BFF 分离，不要求持有浏览器 OIDC client secret；模型 origin 和 Secret 环境变量名必须显式允许。
- `ChatModel` 有界解析流式文本/工具参数/usage，拒绝重定向、压缩流、不完整回合和原始错误回显；不自动重试可能已计费请求。
- 完整模型回合和工具结果对应持久 checkpoint，工具/模型版本按摘要与当前资源授权验证。
- 审批可以挂起并释放 Worker；批准后新 Worker 使用原已提交调用继续，不重复生成第一轮模型动作。
- 派发许可只可消费一次，业务 operation key 跨安全恢复保持稳定；派发后结果不明进入待核对，不自动重跑。
- 队列到期、lease 过期、审批到期与安全 checkpoint 接管；未知工具效果或未清理 cell 保留持久 blocker。
- 有权限的不同人员可核对未知结果；cell 未核实停止时不能解除阻断。确认外部效果不等于整个 Agent 已成功。
- 个人 Run 费用预留/已知费用结算/未知 usage hold；迟到费用通过审计的 append-only adjustment 核对，重复凭据不重复计费。
- v2 提供获权审批列表/详情/决定与 Run 核对 API，审批资格不会带来整段私人 Session 的读取权。

### 新增：真实 Python 隔离执行和私有产物

- 独立 `services/sandbox-manager` 负责 Docker 权限；Worker 仅使用认证的私有 HTTP API。Manager 调用平台内部权限接口复核当前 Run、generation、lease、工具代码和资源权限。
- 固定无网络 Python compute profile：用户代码 UID10001、只读镜像、cap_drop ALL/no-new-privileges、无宿主路径/Socket 挂载、CPU/内存/PID 限额。
- 独立非 root UID10000 的 PID1 到期 watchdog，计算代码不能停止它；没有运行 manager reaper 时，空闲 cell 仍会到期停止。
- 工作区使用独立 tmpfs-backed 卷并设字节/inode 限额，HOME/tmp 同样受限；不能拿普通无限 named volume 当硬配额。
- 命令/分配/导出记录进入 manager journal；单一进程持目录锁，重复 dispatch 不再次运行；遗失执行 cell 不会悄悄重建成空环境。
- 真实验证输出洪水、进程树超时、PID/磁盘/inode 上限、用户间文件/HOME 隔离、无网/只读/权限、稀疏文件和链接导出拒绝。
- 管理器先外部暂停写入，再由 Docker daemon 收集并校验文件，最后确认容器/卷删除；不信任用户 stdout 的完成/清理声明。
- 私有 Artifact 上传/元数据/下载 API 与 BlobStore；同 Org 的对象 hash 也不是授权票据；下载始终为附件，不在控制域执行 HTML/Office。
- 组织/项目持久存储配额、上传/导出预留、写盘前绑定不可变内容，冲突重试不会写入额外未记账 blob；存储低水位与 manager 导出缓存容量独立检查。
- Run 专属 workspace 副本、Project 单写 lease、生成文件 staging、当前来源授权与 head CAS；最终 Artifact/WorkspaceVersion 与 Run 结果在同事务公开。
- 来源撤权影响后续模型/代码动作、派生文件下载、Run 结果/事件回放，并对私人会话中的派生回答做遮蔽；安全取消不因此被阻止。
- `run_worker.py` 在明确 manager URL/token 与 artifact root 后注册真实 `sandbox.python`，未配置仍失败关闭而非宿主执行。
- 全链路测试只替换模型：Worker→认证 Manager API→真实 Docker Python→实际文件→PG 发布→按权限下载已经实际运行。

### 新增：部门管理与真实 Web 工作台

- React/TypeScript 的 SSO 工作台、私有会话、稳定幂等任务提交、严格 SSE/重连/身份 epoch、审批、文件、个人用量与管理中心已接真实 API。
- 管理中心支持预登记身份、部门成员、显式 user/department Grant、操作员白名单内的模型/工具、Agent、预算、运维元数据和审计/组织策略。
- 最后一位 org_admin 保护、私有会话/文件无管理员通读旁路；资源/成员变化不任意污染全组织 policy revision。
- 90 个实际 OpenAPI path 已导出，请求表单使用生成类型；响应仍有手写投影，不宣称所有响应均由 schema 强类型生成。
- API 同源提供生产构建；部署步骤与有限时长本机预览见 [工作台 README](../../web/platform/README.md)。

### 新增：共享 Skill 文本能力包 v1

- 受限文本 JSON 包、服务器计算摘要/文件清单、不可变内容列、组织配额和私有作者/指定审核人访问。
- 独立持久验证 Job，通过已鉴权 Manager 在无网络 cell 中做静态检查和声明样例；清理回执未知时不能发布，也不盲目重跑。
- 不同人员审核时再次检查当前权限、包 revision、验证结果、外部清理与操作员 profile；发布工具和状态原子提交。
- Agent 选择固定 Skill；`skill.read` 读取获权引用，`skill.python` 执行嵌入的固定入口，不受 workspace 中同名脚本替换。
- read/use 权限及其来源分别传播到 Run、历史 checkpoint、Workspace 和产物；撤权影响后续模型/工具、历史、事件和下载。
- 修复 Worker 原始历史重用、清理恢复租约抢占和危险 schema 校验问题。覆盖与完整规划差额见 [Skill 增量覆盖](skill-slice-coverage.md)。

### 新增：MCP 只读 HTTP 与独立凭据网关

- 固定服务定义/个人与部门连接/凭据引用分开；Agent 分享定义，不复制创建人的个人 Token。
- API 只短暂转交用户填写的令牌，PG/Worker 使用凭据引用；独立网关用 AES-GCM 存储凭据与结果，服务控制口无 token-read/任意 URL/exec 接口。
- 操作员批准端点与只读工具名，真实 DNS/socket peer/Host/TLS SNI 校验，不跟随 redirect，不自动抓取 resource link。
- 凭据保存不等于已连接：实际 initialize/tools list 检测成功后才 active；发布固定 schema/alias，后续漂移拒绝业务 RPC。
- Run 解析当前用户连接并冻结 ref/revision；当前授权/lease 再验证，发送后的未知结果不自动重跑。
- 连接来源贯穿历史、workspace 和产物；错误插入个人 connection.use Grant 也不能借用另一个用户的令牌。
- Web 已接入 MCP 服务发布、我的连接、密文上传票据、检测、明确撤销和任务身份选择。管理台/连接页按需加载，当前主 JS 构建约 450 KiB（本机构建 `index-*.js` 461,038 字节，Admin/Connections/Knowledge 另行分块）。
- 初始 HTTP 增量边界见 [MCP 覆盖](mcp-slice-coverage.md)；后续 OAuth、隔离 stdio 和知识库见下文独立证据。可核对真实写仍未交付。

### 新增：知识库、文档 ACL、混合检索与引用

- 新增 KB/document/version/chunk/query/citation/embedding-model/usage 领域表；当前版本的原文、解析结果、索引与引用都有明确来源。
- 上传先预留额度和不可变字节意图；TXT/MD/CSV/PDF/DOCX/XLSX 在真实无网 parser cell 中处理，控制宿主不解压/渲染用户文件。
- 受限文档默认不随 KB 公开；检索先做当前权限与 Run 固定版本交集，再执行中文词项/pgvector exact cosine/RRF，未获权内容不先交给模型。
- 浏览器仅做关键词预览；Worker 做配置后的混合检索。嵌入请求先预留预算、保存意图，再外发；费用/结果未知不当成零、不盲目重试。
- server-minted 引用绑定固定文档版本/位置；更新、权限变化、删除会传递到历史、Run、workspace 和产物。
- 删除先撤权，确认 parser 清理和导出 acknowledge 后删除索引/引用及无其他引用的原始 blob；迟到 Job/heartbeat 不复活或倒退已提交内容。
- Web 已接上传、版本状态、权限/删除确认、引用查看、embedding模型/费用核对。当前边界见 [知识库契约](../engineering/platform-knowledge-contract.md) 和 [规划差额](knowledge-slice-coverage.md)。

### 新增：同一 Run 内的持久顺序 Team

- AgentVersion 显式开放模式与步骤/轮数上限；Planner、步骤和汇总关联同一个 Run，不创建子用户/子项目或每步常驻容器。
- 规划/汇总无工具；步骤只能用固定 Manifest 的能力子集，模型/工具事实绑定 stage/step，dispatch 重新核对当前范围与身份。
- 计划、步骤状态、输入输出 checkpoint 落 PG；保留 v1 checkpoint hash，全局模型/工具 logical ID 不因步骤重置。完成步骤重启后不重新问模型。
- Planner/步骤/embedding/汇总共用一份预算、取消和截止；失败/拒绝/未执行状态真实进入汇总，模型不能把失败步骤改为成功。
- 同代次真实 Python 步骤间文件可共享；下一 Run 使用不同 cell，前次已发布附件字节不变。MCP 身份和知识库来源贯穿步骤/汇总，撤权同样阻止 Team 详情与事件读取。
- Web 提供发布配置、执行方式选择、持久步骤进度；中间输出不混入最终答复，长 SSE 内刷新授权投影，迟到响应不恢复已撤权内容。
- 安全审批边界已接入私有文件检查点交接：旧 cell 销毁确认后，新 Worker 验证来源、字节、配额和原项目版本，再恢复新环境；无 ready 证明的旧活动进程仍阻断。见 [Team 契约](../engineering/platform-team-contract.md)、[文件检查点](../engineering/platform-workspace-checkpoint-contract.md) 与 [规划差额](workspace-handoff-slice-coverage.md)。

### 新增：审批边界的私有文件检查点

- 检查点不冒充已发布产物，不提前推进 project head；当前支持 <=64 文件、总计 <=8 MiB。
- 计算后等待审批不必占着容器与 Worker；审批期间决定到达也强制结束旧代次，在新代次核验后恢复文件，不重复已完成步骤或已提交参数。
- 原 Run 的五类来源、费用、取消和截止不重置；不恢复内存、后台进程、HOME 或系统安装状态。
- 预留先从工作区转移到 checkpoint，再绑定实际 bytes；组织/项目及知识库存储总额统一计入。旧 SQL/JSON null 不再误留未绑定输出 hold。
- 本地字节写入与引用 GC 使用同一存储锁，避免被取消的线程迟到重建无引用文件；缺失/损坏/撤权/半写不会继续模型或远端动作。
- ack 清除 Manager 导出缓存和旧 CellSpec 输入副本；后台核实旧/停止中 cell 清理，仍保留未知效果 blocker。引用 GC 不删仍由文档、产物、上传、workspace 版本或其他快照引用的 hash。
- Web 显示有界文件检查点元数据与 file-only 限制；临时数据清理和 ack 推进 Run revision，晚响应不能倒退状态。

### 新增：MCP OAuth、稳定授权绑定与刷新

- 操作员预登记 client、issuer、PRM/AS/JWKS/token/revoke/callback 与最小 scope；发现信息不变成任意 URL/权限，OAuth 出口复用 DNS/socket peer/TLS 检查。
- 原 BFF 登录会话与连接意图绑定 state/code hash；PKCE verifier、OAuth nonce、access/refresh token 仅在独立网关加密，平台登录 token 不转发给 MCP。
- 回调跨用户/新会话/过期/不一致重放拒绝；OAuth 保存后仍需 MCP 初始化与发现，不用“授权成功”冒充连接可用。
- 内部 token generation 与平台 authorization binding revision 分离；自动刷新不会换成另一个用户或使正常历史来源失效，重新授权仍建立新 revision。
- 刷新单飞、持久状态、取消后存储写入排空、撤销先 inactive，迟到成功不复活；丢失 rotating-token 回复进入重新授权，不重放 tools/call。
- RFC7009 远端撤销与本地断开分别记录；unsupported/unknown 不冒充远端全部撤销。前端提供安全授权链接、源身份/状态与明确清理提示。
- 真实 HTTP 已验证两位使用者独立 OAuth、短 access token 刷新、各自 Worker 读取、断开/远端撤销及来源失效；仍是合成 AS/模型/数据。
- 详见 [OAuth 契约](../engineering/platform-mcp-oauth-contract.md) 和 [覆盖差额](oauth-slice-coverage.md)。

### 新增：按 Run/连接隔离的 MCP stdio

- 第三方 MCP 程序只在独立 Manager 创建的无网络 cell 中执行；固定 image/dependency/startup-template digest，不接受页面任意 executable/安装命令，不回退 API/Worker/Gateway 宿主 subprocess。
- 同 Run、generation、connection 复用一个进程；发现使用独立短时 cell，不跨用户/Run 复用 HOME、workspace、会话或凭据。compute/stdio 共用节点容量门槛，不能绕开全局 CPU/内存/cell 配额。
- UID10001 执行 MCP，与 UID10000 PID1 watchdog 分离；只读 root、cap_drop/no-new-privileges、无 host bind/Socket、有界 tmpfs/PID/输出/期限。凭据仅由 Gateway 经 exec stdin 短暂注入，不进入 Docker Config.Env/Cmd、宿主文件或 Manager journal。
- 获授凭据的 MCP 程序能读取该凭据，UI/契约明确这一风险；它不是无凭据 compute。当前仅支持 Bearer/匿名，不把 HTTP OAuth 元数据自动转换成 stdio OAuth。
- JSONL 帧、stdout/stderr、累计字节、队列、管道写与 RPC 等待有界；Manager 仅保留 RPC 摘要/生命周期，业务结果由 Gateway 加密。重复 RPC 身份拒绝，不自动重放。
- PG 租约先 claim 精确 Manager 节点，再启动进程；错误节点不能报告销毁。撤权/到期/挂起/终止清理实际 cell；进程失联记录 lost，不能静默重建旧会话。未确认停止继续保留核对阻断。
- 真实 Docker/官方 MCP SDK、PG/Worker/Gateway 及两用户 HTTP 链路已验证；这是无网络合成参考服务，不代表任意第三方联网镜像/供应商系统都已验收。
- 配置、接口和差额见 [stdio 契约](../engineering/platform-mcp-stdio-contract.md)、[stdio 覆盖](stdio-slice-coverage.md) 与 [参考镜像](../../services/mcp-stdio-runtime/README.md)。

### 新增：stdio 读取本次明确授权的附件

- 模板 `input_policy=run_attachments` 和本次 `allow_stdio_attachments=true` 双 opt-in，任意一层缺失都是零附件；不自动读取 Project head 或计算中的 workspace。
- 最多 32 文件、合计 4 MiB；源文件仍按当前权限/项目/来源检查，BlobStore 在事务外核对实际 bytes，发送前再次授权。4 MiB 边界通过，超限不分配执行 intent、不静默裁剪。
- v1 无输入 Spec/digest 不变；v2 固定元数据、UUID 目标路径、SHA 和大小。PG 租约/Manager journal 不复制文件正文，Gateway 只在首次启动短暂转交，不在任何控制宿主解压/解析用户文档。
- Manager 全量核验后，在新 cell 启动 MCP 之前复制文件；同代次复用不重复覆盖副本。MCP 可改变自己的副本，但 BlobStore 原件/Project head 不改变，也没有 stdio 文件发布入口。
- Web 提供默认不选的独立授权复选框；改变所选文件/切换会话复位，丢失回复后保持同一授权值、文件集合与幂等键重试。
- 真实 Docker、PG/Worker/Gateway 与两用户 HTTP 已验证文件读取、未勾选时零文件、损坏/撤权后不启动、跨用户拒绝、原件不变、限额与真实清理。详见 [附件输入契约](../engineering/platform-mcp-stdio-input-contract.md) 与 [本切片任务记录](stdio-input-slice-plan.md)。

### 本轮新增：固定依赖镜像与 Skill v2（本机完整验证通过）

- 已落地独立纯契约包、wheel 版本/文件哈希锁、无网络非 root 构建、依赖目录与受信 Python 分离、实际 inventory/闭包/CycloneDX SBOM/功能 smoke、操作员 Ed25519 审批与独立公钥准入。
- NumPy 2.5.3 / Pandas 3.0.5 / python-dateutil 2.9.0.post0 / six 1.17.0 已在真实镜像里安装和运行；API/Worker 不安装或执行用户的依赖包，用户进程只获得固定只读依赖路径，PID1 不加载 site hooks。
- Skill v2 固定 runtime digest 和精确依赖声明，真实环境检查后继续原隔离验证、不同管理员审核与发布；原 v1 包摘要保持不变。当前环境撤回和混合主计算 profile 会拒绝后续执行/创建，不自动换镜像。
- 管理台可展示环境版本/摘要、导入数字版本的 v2 包；依赖示例、构建/签名命令和明确限度见 [依赖运行时契约](../engineering/platform-dependency-runtime-contract.md) 与 [任务记录](dependency-runtime-plan.md)。下面统计为 2026-09-13 当前代码的本机验证证据；不代表生产上线批准。

### 本轮修复：真实数据库的生命周期与队列竞争

- stdio 停止、检查点 ack、compute 停止观察、系统清理及 Run 控制统一遵守组织→核心资源→Run→生命周期记录的锁序；结构锁不授予业务或私人历史读取权限。
- 真 PG 已在旧实现稳定复现资源/Run 锁反转，以及队列只跳过 Run 却卡在资源/Job 的问题。领取改为有界候选扫描、原子 NOWAIT 前缀和候选 savepoint，繁忙时释放所有部分锁，再检查下一项；取消/过期/延后等当前条件会重新核对。
- 取消、审批、核对仍复核当前权限；组织停用不妨碍安全清理。只将前缀中的 55P03 视为繁忙，不吞掉 40P01/连接故障，也不重试已派发业务动作。
- Docker 并发清理的真实 404 也已复现并修复：只有已核对所属、且再次确认资源不存在时才认定清理完成，假 404、无确认的 409 与其他删除错误仍拒绝；同 binding 清理串行，确认 removing 时有界等待且不重发 DELETE。详见 [Docker 清理契约](../engineering/platform-docker-cleanup-contract.md)。
- 预览诊断只保留有界异常类型/代码位置/状态，不记录原始异常正文、参数、提示词或文件；新的 HTTP 验证会使旧成功报告失效。具体证明、测试与局限见 [生命周期与队列锁序](../engineering/platform-stdio-lock-order.md)。

### 2026-09-14：Skill 归档隔离导入

- ZIP/TAR/TAR.GZ 原始字节进入私有 quarantine，host 不解析成员、不安装或执行归档脚本；固定无网 cell 生成包，停止/清理/ack 后原子创建私有不可变草稿。
- 支持 `skill.json` v1/v2 与原生 `SKILL.md` 文件夹；原生元数据明确填写，frontmatter 只保留为文本，不自动赋予执行能力。导入后仍需现有隔离验证、不同审核人发布和明确共享授权。
- 大小/比例/数量/UTF-8/别名/链接/设备/加密/尾随/重复 JSON/已知 Secret 形状拒绝；并发、撤权、未知结果、GC/配额与清理恢复有 PG 证据。原始归档清理不删除生成的 Skill。
- 新增 43 项真实 Docker scanner 测试、14 项平台归档测试、14 项契约测试与 6 项 Web 测试；该增量完成时（2026-09-14）完整平台 436（`archive-platform-final.xml`）、Manager 136、Web 73（`platform-web.xml`），HTTP 234 项连续两轮通过；平台套件与 Web 套件此后都已扩充，436 / 73 不再是当前规模。HTTP 使用真实隔离执行，但合成模型/IdP，不能冒充公司 UAT。
- 证据：`workbench-archive-http-initial/final.json`、对应 lifecycle、`archive-final-run.json` 和完整 JUnit；汇总/源码与证据哈希在 `var/verification/implementation-progress.json`。格式与边界见 [归档契约](../engineering/platform-skill-archive-contract.md)。
- 不包含任意二进制资产、跨模块执行、全量旧库种子迁移、专业扫描或完整发布/生产 Gate。

### 2026-09-16：组织 / 部门共享预算

- 个人预算仍是必要条件；组织与部门是附加硬上限，不是赠送额或第二本账。同一笔消费同时约束组织和提交时全部有效部门，这些重叠投影不能相加当作公司总账。
- v13 新增 `budget_pools` / `budget_allocations`：固定 scope 投影 + 不可变主体绑定（恰好一个 Run 或一个独立 embedding 意图），六位小数、FORCE RLS、复合组织外键、组织级偏索引与互斥主体约束；未配置上限也保留完整投影。
- 迁移在维护窗口执行：组织期初消费取既有个人消费合计，未结算 hold 按真实 reservation / 独立 embedding 绑定，部门只承接升级时未结算承诺（`migration_hold`），不虚构历史归属；无法对齐的预留或非 USD 一律拒绝升级并保留原始事实，且无丢账 downgrade。
- 迁移身份必须豁免行级安全：FORCE RLS 对表属主同样生效，受限身份会读到零行并静默提交空投影。守卫已提取为可复用的 `app/db/migration_guard.py`：回填前既校验角色属性，也检查「看得到 bootstrap 表却看到零个组织」这一被过滤特征；回填后再由 `_reconcile()` 用独立 `COUNT(*)` 与累计观测值复核 pool 数、期初消费合计与每笔 hold 的 allocation，证明确实读到了数据而非本可读到。两侧都有真 PG 用例（含 `NOBYPASSRLS` 负控）。`0013` 是目前唯一回填数据的迁移；其余迁移只建表，不受此影响。
- 锁序为组织 pool → 部门 pool UUID → 个人预算 → Run / 回执 / allocation；`ensure` / `lock_subject` / `change` 共用同一比较器，`change` 自行取该前缀而不依赖调用方。全仓不用 advisory lock，改账只在短事务内，锁内不调用模型 / embedding / Docker。
- 金额在写入前校验：`NUMERIC(20,6)` 会把第七位小数静默舍入，因此非有限、负数、越界和超精度一律拒绝，不落库。
- Run 准入 / 取消 / 完成 / 恢复 / 未知费用核对与摄取 / 独立查询 / Run 内 embedding 的全部金额路径均已接通；Run 内 embedding 并入该 Run 预留，独立意图单独预留，未发送退款与重复回执不重复计费。真实账单高于保守估计可如实落账，后续付费动作被拒而不是篡改账单。
- 管理 API 仅 `org_admin` 可读写本组织汇总与上限，普通成员与操作员在带正确 CSRF 时写入同样被拒；精度、revision、低于已承诺金额三类拒绝齐备；响应键集正向断言，错误只给受限 scope，不返回他人 prompt / 调用参数 / 凭据。每次生效的上限变更留一条持久审计行，被拒的变更不留行。
- Web 与个人预算同页共存且个人路径未回归：重叠 scope 说明、四态徽标（红 / 琥珀 / 绿 / 中性）、期初消费单列、移除上限需二次确认、409 冲突保留弹窗并刷新 revision。
- 金额展示统一走 `money` / `remainingMoney` 精确小数 helper：服务端十进制字符串原样呈现，可用额度按六位定标整数（BigInt）相减，不用二进制浮点。修掉两处各自的局部实现：「我的用量」页原用 `Number(...).toLocaleString` 并浮点相减，把 `1000000.000000` 显示成带千分位的 `1,000,000.00`、真实费用 `0.0000001` 显示成 `0.00`；管理台「成员任务预算」表原用 `Number(...).toFixed(2)` / `toFixed(6)`，把上限 `9.999999` 向上取整成 `10.00`（虚报硬上限）、`1234567.891234` 截成 `1234567.89`、已消费 `0.0000001` 显示成 `0.000000`，空值还会显示成 `0.000000` 或 `NaN`。两处均改为调用同一 helper，并各补一条按上述金额逐字断言的回归用例；负控还原旧实现即失败。
- 本增量新增预算用例 64 项（含锁前缀负控：错误前缀留下的签名与正确前缀不同）。实际 HTTP 41 条断言、其中 25 条共享预算断言，两套独立干净栈复现；首次真跑的失败在验证脚手架（按原始 JSON 字符串比较 `"0"` 与 `"0.000000"`），不是产品缺陷。
- 不含月度 / 跨币种周期、供应商发票自动同步、全部工具价格、告警投递、财务导出、部门管理权委派、完整用量分析、容量 / HA 与生产 Gate。详见 [共享预算契约](../engineering/platform-shared-budget-contract.md) 与 [任务记录](shared-budget-plan.md)。

### 2026-10-25：持久审计与结构化元数据（GOV-02 Slice A）

- v14 `0014_audit_records`：审计表加 trace/决策/revision/风险/`metadata_schema` 列与 `NOT VALID` CHECK（历史行保持原值并标 `legacy`，所有新写入强制结构化、4 KiB 未压缩上限）；分页索引；outbox 投递簿记列。表数仍为 61。
- 唯一写入口 `observability/audit.record()`：每个 action 一个封闭 pydantic 模型 + outcome 词表，无自由文本字段；旧的 `AdminService.audit` / `PlatformService._audit` 与散落的 `insert(s.audit)` 已移除（12 文件 55 处，54 个 action）。
- 高风险 fail-closed：`prepare_dispatch`、`consume_dispatch`（新增）、审批决定、未知效果核对（新增 `run.reconcile`，只存证据摘要）、审计查询在返回前用 `require_recorded` 校验本次事实；审计不可写即 503 `AUDIT_SINK_UNAVAILABLE` 且无外部效果。
- Runtime 对审计只读+追加、对 outbox 事实列不可改且无 DELETE；启动校验拒绝多余授权。审计查询限 `org_admin`/`auditor`，返回无 `metadata`，每次读取同事务留 `audit.read`。HTTP 请求的 trace 由服务端生成，忽略客户端头。
- 实施中修复：CHECK 中 `':v1'` 被 SQLAlchemy 当绑定参数渲染成 `'NULL'`，导致全部结构化写入被拒（266 个 PG 用例 error）；`test_shared_budget_migration` 的扰动钩子按对象身份匹配 v14 表而失效（7 failed）。两者已修并补回归。
- 未做：`x-aio-sensitive` 与统一出口脱敏（Slice C），审计导出、保留策略。详见 [审计契约](../engineering/platform-audit-contract.md) 与 [任务记录](audit-redaction-plan.md)。

### 2026-10-25：审计归档投递 relay（GOV-02 Slice B）

- `record()` 在同一事务内为每条事实写一条 `audit.archive` outbox 指针（无内容副本）；v15 `0015_audit_archive` 为 v14 已有结构化事实补指针，并加只覆盖该 kind 待投递行的索引。表数仍为 61。
- `observability/archive.AuditRelay`：短事务 `FOR UPDATE SKIP LOCKED` 领取并写租约 → 事务外带超时发送 → 以租约为栅栏记结果；失败按 5s 起翻倍、上限 15 min 退避且不丢弃；错误只存固定码。claim 只锁 outbox 行，不进入组织/Run/预算锁序。
- 投递单元是封闭的 `ArchiveRecord`（类型化列 + 按 action 契约重验的 metadata），sink 必须按 `<org_id>:<audit_id>` 去重；指向不存在或不可投影的事实不发送。
- 两类故障分离：PG 审计写失败仍是 `AUDIT_SINK_UNAVAILABLE` 并拒绝动作；归档不可达只形成 backlog（`AUDIT_ARCHIVE_BACKLOG`，仅日志告警），不影响 Run 执行和只读请求。
- 未做：真实归档/SIEM 适配器、`run_worker.py` 启动 relay、backlog 指标导出与管理 API。部署后指针会在 outbox 中累积，接入适配器后从最早的事实补投。

## 2. 明确尚未完成，不得当作可上线平台

- 工作台与管理台已可操作；外部企业目录同步、部门管理权委派、完整支持访问流程和浏览器视觉验收仍未完成。
- 当前 PostgreSQL schema 是基础版本，不代表原计划所有领域表与业务约束已经实现。
- 后台 single、真实 Python compute、只读 HTTP MCP、配置后的 OAuth、无网络 stdio 与明确附件副本已接通；stdio 受控联网/活动工作区协作、可核对真实写和其他执行器仍未启用。
- Team 和安全审批边界的文件交接已实现；任意时刻的进程/内存恢复、跨节点存储/迁移及完整故障矩阵仍未完成。
- 无网 compute、独立凭据网关和固定离线依赖镜像已实现；Node/浏览器/更多 parser、更多依赖/镜像发布运营、完整生产出口策略和 gVisor/Kata/微 VM 仍未完成。
- 真实 Python 与无网络 stdio 已有独立差量测试，但多语言、浏览器、联网第三方 stdio 不能按这些结果宣称已安全。
- Artifact 字节上传和生成文件下载可用；通用附件的恶意内容扫描/杀毒/安全预览、S3/跨节点对象后端、完整生命周期与孤立 blob 自动清理仍未完成。当前附件不会假称已杀毒，未完成写盘保留配额与内容追踪。
- 知识库的六格式隔离摄取、pgvector/中文检索、文档ACL/引用/删除已实现；OCR/外部源同步、专业扫描、完整大规模生命周期与生产治理仍未完成。
- 个人 Run 结算、unknown 费用核对、模型价格登记、个人预算管理以及组织/部门共享硬上限已实现；供应商账单同步、月度/跨币种周期、告警投递、财务导出、部门管理权委派与更细运营分析仍未完成。
- 持久结构化审计、高风险 fail-closed 与归档投递 relay（仅 fake sink）已实现；真实归档适配器与 relay 进程接入、统一出口脱敏、审计导出与保留策略、支持访问、kill switch、运营监控、备份恢复、HA、灰度/真实业务验收未完成。
- 尚未接入公司真实 IdP、模型、业务系统或生产数据；签名验证测试使用合成 IdP 和真实 JWT 验签。
- G0–G6 的完整放行均未声明通过。普通 GUC RLS 不被描述为能抵御应用 DB 凭据失陷。

## 3. 验证事实与范围

本轮实际在一次性 PostgreSQL 容器执行了平台测试，镜像固定：

`pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`

- **2026-10-25 归档投递增量（当前结论）**：同一远程主机，local-harness 217 个 Python 源文件与本机逐字节一致，`test_sandbox.py` 注入全部镜像后平台套件 **599 tests、0 failures、0 errors、0 skipped**（新增 `test_audit_relay` 12、`test_audit_contracts` 4），Manager 136、runtime-policy 15、document-parser 16 全绿；仅 PG 为 525 passed / 74 skipped。connector-gateway 未改动，3.13 下仍是同一项 TLS 失败（3.12 下见下条 82 passed）。变异测试 9 项杀死 8 项（存活项被 FORCE RLS 兜住，见计划第 6 节）。OpenAPI 无变化。证据 `var/verification/audit-v15/`（平台 XML SHA-256 前缀 `90a9bed4`）。计划估计本片 20–25 条用例，实际新增 16 条。
- **2026-10-25 审计增量（Slice A）**：在用户提供的远程 Linux 主机（Docker 29.8.2、Python 3.13.5，非本机、非 CI）上，以与本机逐字节一致的 321 个 Python 源文件运行 `scripts/platform/test_sandbox.py`：平台套件 **583 tests、0 failures、0 errors、0 skipped**（含 `test_audit_integration` 31、`test_audit_contracts` 40），Manager 136、runtime-policy 15、document-parser 16 全绿；`test_postgres.py` 仅 PG 为 506 passed / 74 skipped（skip 均为未注入镜像）。connector-gateway 在 3.13 下 1 failed（`test_real_tls_keeps_original_sni...`：3.13 默认 `VERIFY_X509_STRICT` 拒绝缺 AKI 的测试证书，与本增量无关），在 CI 同版本 Python 3.12.15 下 **82 passed**。同一套件前一轮出现过一次 `test_uncertain_effect_stops_whole_team_without_blind_replay` 失败（invocation 查询为空），单独 8 次与再次全量均通过，未定位根因，按偶发记录。本机：ruff、local-harness 411 passed（PG 用例 skip）、sandbox-lite 24、Web 126、`tsc -b`、compileall、pip check 通过；OpenAPI 与 `generated.ts` 已重新生成（新增审计查询参数）。证据 `var/verification/audit-v14/`（平台 XML SHA-256 前缀 `8fe9a79e`）。未重跑真实 HTTP 端到端脚本与 `npm audit`。
- 以下为 2026-09-16 共享预算增量的历史结果。平台套件：当时已由 `scripts/platform/test_sandbox.py` 构建并注入全部镜像后完整运行，**500 tests、0 failures、0 errors、0 skipped**（证据 `var/verification/platform-postgres.xml`），覆盖契约、真实 PostgreSQL/Worker/权限/上传、固定依赖、标准计算、Skill、知识库、Team、stdio/附件、队列/生命周期锁序及本增量的共享预算（`test_shared_budgets` 21、`test_shared_budget_contracts` 27、`test_shared_budget_migration` 7、`test_budget_lock_order` 9，共 64 项）。仅跑 `scripts/platform/test_postgres.py`（不构建镜像）时为 500 collected、426 passed、74 skipped（证据 `var/verification/final-verify-platform.xml`）：`AIO_TEST_COMPUTE_IMAGE` 系列 48（真实计算 27、归档导入 14、Skill 执行 6、MCP/compute 边界 1）、`AIO_TEST_STDIO_IMAGE` 12、`AIO_TEST_DOCUMENT_IMAGE` 9、`AIO_TEST_DEPENDENCY_PROFILE` 5，skip 不等于通过，需注入镜像后才实际执行。此前 **436 tests** 属于上一（Skill 归档）增量的较小套件，不是本轮结论。本轮修复过两批失败，均在用例侧、且都已在上述全绿运行中复跑通过：`test_queue_expiry_recovery_releases_every_scope_exactly_once` 前置常量写错（准入占额是 manifest 的 `run_budget` 0.1，而非单次模型调用上限 0.02，失败证据 `var/verification/gt-baseline-nogate.xml`）；`test_CONTROL_wrong_prefix_is_rejected` 的 `inverted_pools` / `no_pool_locks` 两个负控参数（失败证据 `var/verification/gt-postfix-platform.xml`）。不能把全部平台用例都称为 Docker 用例。
- Manager/隔离套件：**136 tests，0 failures，0 errors，0 skipped**；包括标准隔离、stdio、固定依赖真实镜像与恶意 wheel 拒绝，以及对应契约测试；新增 17 项真实 Docker 资源及故障注入的并发清理/404/409/故障保留回归。
- 独立运行时策略契约：**15 passed**；覆盖签名、独立信任根、test/production 分离、内容篡改和固定清单边界。
- 文档 parser 契约：**16 passed**；平台套件另包含 9 项实际 Docker 六格式/活动内容拒绝链路，不能把 host 合成夹具测试当作真实文档隔离证据。
- 独立网关：**82 tests，0 failures，0 errors，0 skipped**，含官方 MCP SDK 服务端、真实 HTTP/TLS 互操作与 stdio/输入委派边界。
- 凭据网关镜像真实启动 smoke 通过：UID10002、只读 root、无 Docker Socket、独立私有卷；该 smoke 使用 network=none，不冒充生产出口/HA 验收。
- 证据：`var/verification/shared-budget-final-gated.xml` 与 `platform-postgres.xml`（同一份注入全部镜像的 500/0/0/0 运行，suite timestamp `2026-09-16T13:33:01`）、`final-verify-platform.xml`（同代码的仅 PG 运行 500/426/74）、`sandbox-manager.xml`、`final-web.xml`、`connector-gateway.xml`、`connector-image.json`、`document-parser.xml`、`document-profile.json`、`stdio-profile.json`、`runtime-policy.xml` 和 `sandbox-profile.json`；均为本机验证产物。较早的 `gt-platform-postgres.xml`（469/395/74）属于套件扩充前的快照，`platform-web.xml`（73）属于本增量前的 Web 规模，两者都不是当前结论。CI 已配置相同验证入口及报告上传，但没有把尚未执行的远程 CI 当作已通过。 新增依赖构建、SBOM/签名、锁序回归与两轮 HTTP/Lifecycle 报告的路径和 SHA-256 已归集到 `var/verification/implementation-progress.json`。
- 真实 PG 覆盖 v1→v13 升级保留（含 `0012_skill_imports`→`0013_shared_budgets` 保留原 hold、不虚构历史部门支出、余额不可核对时拒绝升级）、runtime 最小权限、RLS/外键、事务池清理、跨用户/组织、幂等/预算竞争、Run/验证 Job 租约、双人审批、当前部门授权、未知效果与费用核对、不可变 Skill 发布与来源撤回，以及 Team 阶段/步骤归属和 stdio 身份/节点/代次绑定。
- 新增后台完整路径与故障证据：模型→工具→模型完成、审批释放 Worker/新 Worker 恢复、拒绝审批不执行、派发前丢 lease 可恢复、派发后未知效果不重排、派发并发只发一份 permit、结果/游标失败同事务回滚、当前 Tool/批准者撤权、unknown 费用 hold/迟到账单幂等调整、未确认清理不能解除 blocker、取消中的心跳中断、未知 checkpoint 版本拒绝重跑。
- 模型 HTTP 使用 MockTransport；业务副作用测试使用合成 EffectSink。新增 Python 产物链路中的代码、容器、配额、文件、数据库和授权是真实执行；未调用真实模型供应商或公司业务系统。
- 当前证据仅支持已测试的 Python/parser/stdio/配置边界；不证明未知内核漏洞不存在，不证明其他执行器、知识库完整生命周期、生产 SSO/HA 或外部业务 exactly-once 已完成。
- 现有 Harness 回归：142 passed，0 skipped（包含补装既有可选 MCP 依赖后的 3 项测试）。
- 现有 Sandbox：24 passed；旧前端 jsdom：45 passed。新工作台：**126 passed**（含共享预算 6、badge 色调 30、金额精度 19、我的用量与管理台成员预算金额回归各 1）；TypeScript/生产构建/Prettier 通过；官方 npm audit **0 已知漏洞**。ruff、pip check、compileall 通过；pip check 不等于 Python 漏洞审计。
- 真实 HTTP 端到端：本增量为 **41 项检查（其中 25 项共享预算）在两套独立干净栈连续通过**，证据 `var/verification/shared-budget-http-current.json` 与 `shared-budget-http-current-confirm.json`（两份均 `status=passed`、`real_financial_reconciliation_verified=false`）。下述 **234 项检查连续两轮通过** 是 2026-09-14 归档增量的历史结果（`workbench-archive-http-initial/final.json`），本增量未重跑该全量脚本：覆盖四个合成 SSO 身份、部门隔离、实际 Worker/Manager/Docker、Skill/MCP/知识库、混合检索与引用、个人身份隔离、下载和删除撤权，以及 compute/MCP/知识库三条 Team 路径和计算→第二身份审批→新代次恢复文件的交接路径。R2 为明确合成回执，不是业务写入证明。还包含两用户 OAuth、刷新、令牌隔离与远端撤销，以及两用户 stdio 发现/运行/身份隔离/停止、明确授权后的文件副本读取和未同意时零文件。模型/IdP/MCP/OAuth 源数据是合成的；公司真实接入尚未验证。 另含固定依赖 Skill 的实际 NumPy/Pandas 执行、精确 CSV 字节和另一用户下载拒绝；两轮均为全新有限寿命栈，并核实自有服务清理。
- 实际 OpenAPI 为 **90 条路径**：已核对签入的 `docs/api/platform-v2.openapi.json` 与 `scripts/platform/export_openapi.py` 的现场导出逐字节一致；`web/platform/src/api/generated.ts` 由 `openapi-typescript` 现场重新生成后亦逐字节一致（SHA-256 前缀 `5f3e172e`），契约与生成客户端均未落后于代码。不是把规划接口总数当作已实现接口。

- 本轮自有验证容器/卷已清理；没有操作其他用户的 Docker 服务，已构建的验证镜像保留用于复现。
- 浏览器视觉检查仍未完成：本轮重试浏览器工具返回 `Codex auth token is unavailable`；未用其他自动化绕过，也没有把 HTTP/jsdom 写成视觉 QA。

## 4. 如何复现（项目目录运行）

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/local-harness/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -r apps/local-harness/requirements-mcp.txt
.\.venv\Scripts\python.exe -m pip install -e packages/runtime-policy -e services/sandbox-manager
.\.venv\Scripts\python.exe -m pip install -e "services/connector-gateway[test]"
.\.venv\Scripts\python.exe -m pip install -e services/document-parser

docker pull pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f
.\.venv\Scripts\python.exe scripts/platform/test_sandbox.py

.\.venv\Scripts\python.exe -m pytest apps/local-harness/tests --ignore=apps/local-harness/tests/platform -q
.\.venv\Scripts\python.exe -m pytest apps/sandbox-lite/tests -q
.\.venv\Scripts\python.exe -m ruff check apps tools scripts
```

平台测试脚本生成临时随机数据库密码/运行账号、迁移到空库，再运行测试。无 Docker 或未拉镜像时明确失败；不用 SQLite/mock 顶替真实数据库结论。直接跑 pytest 而未设隔离 PostgreSQL 时，相关集成测试会明确 skip，不能算通过。

只跑 `scripts/platform/test_postgres.py` 时它仅注入 `AIO_TEST_POSTGRES_URL`，依赖真实镜像的用例会按四个变量分别 skip：`AIO_TEST_COMPUTE_IMAGE`（真实计算/Skill/MCP 边界与归档导入）、`AIO_TEST_STDIO_IMAGE`、`AIO_TEST_DOCUMENT_IMAGE`、`AIO_TEST_DEPENDENCY_PROFILE`。这四个变量由 `scripts/platform/test_sandbox.py` 构建镜像后注入，因此只有它能让整套用例都实际执行。读 `-ra` 的 skip 原因即可区分“镜像未注入而跳过”和“已通过”，不要把 skip 计入通过。

## 5. 当前新增启动入口和限制

- API：`apps/local-harness/run.py`，显式 platform 模式使用 v2；部署先执行迁移到 `0015_audit_archive`（需 RLS 豁免的迁移身份，因为它为既有事实补投递指针），再由操作员刷新 `grant_runtime_access`（v14 起会收回 outbox DELETE 与事实列 UPDATE；按代码，未刷新的 v13 授权会使启动校验失败，该升级顺序本身未单独实测）。CLI 为 `scripts/platform/manage_platform.py`，不在 API 启动时自动 bootstrap。
- Worker：`apps/local-harness/run_worker.py`。配置模板为 `config/platform-worker.env.example`；不自动读取旧 `.env`，不加载个人 Codex/其他代理配置。
- 模型/工具/Agent、成员/部门、预算与授权可通过管理页面配置。Skill 由私有草稿、隔离验证、不同审核人发布后引用；第三方通讯录同步尚未完成。
- 默认没有未经配置的执行器。显式 manager/storage 配置后可用 sandbox.python；Manager 的服务凭据与 control-authority 凭据不同，计算 cell 不持有它们。
- Manager 启动/权限与 profile 配置见 [Manager README](../../services/sandbox-manager/README.md)，生成的测试 image digest 在 `var/verification/sandbox-profile.json`。
- stdio 额外配置 Manager 的 `SANDBOX_STDIO_PROFILES` / `SANDBOX_CONNECTOR_TOKEN` 和 Gateway 的 `CONNECTOR_STDIO_MANAGER_URL` / `CONNECTOR_STDIO_MANAGER_TOKEN`；专用 token 不能调用普通 compute API，反之亦然。`export_stdio_endpoint.py` 从审核 profile 导出一致引用。
- 代码契约见 [Worker](../engineering/platform-worker-contract.md)、[沙箱/产物](../engineering/platform-sandbox-contract.md)、[管理台/Web](../engineering/platform-admin-web-contract.md)、[Skill](../engineering/platform-skill-contract.md)、[MCP](../engineering/platform-mcp-contract.md)、[知识库](../engineering/platform-knowledge-contract.md)、[Team](../engineering/platform-team-contract.md)、[文件检查点](../engineering/platform-workspace-checkpoint-contract.md)、[OAuth](../engineering/platform-mcp-oauth-contract.md)、[stdio](../engineering/platform-mcp-stdio-contract.md)、[stdio 附件输入](../engineering/platform-mcp-stdio-input-contract.md)、[审计](../engineering/platform-audit-contract.md)。

## 6. 下一条实际关键路径

1. 在已验证的文件交接、无网络 stdio 和显式附件副本上继续完成受控联网、更多批准依赖环境及发布运营、活动工作区协作、更多运行时的独立安全差量；不要把 file-only 检查点当作任意进程快照或 HA，也不把标准 Python 镜像的结果外推到任意第三方镜像。
2. 在已实现的标准 OAuth/stdio 上补齐供应商扩展、其他传输、二进制产物、可核对真实写和完整保留/限流治理；协议路径通过不代替这些任务。
3. 在已完成归档导入上补齐 Skill 二进制资产/跨模块/种子迁移、token 上下文预算和完整发布治理，不把文本 v1 或固定依赖 v2 当成全部 CAP 任务。
4. 扩展知识源/OCR、更多语言/浏览器/parser profile、受控依赖安装、规模检索质量/性能与更强隔离选型。
5. 在已实现的组织/部门共享硬上限上补齐月度/跨币种周期、供应商发票对账、告警投递与财务导出、部门管理权委派；以及支持访问、完整保留/孤立对象清理、共享存储、监控/备份/恢复/HA。
6. 进行浏览器视觉与业务旅程验收，接入公司真实 IdP/模型/业务系统，执行全部适用安全/故障/生产 Gate、灰度和交接。

完整目标仍未完成；不以一条已跑通的 Skill 路径或绿色测试套件替代完整企业平台。
