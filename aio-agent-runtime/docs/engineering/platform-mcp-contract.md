# 平台 MCP 连接与独立凭据执行契约（HTTP 只读 v1）

> 范围：`app/connections/`、`services/connector-gateway/`、`web/platform/src/features/Connections.tsx`；MCP 由 `0006_mcp` 引入，当前应用迁移为 `0013_shared_budgets`。原 MCP-01～08、KB、team 和生产 Gate 的完整范围没有缩减。

## 1. 四种对象与边界

| 对象 | 事实/权限 |
|---|---|
| 操作员 Endpoint | 固定 URL/auth/只读工具名/出口策略；不是用户任意地址 |
| MCP ServerVersion | 共享的已审核工具定义、alias、schema 摘要；发布不可修改 |
| Connection | 个人账号或明确的部门服务账号；个人连接不可借给其他用户，管理员也没有通读/借用旁路 |
| CredentialBinding | 独立 revision/ref、创建人/票据/期限/状态；PG 不存原始令牌，实际密文仅在网关 |

AgentVersion 绑定 ServerVersion/ToolVersion，**不绑定创建人的个人凭据**。Run 创建时为当前用户解析其个人/获权部门连接；不唯一时要求明确选择。id/ref/revision/endpoint 摘要进入本次 ManifestSnapshot，后续不能偷偷改用新 Token。

### 当前实现的状态

```text
ServerVersion: draft -> published ; Resource.status 独立 active/disabled
Connection: pending -> active（通过真实 MCP 初始化与发现后） -> reauth_required/revoked
CredentialBinding: pending -> active -> retiring -> revoked
Discovery: running -> ready/failed（有截止时间和不可变结果）
Gateway effect: preparing -> calling -> done / unknown ; 未进入 calling 可证 not_sent
```

保存密文不等于源身份有效。凭据上传/OAuth 授权后连接仍 pending；检测成功才 active。手动换令牌/重新授权建立新的绑定版本；OAuth 自动刷新只改变网关 token generation，不更换稳定 grant 身份。详见 [OAuth 契约](platform-mcp-oauth-contract.md)。

## 2. 请求签名与事务

```text
POST /api/v2/admin/mcp/servers
  ServerCreate{name,version,endpoint_id} -> draft
POST /api/v2/connections
  ConnectionCreate{server_id,name,scope:personal|department,department_id?}
POST /api/v2/connections/{id}/credentials
  CredentialPrepare{expected_revision,request_id} -> {binding_id,state,expires_at}
PUT /api/v2/connections/{id}/credentials/{binding_id}
  CredentialUpload{secret} -> metadata (never plaintext secret)
POST /api/v2/connections/{id}/discover
  DiscoveryCreate{request_id} -> owned discovery snapshot
POST /api/v2/admin/mcp/servers/{id}/publish
  ServerPublish{expected_revision,discovery_id,tools[{remote_name,alias}],acknowledge_readonly_credentials}
DELETE /api/v2/connections/{id} -> durable revocation before gateway cleanup
```

- 写操作认证 + Origin/CSRF。部门连接仅组织管理员配置；个人连接只用当前登录身份创建/维护，不接受客户端 owner_id。
- 上传票据/metadata 先在短 PG 事务持久化；网关调用在事务外。原始 secret 只短暂通过 BFF 转交私有服务，不能出现在 PG、审计、模型或计算环境，也不存浏览器 localStorage。
- activate 前重新检查当前身份/资源/票据；切当前 binding 与旧 binding retiring 同事务。旧密文清理由 Worker 重试，不能失败时改用旧凭据。
- Discovery 有 request_id/期限、创建人和绑定；重复已完成查询复用结果，运行中的相同请求不并发重发。发布再次检查当前连接和 source discovery。
- 只发布操作员允许的工具；远端注解不授予只读权限。按平台有界 schema dialect 校验模型参数，固定 alias，工具与 ServerVersion 同事务发布。
- runtime 数据库有 FORCE RLS、组织复合外键、connection 当前 ref/revision 复合约束；运行账号不能修改已登记的 server endpoint 身份字段。

## 3. Worker/Gateway 调用契约

```text
RunCreate.connection_bindings: optional {server_version_id: connection_id}
ExecutionStore._current_tool -> base published tool + this Run's current binding
ActionSpec -> connection_id + credential_binding_revision + frozen arguments/tool/scope/deadline
MCPDriver.execute(DispatchPermit) -> authenticated private gateway request
POST /internal/v1/connectors/authorize -> exact current credential/discovery/Run/dispatch authority
```

