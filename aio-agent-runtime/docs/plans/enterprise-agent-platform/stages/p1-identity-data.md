# P1：身份、数据、权限与平台基础

> 父任务：DAT-01～06、IAM-01～10、UI-01～02，共 18 项。全部待实施。阶段目标是身份与资源边界，不是开放任意执行。

## 1. 进入条件、范围与迁移批次

进入：G0 的对象/安全/数据契约可采用；SSO 测试租户、PG、对象存储有负责人与最小测试权限。外部身份源暂缺时只能用隔离测试 issuer，不代替真实 SSO 验收。

建议迁移顺序：M0001 身份和组织；M0002 项目/resources/grants 与最小 Session；M0003 Run/事件/审批/job/版本引用骨架；M0004 upload/artifact/SecretBinding；M0005 RLS/业务约束加强。真实编号由实现时确认，统一一个 Alembic head，不能各组各维护一条互斥主迁移线。

新表在授权实现之前保持默认拒绝。P1 的 G1 只覆盖已开放 API；P2/P3 新加 Run/工具/知识路径必须扩展同一授权 suite，不能沿用旧结果免测。

## 2. 数据基础任务卡

<a id="dat-01"></a>

### DAT-01 — PostgreSQL、事务和迁移入口

**位置/契约**：`APP/db/engine.py`、`MIG/`、测试 PG 配置；业务 API 使用应用角色，迁移用独立账号。

- [ ] **DAT-01.01** 锁定数据库驱动/ORM/迁移版本，统一 async 或明确的线程边界，避免在 async handler 阻塞数据库调用。
- [ ] **DAT-01.02** 创建独立应用、迁移和队列调度角色；应用不得是 owner/superuser/BYPASSRLS，也不得 SET ROLE 到高权限账号。
- [ ] **DAT-01.03** 配置连接池、连接/语句/事务超时、TLS 与健康检查；数据库 URL 只来自 Secret/受控部署配置。
- [ ] **DAT-01.04** 建立单入口迁移与 revision 检查，API 启动只验证兼容，不由每个 worker 自动改 schema。
- [ ] **DAT-01.05** 添加临时测试数据库、事务回滚夹具和迁移空库→当前版本的测试；隔离测试不使用生产 schema。
- [ ] **DAT-01.06** 记录升级前备份点、expand-contract 边界及失败处理；破坏性迁移禁止自动 downgrade 删除业务事实。

**验收**：迁移可重放、应用最小角色可连接但不可提权；AUTH-08、OPSTEST-09。**PR/回滚**：驱动/基础设施与首批迁移分开；关闭 v2 路由保留数据，不回退匿名 SQLite。

<a id="dat-02"></a>

### DAT-02 — 组织、项目、资源与授权实体

**位置/契约**：`APP/db/models/identity.py,resources.py`、`MIG/versions/`；跨实体使用同 org 复合外键。

- [ ] **DAT-02.01** 实现 org、user、membership、department 多对多，用户主标识用 issuer+subject，不用会变的邮箱。
- [ ] **DAT-02.02** 实现 project/member、resource/grant，默认 private，管理员范围不能超过组织策略。
- [ ] **DAT-02.03** 为引用关系添加同 org FK/唯一键、必要索引、UTC 时间与 revision；禁止依赖调用方约定同组织。
- [ ] **DAT-02.04** 补最小 sessions/agent 版本引用所需 schema 或相容迁移，避免 IAM-05 引用尚不存在的表；业务发布功能留给 CAP-06。
- [ ] **DAT-02.05** 定义资源类型与领域实体一致性、删除/停用规则；身份退出不删除历史审计操作者。
- [ ] **DAT-02.06** 用双组织 fixture 测正常创建、跨 org 关联、重复 external ID、多部门成员、Grant 到期。

**验收**：数据库拒绝错误关联，未授权资源不默认公开；AUTH-05/08/10/12。**PR/回滚**：按身份/资源两次迁移；新增列先兼容，不把旧共享数据自动分配到某用户。

