# MCP OAuth 授权、刷新与撤销契约

> 实现：`app/connections/oauth_{service,settings}.py`、独立网关的 `oauth{,_contracts,_http,_store}.py`、连接页面与 v10 迁移。
> 这是配置后的标准 HTTP 授权码/PKCE 路径，不代表所有 OAuth 供应商、stdio OAuth、业务写或生产 Gate 均已完成；独立无网络 stdio 的 Bearer/匿名路径见 [stdio 契约](platform-mcp-stdio-contract.md)。

## 1. Scope / Trust Boundary

- 部署操作员预登记 OAuth client 与固定 Endpoint；业务用户不能指定任意 issuer、token URL、redirect、client secret 或 scope。
- 定义可以共享；OAuth grant 仍属于具体个人连接或显式部门服务身份。个人连接不能因通用 Grant 或管理员角色被另一个用户借用。
- 平台登录会话用于证明谁发起授权，不作为 MCP access token 转发。MCP 授权独立于平台 OIDC 登录。
- 授权码仅短暂经过 BFF 和网关；MCP access/refresh token、PKCE verifier、OAuth nonce 只在独立网关加密存储。平台 PG 不存这些明文，用户计算 cell/模型不持有它们。

## 2. API / Storage Signatures

```text
POST /api/v2/connections/{id}/oauth
  CredentialPrepare{expected_revision,request_id}
  -> flow_id,connection_id,authorization_url,expires_at
GET /auth/mcp/callback/{endpoint_id}?state=...&code=...&iss=...
  -> 303 /app/connections?... (authorization code stripped)

Private POST /v1/oauth/start: OAuthBegin{binding,flow_id,ticket_id,not_after}
Private POST /v1/oauth/exchange: OAuthExchange{...,code,state,response_issuer}
Private POST /v1/credentials/revoke: binding + ticket_id

Control purposes: oauth.start / oauth.exchange / oauth.refresh / oauth.reauth_required
```

新增 `aio_mcp_oauth_attempts`：org/connection/binding、请求人及 membership revision、原 auth_session_id、request_id、state/code hash、issuer、期限和状态；有 FORCE RLS 和绑定/原浏览器会话复合外键。

`mcp_bindings.auth_kind` 区分 opaque 与 oauth2，增加远端撤销事实；Connection 只保存安全的授权投影与清理状态。OAuth 由 `0010_mcp_oauth` 引入，原 v1～v10 schema 快照不改，当前应用为 `0013_shared_budgets`。

网关增加加密 OAuth flow/grant journal，与既有 credential binding AAD 隔离。授权过程和刷新不是内存里一把锁而已：开始交换/刷新先持久化，进程重启不重发已经可能消费的 code/轮换 refresh token。

## 3. Operator Configuration

示例：[connector-oauth-endpoints.example.json](../../config/connector-oauth-endpoints.example.json)。API/Worker 与网关读取相同的批准 Endpoint 内容；BFF 只保留公开投影和配置摘要。

必需配置包括：issuer、授权服务器 metadata URL、protected-resource metadata URL、authorize/token URL、client_id、scope 和 redirect URI。支持 public client、`client_secret_basic`、`client_secret_post`。

- 回调固定为平台 origin 的 `/auth/mcp/callback/{endpoint_id}`，各端点使用独立路径。默认还要求 RFC 9207 issuer 响应参数；关闭该要求也不取消独立回调和原状态/会话绑定。
- confidential client 只能引用 `CONNECTOR_OAUTH_CLIENT_SECRET_*` 环境变量，由网关从秘密管理系统注入值。不能引用 vault/control/SSO 环境密钥，也不能通过 Web 上传 client secret。
- 所有 URL 必须是批准的 HTTPS 固定地址；HTTP 只用于显式回环测试。MCP 返回的任意 metadata、resource link 或 WWW-Authenticate URL 不自动成为允许目标。
- profile 摘要包含完整 OAuth 配置的摘要。改 issuer/client/resource/scopes 等必须形成新的授权绑定；不能让旧任务无感使用新权限。
- token 格式默认 opaque；可显式选择 JWT access token 验证。OIDC `openid` 或 JWT access 模式必须配置固定 JWKS URI。

## 4. Implemented Contracts