网关不接受调用方自称 user/admin 的授权。控制回调从 PG 读取真实 actor/Job/lease/当前 grant；比较完整 binding、目标工具、参数、operation key、generation 与 deadline。发布人的 Token 不进入所有使用者的 Manifest。

HTTP 每次操作使用独立 session；隔离 stdio 只在同 Run/代次/连接内复用进程，发现使用单独短时 cell。握手后重新获取当前工具 schema，和批准 digest 对比；描述/schema 变化要新版本审核，不能静默扩大。未知结果有持久 journal，调用重试不能再次执行业务动作。API/Worker 没有 vault master key，API/Worker/Gateway 都不会回退宿主 stdio/subprocess。独立固定模板与凭据风险见 [stdio 契约](platform-mcp-stdio-contract.md)。

## 4. 来源与撤回

`Run/Artifact.mcp_source_refs = [{connection_id,credential_revision}]`。来源从 MCP 能力/输入、历史回答和 Project workspace 传递到后续 checkpoint/产物；当前访问重新检查个人/部门 scope、server/connection active 和绑定版本。

分享 Project/Artifact 不能把个人 MCP 数据洗成其他人的公开资料。连接撤销或身份变化影响旧结果/事件/文件读取；不能收回已经下载到外部的副本。仅凭 connection 状态不能证明供应商上某一文档的实时 ACL，逐资源 ACL/订阅/KB 同步仍需后续适配。

## 5. 验证与错误矩阵

| 场景 | 结果 / 不变量 |
|---|---|
| 未批准 endpoint/tool | 403；不转发令牌或业务调用 |
| 缺另一个人的个人连接权限，即便错误插入 Grant | 404；不借用其 Token |
| 凭据保存但没通过检测 | pending；不能作为可运行连接 |
| 票据重放、另一连接/身份/期限 | 不覆盖绑定；按冲突/过期拒绝 |
| 运行前换 Token/ref | 旧 Manifest/ActionSpec 失效，不偷偷切换身份 |
| 远端 schema/描述变化 | MCP_TOOL_DEFINITION_CHANGED；业务 RPC 未发送 |
| 发送后断连接 | recovery_required / unknown，不自动重跑 |
| source connection 撤销后下载派生文件 | 拒绝；项目/文件单独 Grant 不能绕开来源 |
| server 返回 resource_link | 仅数据，无 SSRF 自动获取 |
| gateway/authority 不可用 | 失败关闭，没有本机执行或共享 Key fallback |

**正确**：一份 MCP 定义被两部门使用，各用户/部门显式选择自己的连接；当前连接再去独立凭据服务派发。  
**错误**：在 AgentVersion.config 保存发布人的 Token、所有用户共享有身份的 HTTP session，或把 Token 挂到运行任意代码的容器。

测试：网关协议/Vault/SSRF/TLS/官方 SDK；`test_mcp_integration.py` 的真实 PG + 网关；`test_mcp_sandbox.py` 的真实 compute 无凭据及产物来源；Web 连接表单与确认、固定绑定重试；HTTP 工作台使用多组合成身份验证不同 Token 返回不同资料。

## 6. 升级与未完成工作

先停止/排空旧 API 和 Worker，迁移到当前 v13、刷新 runtime grants 后再启动兼容的 API/Worker/Gateway/Manager；旧读取器不认识 MCP 来源/stdio 生命周期，不能混跑冒充已验证滚动升级。网关有独立私有卷/密钥，见 [网关部署说明](../../services/connector-gateway/README.md)。

配置后的 HTTP OAuth/自动刷新及无网络 stdio 已实现，分别见 [OAuth 契约](platform-mcp-oauth-contract.md) 和 [stdio 契约](platform-mcp-stdio-contract.md)。显式 Run 附件的双 opt-in 复制见 [输入契约](platform-mcp-stdio-input-contract.md)。待交付：更多 OAuth 供应商扩展、stdio 受控联网/活动工作区协作/其他运行时、其他 transport、二进制产物导入、可核对真实写、连接级熔断/更完整限流、完整保留和密钥轮换/备份/HA、源文档 ACL 同步、公司真实系统/UAT、安全/生产 Gate。现有费用账本仍主要覆盖模型调用，不能把源系统的收费宣称为已全部核算。