<a id="dat-03"></a>

### DAT-03 — Run、审批、事件与 checkpoint 持久结构

**位置/契约**：`APP/db/models/runtime.py`、`MIG/versions/`；这里建结构和约束，状态业务在 RUN 系列完成。

- [ ] **DAT-03.01** 创建 runs、steps、tool_invocations、approvals，记录 actor/project/session 与状态 revision。
- [ ] **DAT-03.02** 创建 jobs、lease/generation、run_events、outbox、idempotency_keys，确定序号/幂等键唯一范围。
- [ ] **DAT-03.03** 创建 run_checkpoints 及内容引用字段，记录 engine schema/cursor/restartability，完整提交后才可读为恢复点。
- [ ] **DAT-03.04** 补 Run 依赖的最小 Agent/Manifest/模型配置版本引用，以及预算预留扩展点；发布管理和账本业务不在本卡重复实现。
- [ ] **DAT-03.05** 对活跃 Run、待审批、逻辑工具调用和任务 lease 添加必要唯一约束，迁移前先处理异常既有行。
- [ ] **DAT-03.06** 测事务失败、重复事件、重复 logical_call_id、非法 org 引用和并发插入；schema 能支撑后续 fencing。

**验收**：RUNTEST-01/03/04 的数据约束测试可运行，但不把 schema 测试当完整 Worker 验收。**PR/回滚**：大 schema 分独立兼容迁移，不先写“万能 JSON 表”省掉关键约束。

<a id="dat-04"></a>

### DAT-04 — 受控对象存储与上传槽

**位置/契约**：`APP/workspaces/storage.py,uploads.py`、artifact/upload slot 表；对象 key 由后端生成。

- [ ] **DAT-04.01** 划分 quarantine、candidate、published、versioned 逻辑前缀/桶和最小服务账号，不给浏览器全桶访问。
- [ ] **DAT-04.02** 定义 StorageBackend 的 put/get/head/delete/条件写契约和错误；本地测试适配器不自动用于生产。
- [ ] **DAT-04.03** 实现 upload slot：org/user/project/purpose/max_bytes/expiry/一次性完成，支持流式计数与 hash 校验。
- [ ] **DAT-04.04** 校验实际大小、Content-Type/文件名、已获权项目，初始对象进入 quarantine；扫描器尚未就绪时保持不可公开。
- [ ] **DAT-04.05** 实现有界分段上传、重复 complete、失败分片和到期槽清理；不信任客户端提供 object_key。
- [ ] **DAT-04.06** 为后续 ArtifactService 提供不可变对象和短期范围下载能力；严格即时撤权需求走授权代理。
- [ ] **DAT-04.07** 测跨用户完成/下载、伪造长度、过期、重复提交、存储失败和中断清理。

**验收**：AUTH-05、SBXTEST-11、GOVTEST-09；仅验证上传存储，不在 P1 控制服务解析 Office/PDF。**PR/回滚**：停新上传但保留已确认引用；删除必须验证资源归属和精确 key。

<a id="dat-05"></a>

### DAT-05 — 旧数据盘点与迁移映射设计

**位置/契约**：`SCRIPT/import_legacy.py` 的 inventory/dry-run 接口与映射 schema；真实迁移在 REL-01。

- [ ] **DAT-05.01** 只读盘点 SQLite schema、WAL 模式、会话计数、共享 workspace 文件和现有 Skill/模型配置来源。
- [ ] **DAT-05.02** 定义 source+legacy_id、org/user/project 显式映射格式，允许 quarantine/unassigned，不自动猜所有者。
- [ ] **DAT-05.03** 设计一致备份接口与校验流程，活跃 WAL 不能只拷主数据库文件。
- [ ] **DAT-05.04** 实现 dry-run 的冲突/缺失/重复/非法权限报告，输出数量与 hash 而非正文/Secret。
- [ ] **DAT-05.05** 定义幂等导入键、批事务、可恢复游标与原始来源记录；历史未知身份不能伪造归属。
- [ ] **DAT-05.06** 在合成 legacy fixture 上测试两次 dry-run 一致、无主数据隔离和源数据不变。

