# Platform Foundation Code Contract

## 1. Scope / Trigger

适用于 `apps/local-harness/app/{platform_settings,auth,policy,db,runtime,api/v2}` 与平台测试。数据库当前为 `0013_shared_budgets`；新增契约见 [共享预算](platform-shared-budget-contract.md)、[Worker](platform-worker-contract.md)、[管理台](platform-admin-web-contract.md)、[共享 Skill](platform-skill-contract.md)、[归档隔离导入](platform-skill-archive-contract.md)、[MCP](platform-mcp-contract.md)、[知识库](platform-knowledge-contract.md)、[Team](platform-team-contract.md)、[隔离 stdio](platform-mcp-stdio-contract.md)。仓库未使用 Trellis，契约保存在当前工程文档，不自行初始化 `.trellis`。

## 2. Signatures

```text
deployment_mode(env?) -> DeploymentMode
PlatformSettings.from_env(env?) -> PlatformSettings
Database.transaction(Principal) -> short PostgreSQL Connection transaction
Database.verify_runtime_role() -> rejects owner/superuser/BYPASSRLS/missing FORCE RLS/wrong revision
AuthService.authenticate(opaque_cookie) -> Principal
PlatformService.create_run(principal, session_id, canonical_request, idempotency_key) -> persisted Run
PlatformService.claim_next(org_id, worker_id) -> leased Run or None
PlatformService.plan_invocation(principal, run_id, generation, ActionSpec) -> persisted Invocation/Approval
PlatformService.decide_approval(principal, approval_id, revision, digest, decision) -> durable decision
```

## 3. Contracts

- production 必须显式配置，不能读取 legacy 配置后再决定是否安全；`!command` 密钥形式进入 Shell 之前就拒绝。
- DB 使用 PostgreSQL 与独立迁移账号；运行时不会自动建表/创建角色/回退 SQLite。
- 身份从 BFF/已验证 OIDC 建立；body 的 user/org/sandbox 参数不能授权。
- 所有租户查询在短事务设置本地 scope；结束/异常回滚后不残留给下个用户。
- 旧 Scalar ModelService 的缓存和 subprocess 工具不接入平台模式；未实现执行能力保持不可用。
- 幂等先锁 scope/key，重放仍检查当前 Session/Project/Agent 权限；同 key 不同 canonical request 拒绝。
- 审批过期必须先持久化 expired 再在事务外返回错误，不能抛异常导致状态回滚为 pending。
- OIDC issuer 是精确标识，不把它的末尾斜杠任意删除。签名/JWKS 端点是管理员固定配置，默认不跟随重定向。

## 4. Validation & Error Matrix

| 输入/条件 | 行为 |
|---|---|
| 无/错误平台配置 | PlatformConfigurationError，不能回显 DSN/Secret |
| 未登录/停用/过期会话 | 401，无用户正文 |
| 跨用户/组织、上级 Project 被禁 | 404/拒绝，列表也不返回条目 |
| JSON 重复键/非有限数/过深/超大 | 422/413，FastAPI 解析前拒绝 |
| 缺 CSRF/错误 Origin | 403，不执行 mutation |
| 同幂等键异体/旧 revision | 409，事务无部分写入 |
| 预算不足/同 Session 未解决任务 | 429/409，不留下第二份消息/Job/预留 |
| 旧/过期 lease generation | 409，不推进执行 |
| 自批双人动作/参数变更/过期审批 | 403/409/410；过期事实仍被保存 |
| 未配置 Artifact root/Manager | 明确不可用，不访问原共享 workspace；已配置的 Python 沙箱见独立契约 |

## 5. Good / Base / Bad Cases

- Good：两个同 key 并发请求得到同一 Run，PG 只有一份 Job/预留/消息。
- Base：被授权的 Bob 可读共享项目，但不能因此读取 Alice 私有 Session。
- Bad：审批结果过期后在事务内部 raise，导致 expired 更新回滚；修复必须返回事务后才报错。
- Bad：对两个复合 UNIQUE 都用 column_0_name 命名；它们都以 org_id 开始，在 PostgreSQL 产生同名 backing index。

## 6. Tests Required

- `tests/platform/test_settings.py`：生产入口和直接 legacy 密钥解析的 Shell spy 必须为零。
- `test_contracts.py`：状态矩阵、不可变 ActionSpec、RFC 8785/严格 JSON、所有 constraint 名字唯一。
- `test_oidc.py`：真实 RSA JWT 验签与 issuer/audience/nonce/azp/expiry 负例。
- `test_policy.py`：owner 不等于管理员、org ceiling、委托上限和撤权。
- `test_postgres_integration.py`：使用真实 PG 运行角色/RLS/迁移/并发/API/审批/登录回放，不能替换成 SQLite。
- 新增子任务需补专属正负例；这个基础套件不证明整个多租户平台或沙箱已完成。

## 7. Wrong vs Correct

```text
Wrong: uq_<table>_<column_0_name>          # 多个 UNIQUE(org_id, ...) 重名
Correct: uq_<table>_<column_0_N_name>     # 所有列参与，长名由方言稳定缩短

Wrong: catch manager failure -> run subprocess locally
Correct: unavailable/queue/fail closed; no host execution fallback

Wrong: compare Session owner only in detail API
Correct: list/detail/run/events all honor current resource AND Project policy
```

PostgreSQL `SELECT ... FOR SHARE` 需要对应 UPDATE 权限。应用角色只给 organizations.policy_revision、memberships.revision 列 UPDATE 以便短共享锁，不授予激活/角色/政策内容的随意修改；仍必须理解持 DB 凭据的任意 SQL 攻击不在 GUC RLS 的独立保护范围内。