### 4.1 授权码、PKCE、当前浏览器

1. 发起请求必须通过平台 Cookie、Origin、CSRF、当前成员/连接管理权限；部门服务身份仍由组织管理员维护。
2. flow 绑定**原平台 auth_session_id**，不是仅比较 user_id；换用户、换登录会话、注销或过期后不能消费原回调。
3. 网关生成高熵 state、nonce、PKCE verifier；只暴露 S256 challenge 和正常授权 URL。PG 保存 state/code 摘要，不保存 verifier/code/token。
4. protected-resource metadata 的 resource、授权服务器列表以及 AS metadata 的 issuer、端点、S256、client auth method 都必须符合操作员配置。
5. 浏览器回调严格拒绝重复参数、错误 issuer/state/原会话、不一致的重放；相同已完成回调可幂等返回，但绝不重新兑换 code。
6. OAuth token 交换前后重新验证控制授权。credential 激活与 PG flow 完成同事务；授权服务器拒绝、撤权、过期或存储失败不能激活连接。
7. 回调总是清理浏览器 URL，不反射 provider error_description。平台 CLI 禁用 access log；反向代理/外部启动器仍必须禁止记录回调 query。
8. 授权保存后连接仍需实际 MCP initialize/tools discovery 才 active；“OAuth 已授权”不代替资源服务器身份验证。

### 4.2 Token / Claim Validation

- token endpoint 必须返回 bounded Bearer 响应、合法 expires_in、批准 scope；扩大/减少到不符合批准集合均不静默接受。
- authorize、token exchange、refresh 都发送批准的 RFC 8707 resource；返回的 resource 如存在也须匹配。
- OIDC id_token 验签限制 RS256/ES256，验证 issuer/client audience/azp、有效期、nonce 和可选 at_hash。刷新返回 id_token 时还检查稳定 sub；未返回时保留原 grant 身份。
- 显式 JWT access 模式使用批准 JWKS，要求 access-token typ，验证 issuer/resource audience/client 身份/有效期；拒绝 token 自带的 jku/x5u/jwk/crit 引导抓取。
- opaque access token **不能被客户端假装解码验证 aud**。该路径依靠固定授权服务器、resource 参数、独立绑定与实际资源服务器验证；不声称它有 JWT 级客户端 claims 证明。

### 4.3 刷新与身份版本

- 对同一 credential_ref 加锁，并持久化 token generation/refreshing 状态。正常自动刷新属于同一 grant，不增加平台 `credential_revision`，所以不会仅因 access token 到期就使历史来源和在途 Run 全部失效。
- 用户重新授权/手动更换身份仍建立新 binding revision；旧任务不能借新账号或新 scope 继续。
- 刷新前后检查当前绑定仍为连接使用的版本、资源/服务器/部门未停用；生命周期写入不依赖最初浏览器一直在线。
- 刷新只发生在业务 RPC 之前。握手/目录的 401 最多触发一次刷新并创建全新 MCP client；**tools/call 已发送后不因 401 或任何错误重放业务动作**。
- refresh response 丢失或重启时处于 refreshing，要求重新授权，不自动再次消费可能已轮换的 refresh token。模型/工具预算不因此被清零或重开。
- 取消协程时等待已启动的加密存储线程结束再释放 grant lock，防止迟到写入越过撤销；并发测试等待实际 inactive 事实，而不是依赖固定 sleep 猜顺序。

### 4.4 撤销与数据来源

- 平台先持久撤销连接并提升资源 revision，拒绝后续使用/回调；网关先 inactive，再等正在执行的刷新结束，不让迟到成功恢复 active。
- 已批准 revocation endpoint 存在时，按 RFC 7009 撤销已知 refresh/access token。仍有效的较早 access token 在有界历史内保留供撤销，过多轮换需重新授权。
- remote cleanup 分为 confirmed / unsupported / unknown。端点移除、不支持自动撤销、token 发行回复不明，都不能写成“远端授权全部撤销”。本地不再使用凭据与远端 grant 结束是不同事实。
- 原 mcp_source_refs 继续使用 connection + authorization binding revision。自动刷新不换身份；真正撤销/重新授权/失败需重新授权时，旧来源不能绕到 Team/检查点/产物继续读取。
- 网关失败通知只允许把当前同一 binding 的连接改为 reauth_required；旧 ref 不能把新连接恢复 active，也不能污染新账号状态。