**验收**：OPSTEST-07/08 的设计与 fixture；不动真实旧库。**PR/回滚**：工具与映射文档独立；无生产 import 按钮，未经 REL-01 审查不执行。

<a id="dat-06"></a>

### DAT-06 — Request/Job 数据库上下文和连接池卫生

**位置/契约**：`APP/db/context.py,repositories/base.py`；每个 request/job 的上下文与事务共同结束。

- [ ] **DAT-06.01** 定义从 Principal/RunContext 到数据库 org/user 的参数化设置接口，禁止字符串拼接 SQL 或来自请求 body 的 org。
- [ ] **DAT-06.02** 使用事务本地设置，commit/rollback/取消都释放连接；无上下文查询默认拒绝。
- [ ] **DAT-06.03** 统一 repository 的 org/scope 参数，禁止随手开放全局 get(id) 给业务 handler。
- [ ] **DAT-06.04** 定义 Worker 的上下文恢复与调度器特殊角色；调度器只能读队列元数据，不能顺便读取跨 org 正文。
- [ ] **DAT-06.05** 对超时、异常、嵌套事务、并发协程和连接池复用写压力夹具。
- [ ] **DAT-06.06** 增加审计/trace 关联但不把 token 放到数据库日志；验证连接归还后的默认身份为空。

**验收**：AUTH-07/08，两个组织交替复用同连接不能串行。**PR/回滚**：上下文与 Repository 同步迁移，不能回退成无 scope 查询。

## 3. 身份与权限任务卡

<a id="iam-01"></a>

### IAM-01 — Principal、角色和授权词汇

**位置/契约**：`APP/auth/principal.py`、`APP/policy/types.py`；不可变 Principal，显式 action/resource。

- [ ] **IAM-01.01** 实现 org/user/auth_session/membership_revision/auth_level/service_actor 字段，不含 Secret。
- [ ] **IAM-01.02** 定义员工、项目管理员、部门管理员、维护者、审批者、运维、审计、应急角色的动作集合。
- [ ] **IAM-01.03** 明确 org→部门/项目→资源的上限相交规则，多部门成员不自动合成更大的外部系统权限。
- [ ] **IAM-01.04** 将 Session 私有、Project 成员、Artifact 分享、连接拥有者和支持访问分开建模。
- [ ] **IAM-01.05** 定义服务代理时 original_actor 与 service_actor 的区别，审计不能所有请求都记成 system。
- [ ] **IAM-01.06** 生成 role/action/resource fixture 和默认拒绝测试，非法/未知动作返回稳定 reason_code。

**验收**：AUTH-06/10/11；授权词汇能覆盖所有 v2 API。**PR/回滚**：类型和策略测试先合并，外部字段变更版本化。

<a id="iam-02"></a>

### IAM-02 — 企业登录、BFF 会话和 CSRF

**位置/契约**：`APP/auth/oidc.py,sessions.py`、`APP/api/v2/auth.py`；浏览器仅拿安全会话 Cookie。

- [ ] **IAM-02.01** 按固定 issuer/discovery 配置初始化 OIDC，选择维护良好的协议库，校验回调域名和跳转白名单。
- [ ] **IAM-02.02** 实现 state/nonce/PKCE、issuer/audience/expiry 校验和一次性授权交换；不以未验证 JWT claims 创建用户。
- [ ] **IAM-02.03** 创建可撤销 BFF auth session，登录时轮换 session ID，Cookie 使用 Secure/HttpOnly/明确 SameSite。
- [ ] **IAM-02.04** 为写 API 实现 CSRF/Origin 验证，退出是受保护动作；CORS 只允许明确来源。
- [ ] **IAM-02.05** 处理过期、退出、登录失败、组织未分配、时钟偏差、JWKS 缓存/轮换与身份服务中断。
- [ ] **IAM-02.06** 测错误 issuer/aud、回调重放、state 混用、跨用户会话固定和无 CSRF 审批请求。
- [ ] **IAM-02.07** 禁生产全局 Harness Token 登录路径；单机调试 Token 只能在显式 legacy-local。

**验收**：AUTH-01/02/03/09、UITEST-01；Secret/token 不存 localStorage。**PR/回滚**：关闭平台登录/显示维护状态，不放开匿名作为应急方案。

<a id="iam-03"></a>

### IAM-03 — 成员同步、停用和多部门变更

**位置/契约**：`APP/auth/provisioning.py`、成员同步 job；外部身份源为事实来源之一，审批内授权仍受组织策略。

- [ ] **IAM-03.01** 建立 issuer+subject/外部 group ID 映射，处理用户改名、改邮箱、多部门和退出重入。
- [ ] **IAM-03.02** 实现增量或全量同步游标、重试和幂等 upsert；同步失败不自动删除全部用户。
- [ ] **IAM-03.03** 对停用/离职先撤销 auth session、成员资格、后续任务能力，再异步清理连接与通知。
- [ ] **IAM-03.04** 增加 membership_revision，组变化触发权限缓存失效与任务再检查；已发送外部请求不可假称撤销。
- [ ] **IAM-03.05** 定义 orphan owner/project 的管理员接管程序，不把私人对话自动转成全组织可见。
- [ ] **IAM-03.06** 测乱序/重复组事件、用户停用后旧 Cookie、新登录、已排队任务与长 SSE。

**验收**：AUTH-09/12；停用链路有可追踪事件。**PR/回滚**：暂停同步并保守拒绝未知身份；恢复同步不能复活已人工禁用账号。

<a id="iam-04"></a>

### IAM-04 — 默认拒绝的 PolicyService

**位置/契约**：`APP/policy/service.py,decisions.py`；返回 allow/deny/approval_required 与当前策略版本/约束。

- [ ] **IAM-04.01** 为每个资源动作定义输入 facts 和上限：组织、项目、拥有者、Grant、数据级别、连接 scope。
- [ ] **IAM-04.02** 实现 deny-by-default、Grant 有效期、停用/禁用、部门边界与组织硬约束相交。
- [ ] **IAM-04.03** 分离 list 可见范围与 detail/action 决定；禁止先查全表后由前端过滤。
- [ ] **IAM-04.04** 将 risk/approval 要求与实际授权分开，第三方工具自报 read-only 不覆盖平台风险。
- [ ] **IAM-04.05** 固定 reason_code、policy revision、obligations，隐藏未授权资源存在性；日志只记最小事实。
- [ ] **IAM-04.06** 加入参数化策略测试，未知资源类型/状态/角色/过期上下文一律拒绝。
- [ ] **IAM-04.07** 为新工具/知识/支持接口预留统一入口，而非在每个路由重新写不同的 if-admin。

**验收**：AUTH-04/05/10/12，CAPTEST-02；决策可解释且不可被模型字符串覆盖。**PR/回滚**：策略回退也须保留组织安全上限，默认 deny 不可回退成 allow。

<a id="iam-05"></a>

### IAM-05 — v2 会话、项目和文件资源授权

**位置/契约**：`APP/api/v2/projects.py,sessions.py,artifacts.py` 与 repositories；去除全局文件浏览假设。

- [ ] **IAM-05.01** 实现按 org/owner/grant 的分页列表，稳定排序、cursor、字段最小化，批量和导出同样受 scope。
- [ ] **IAM-05.02** 创建 Session 时验证项目和模板引用；未知 session_id 不自动创建为用户指定 ID。
- [ ] **IAM-05.03** 更新/删除使用 revision 和对象授权；有活跃 Run 时拒绝或先走受控取消，不直接删任务事实。
- [ ] **IAM-05.04** 文件访问改为 project/artifact/version 引用，路径仅在获权资源内部解析，禁止宿主绝对路径。
- [ ] **IAM-05.05** 在 parser/产物发布尚未完成时保持原始 quarantine 下载受限；返回明确 not_ready，不走旧 Sandbox 下载旁路。
- [ ] **IAM-05.06** 保证 Project 共享不自动公开 Session，Artifact 的授权不能靠文件名或 URL 难猜。
- [ ] **IAM-05.07** 写所有列表/详情/修改/删除/下载的双用户负例和一致错误契约。