### 4.5 Egress / Limits

OAuth GET/POST 复用实际 DNS/socket peer/Host/SNI 校验；每个 URL 和 HTTP method 单独批准。禁止重定向、代理环境、共享 Cookie、压缩或超限响应。

- 配置 <=16 KiB；network response <=64 KiB；code <=4096 字符；access/refresh token 各 <=8192 字符；flow 10 分钟；回调不允许客户端扩大范围。
- JWT keys 数量、token、metadata 数组有界；不执行远端配置或在 API/Worker 上启动第三方进程。
- 网关使用独占私有 journal、凭据配额和有界并发；多节点密钥存储/轮换/保留治理仍是后续任务，不用本地 SQLite 冒充 HA。

## 5. Validation / Error Matrix

| 场景 | 结果 |
|---|---|
| 对 oauth2 端点粘贴 bearer token | `OAUTH_REQUIRED` / mode mismatch |
| 另一个用户或同用户新登录会话消费回调 | `OAUTH_SESSION_MISMATCH`，不访问 token endpoint |
| issuer 不一致或 code/state 重放不一致 | 拒绝，不改变现有授权 |
| metadata 重定向/新 URL/schema 错误 | 拒绝，不携带凭据跟随 |
| PKCE/nonce/client audience/资源 audience 错误 | 不建立 active grant |
| scope 变化/refresh subject 变化 | 要求重新授权，不扩大权限 |
| 两个请求同时需要刷新 | 一次刷新，后者使用新 token generation |
| 刷新中撤销/取消了存储协程 | inactive 胜出，锁释放前排空写入，不复活 |
| 刷新结果丢失/进程重启 | 不重试 rotating token，reauth_required |
| 资源服务器调用已经发出后错误 | 既有 unknown/核对路径，不重放 tools/call |
| 远端撤销不确定 | 平台已断开，明确要求到源系统检查 |

## 6. Tests / Good / Bad

- `test_oauth_contracts.py`：平台/网关配置摘要一致、秘密引用不进入公开 profile、回调/URL/配置参数限制。
- `test_oauth_integration.py`：真实 PG/authority/加密 vault 的回调状态、原浏览器绑定、幂等、CSRF、清理 URL、实际 MCP 检测、刷新和两个用户的 Worker 身份隔离。
- 网关 `test_oauth.py`：PKCE、nonce、issuer/audience、scope、JWT access、真实凭据头、并发刷新、撤销竞争、取消后写线程、丢回应不重复、metadata 重定向、confidential client 边界。
- `verify_workbench_http.py`：实际 HTTP、签名平台 SSO、合成 OAuth issuer/MCP、网关、PG、Worker；两个用户各自授权、过期 access 刷新、调用、断开和远端撤销。不是公司真实授权服务器验收。

**Good**：同一个共享 Agent，Alice/Bob 各自授权连接；access token 刷新，authorization binding revision 不变；外部业务读取分别为 Alice/Bob。

**Bad**：把平台登录 token 粘到 MCP、使用 metadata 任意跳转目标、刷新时改 scope/subject、把不确定 token 回复当作可无限重试。

## 7. Wrong vs Correct / Remaining

```text
Wrong: authentication == bearer is the only branch adding Authorization
Correct: configured OAuth access tokens also become Bearer headers, never refresh/id/platform-login tokens

Wrong: refresh response arrived after local revoke -> store it as active again
Correct: inactive fence + durable generation + drained store writes + revocation-only late material

Wrong: a token refresh is a new external user, or a new user is merely token refresh
Correct: private token generation is distinct from the immutable authorization binding revision
```

当前使用操作员预注册 client。自动动态 client 注册、所有供应商扩展（PAR/JAR/device flow/private_key_jwt）、stdio OAuth/受控联网、其他传输、二进制导入、可核对真实写、跨节点 vault/备份与完整限流保留仍未交付。已经实现的无网络 stdio 不自动继承 HTTP OAuth 元数据或权限。

完整生产验收、真实公司 IdP/模型/MCP、浏览器视觉和全量故障 Gate 仍未完成；不能从这一授权闭环宣布整个企业平台完成。