**验收**：AUTH-04/05/12；新加资源类型必须补同矩阵。**PR/回滚**：按资源逐路由迁移，生产禁止旧 `/api/files` 兜底。

<a id="iam-06"></a>

### IAM-06 — RLS、防跨组织关联与专用角色

**位置/契约**：RLS 迁移、`APP/db/`、测试 SQL；RLS 防跨 org，细粒度动作仍由 PolicyService 控制。

- [ ] **IAM-06.01** 给每个租户业务表 ENABLE/FORCE RLS，USING/WITH CHECK 同时限制读写，无 org 上下文默认无行。
- [ ] **IAM-06.02** 验证应用角色非 owner/BYPASSRLS，不能调用授予的函数或连接到高权限角色绕过策略。
- [ ] **IAM-06.03** 使用 org 复合 FK 拒绝跨组织关联，补遗漏表和导出/归档查询，不只保护 sessions。
- [ ] **IAM-06.04** 为调度器和审计导出设计专用最小角色，逐项列出跨组织元数据操作，不给普通 API 全局读取权限。
- [ ] **IAM-06.05** 在连接池、事务回滚、后台 job、批量更新和并行请求下验证实际行可见性。
- [ ] **IAM-06.06** 将 RLS 负例加入迁移 CI；新表创建若缺 org/RLS/复合关联则测试失败。

**验收**：AUTH-07/08，不能只 mock repository。**PR/回滚**：RLS 启用前先验证角色；出现问题关闭业务访问排查，不关闭 RLS 恢复服务。

<a id="iam-07"></a>

### IAM-07 — SecretRef、内部解析与配置命令封堵

**位置/契约**：`APP/secrets/`、SecretBinding 表、当前 `APP/llm/providers.py` 的生产入口防护。

- [ ] **IAM-07.01** 选择公司现有 Secret/KMS/Vault 等后端和测试 fake；不要自建缺乏审计的明文密钥表。
- [ ] **IAM-07.02** 定义只含引用的 SecretBinding：owner、用途、允许主机/scope、revision、到期，密钥本体不进业务响应。
- [ ] **IAM-07.03** 实现按服务/调用者授权解析，限制每个组件能读的 binding；凭据缓存短期且按身份和版本分区。
- [ ] **IAM-07.04** 在生产调用旧 provider 解析器之前拒绝 `!shell`、任意 endpoint 和字面量配置入库；不先执行再检测。
- [ ] **IAM-07.05** 轮换/撤销触发旧客户端关闭，错误/headers/env/URL/诊断包采用结构化脱敏。
- [ ] **IAM-07.06** 模拟 Secret 服务不可用时明确失败，不回落到其他 Provider Key、管理员 Token 或本地环境通用密钥。
- [ ] **IAM-07.07** 测跨 org/用户解析、expired binding、日志泄漏、配置注入和旧环境兼容边界。

**验收**：GOVTEST-04、MCPTEST-12、SBXTEST-03 的凭据前置。**PR/回滚**：生产可禁用连接/模型，不用旧共享密钥作为回退。

<a id="iam-08"></a>

### IAM-08 — 撤权版本与实时再授权

**位置/契约**：`APP/policy/revisions.py,revocation.py`；通知是加速信号，权威判定仍在 PG/策略服务。

- [ ] **IAM-08.01** 为 org/member/resource/connection 禁用或 Grant 修改统一递增 revision，并在同事务保存失效事件。
- [ ] **IAM-08.02** 缓存键包含 scope/revision；通知丢失也不能令权限长期停留在旧版本。
- [ ] **IAM-08.03** 定义 API、工具、模型、SSE、下载的再检查钩子，新增动作先检查身份和资源当前状态。
- [ ] **IAM-08.04** 注册待取消 Run/关闭连接/撤销短期 capability 的后续动作；P2 接入真实 Worker/manager 后验证，不在 P1 假称进程已停止。
- [ ] **IAM-08.05** 明确已展示、已下载、已发送远端内容无法物理收回；新数据发送必须受撤权约束。
- [ ] **IAM-08.06** 测权限改变、Redis 断开、旧 JWT/Cookie、两实例缓存、任务排队期间停用。

**验收**：AUTH-09、GOVTEST-06，P2/P3 扩展 SSE/工具/知识路径。**PR/回滚**：失效机制出错时禁相关动作，不允许延长旧权限作为兜底。

<a id="iam-09"></a>

### IAM-09 — 审批人与支持访问的独立授权

**位置/契约**：`APP/policy/approvals.py,support.py`、support_grants schema；这里只建权限与范围，执行中心在 RUN/GOV。

- [ ] **IAM-09.01** 定义谁能看审批摘要、谁能批准、何时要求与发起者不同，限制业务系统和资源范围。
- [ ] **IAM-09.02** 明确项目/部门管理员不自动是所有业务写审批人，运维不自动能看正文。
- [ ] **IAM-09.03** 定义 support grant 的 run/resource/field/time/用途与批准者，默认只允许脱敏元数据。
- [ ] **IAM-09.04** 定义 break-glass 强认证、双人/安全批准、到期和使用审计，不作为普通工作账号。
- [ ] **IAM-09.05** 设计审批内容最小化，敏感参数可分层显示，批准人不能借审批读取全部会话。
- [ ] **IAM-09.06** 测自批限制、越部门批准、到期支持授权、复制 grant 到其他 Run、应急权限自动失效。

**验收**：AUTH-11、RUNTEST-10、GOVTEST-07。**PR/回滚**：默认撤销支持权限；不为排障临时创建无到期的管理员读取旁路。

<a id="iam-10"></a>

### IAM-10 — 身份与资源隔离集成门禁

**位置/契约**：`HTEST/integration/test_identity_matrix.py,test_rls.py`；使用真实 PG 和假 OIDC 协议服务。

- [ ] **IAM-10.01** 把角色×动作×资源×归属×到期条件组合成数据驱动矩阵，覆盖直接 API 和批量列表。
- [ ] **IAM-10.02** 执行真实 OIDC 错误/重放/CSRF/退出/停用测试，不只 mock 一个已通过的 Principal。
- [ ] **IAM-10.03** 复用连接池跑两个 org，注入事务超时/异常/取消，验证数据库默认拒绝。
- [ ] **IAM-10.04** 测 session/project/file/private sharing 和运维视角，确认错误响应不泄露敏感存在性。
- [ ] **IAM-10.05** 检查 production 的旧 API、docs、调试与静态资源是否出现身份旁路，业务 schema 文档暴露策略单独确认。
- [ ] **IAM-10.06** 输出 G1 报告和已测路由清单；尚未实现路由标未开放，并要求 P2/P3 新路径持续加入矩阵。

**验收**：AUTH-01～12 适用场景全绿，不用覆盖率稀释越权失败。**PR/回滚**：门禁失败禁止多用户范围扩张，不能单独 skip 失败角色。

## 4. 前端基础任务卡

<a id="ui-01"></a>

### UI-01 — 平台前端骨架与类型化 API

**位置/契约**：`web/platform/`、`WEB/api/`、生成类型与浏览器测试；保留旧 static 作为 legacy，不混用全局 state。

- [ ] **UI-01.01** 确定 TypeScript/路由/构建/测试版本并锁依赖，按团队熟悉技术选一个主栈而非并行两套新 UI。
- [ ] **UI-01.02** 建立同源 API client、错误类型、CSRF 处理、AbortSignal、分页/revision，禁止把长期 Token 放 localStorage。
- [ ] **UI-01.03** 使用实际 OpenAPI/事件 schema 生成或校验类型，fake 服务复用同样契约。
- [ ] **UI-01.04** 定义 request/screen/loading/error/empty 状态，API stub 明确 unsupported，不伪装成功数据。
- [ ] **UI-01.05** 加 lint/typecheck/unit/browser smoke 和构建流程，根 CI 正确包含新 web 路径。
- [ ] **UI-01.06** 建立内容 sanitizer、链接规则、权限错误容器与可访问组件基础，后续文件预览不运行同域用户脚本。

**验收**：UITEST-02/05 的基础夹具；前端不能为没有后端权限的功能合成授权。**PR/回滚**：新平台静态入口 feature flag 关闭，legacy 不接生产多租户 Cookie。

<a id="ui-02"></a>

### UI-02 — 登录、退出与无权限交互

**位置/契约**：`WEB/auth/`、protected routes、`/me` 查询；服务端仍是授权事实来源。

- [ ] **UI-02.01** 实现 SSO 跳转/回调后恢复安全路径，禁止任意 next URL 开放重定向。
- [ ] **UI-02.02** 根据 `/me` 建立当前用户与组织范围，处理未分配组织、停用、过期和登录失败。
- [ ] **UI-02.03** 退出时清理内存/客户端缓存/当前 SSE，不保留上一用户私有目录或消息；服务端同时撤销会话。
- [ ] **UI-02.04** 实现过期后重新登录、401/403/404 区分和键盘焦点恢复，不无限循环自动重试登录。
- [ ] **UI-02.05** 对未完成工作台提供明确受保护空页/功能未开放说明，不回退旧全局 Token 页面。
- [ ] **UI-02.06** 两浏览器/同浏览器切换账号测试 Cookie、缓存、保护路由、CSRF 与返回链接。

**验收**：UITEST-01、AUTH-01/03/09。**PR/回滚**：入口可切维护页，不能临时跳过登录保护。

## 5. 集成次序与并行边界

1. DAT-01/02/06 建立数据库和资源底座；DAT-03 与 DAT-04 在模型字段冻结后可并行。
2. IAM-01/04 定义统一词汇后实现 IAM-02/03/05/06；IAM-07/09 可独立推进但复用资源授权。
3. UI-01 从契约开始，UI-02 等真实 BFF；不能以 fake 登录完成替代 SSO。
4. IAM-08 初期完成版本和钩子，P2/P3 接真实订阅、工具、manager 后补集成证据。
5. IAM-10 作为持续门禁而不是阶段最后一次性写测试。

建议 PR 切片：数据库角色→身份/资源表→事务上下文/RLS→OIDC→资源 API→SecretRef→撤权/支持→登录 UI→矩阵验收。跨组同改 migration 由单一负责人整合。

## 6. 阶段演示与 G1 退出

- Alice/Bob 分别登录，创建私有项目和 Session；互相猜 ID、下载、删除均被拒。
- Carol 获授权共享项目后能读项目文件，但不能读他人私人 Session。
- Org-B 使用 Org-A resource ID 被拒，DB 复合外键也阻止关联。
- 停用 Alice 后旧 Cookie 无法继续请求；运维只能看到获准元数据。
- 未通过扫描的文件不能预览/公开下载；尚未实现的执行接口始终关闭。
- 生产模式缺 SSO/角色/Secret 配置明确拒绝启动或关闭对应能力。

交接 P2：已验证 Principal/Policy/SecretRef、资源仓储、Run schema、事务上下文、测试身份、前端 client 和 G1 路由清单。交接 P4：legacy dry-run 协议和无主数据规则。

## 工程契约补充

GUC RLS 是可信应用上下文下的防误用措施，不是抵御应用 DB 凭据失陷的独立身份边界；普通 logout 与停用用户对 Run 委托的影响分开定义。 详见 [工程契约索引](../engineering/README.md)；任务 ID 和原有子任务顺序保持不变。
