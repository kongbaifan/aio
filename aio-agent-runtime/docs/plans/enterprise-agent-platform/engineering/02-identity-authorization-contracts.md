# 02. 身份、授权、委托与撤权契约

> 关联 IAM-01～10、DAT-02/06、GOV-01/05/06。此处定义拟实现行为，不代表当前全局 Harness Token 已被替换。

## 1. HTTP 身份建立顺序

```text
TLS/可信反代
  → 验证本系统会话 Cookie
  → 查 auth_session 未过期/未撤销
  → 查外部身份对应的 user 和当前 org membership
  → 解析 requested_org 并验证有效成员关系
  → 构造不可变 Principal
  → 查获权资源/动作
  → 开启带租户上下文的数据库事务
```

- 外部 `X-User-Id/X-Org-Id/X-Role` 不是身份；反代应清除这类伪造头，后端也不把它们当权威。服务间使用独立认证，不复用这些裸头。
- requested_org 可是用户选择，但必须验证 membership；不能单凭 org_id 是合法 UUID 就接受。
- JWT 的结构能解析不等于签名、issuer、audience、expiry、nonce 已验证；只有协议验证结果才能建立身份。
- 公开路径只含明确 login/callback 和无敏感内容的健康检查/静态资源；`/api/config` 不应泄漏内部 endpoint、文件路径或其他部门模型配置。

## 2. 三类身份不能混在一起

| 类型 | 权威来源 | 能做什么 | 失效条件 |
|---|---|---|---|
| BrowserPrincipal | 受控 BFF auth_session + 当前 membership | 当前用户 API/订阅/审批 | logout、过期、用户停用、会话撤销 |
| RunDelegation | 创建 Run 时持久授权上限 + 当前用户/资源状态 | 只执行本 Run 已批准的能力范围 | Run 终结/取消、用户/资源撤权、deadline、策略禁用 |
| ServicePrincipal | mTLS/短期工作负载身份 + 受控服务角色 | 调度/派发/回收/账本等职责 | 服务凭据到期/撤销、角色失效 |

后台 Worker 同时携带 original actor 与 service actor。不能把 `RunContext` JSON 本身当作身份凭据；它必须来自获权数据库记录并通过服务身份传递。

### 2.1 Logout 与任务生命周期

- 用户关闭页面不影响持久 Run。
- 普通 logout 撤销浏览器会话和订阅，但默认不自动取消已经获准的后台任务；用户可显式 cancel。
- 用户停用/离职、资源/能力撤权、组织 kill switch 必须阻止 Run 的后续动作并触发取消/核对。
- 后台任务不能要求浏览器 Cookie 一直活着，也不能借“后台运行”永久忽略用户已失去权限。
- 若公司要求 logout 同时取消全部任务，以明确策略实现并测试，不让不同接口各自决定。

## 3. 类型契约

以下为接口草案。UUID、UTC timestamp、枚举、长度/状态校验应由真实类型/schema 实现。

```text
Principal = {
  org_id, user_id, auth_session_id?,
  membership_revision, authentication_level,
  service_actor_id?, authn_kind: browser|workload
}

ResourceRef = {
  org_id, resource_type, resource_id,
  expected_revision?  # 并发前置，不是授权凭据
}

Decision = {
  outcome: allow|deny|approval_required,
  reason_code, policy_revision, membership_revision,
  resource_revision, obligations, decided_at
}

RunDelegation = {
  org_id, actor_id, run_id,
  starting_manifest_digest, allowed_resource_scopes,
  max_data_classification, expires_at,
  revoked_at?, issuer_service
}
```

`RunDelegation` 是上限，不能新增后来才授予用户的能力。授权扩大需要新 Run/明确新委托；缩小必须即时影响下一次判定。

### 3.1 Decision.obligations

| 字段 | 语义 | 实施点 |
|---|---|---|
| max_rows/max_bytes | 此次结果的业务资源/大小上限 | MCP/KB adapter 和结果发布 |
| allowed_resource_ids/filter | 获权资源集合或编译出的过滤 | 数据查询前 |
| required_approval_policy | 谁批准、影响阈值、双人/强认证 | ApprovalService |
| network_profile_id | 允许的出口画像 | manager/受控网关，不由工具改 |
| output_classification/source_policy | 产物继承约束 | Artifact/摘要/分享 |
| max_cost/max_duration | 该次操作预算/期限上限 | 准入、派发与计费 |
| redaction_policy | 哪些字段能给用户、日志或模型 | serializer/事件/日志 |

如果某 handler 无法执行必要 obligation，返回 `POLICY_OBLIGATION_UNSUPPORTED` 并拒绝，不忽略未认识字段继续调用。

## 4. 授权求值算法

```text
1. 验证 actor/service 当前有效、org 相符、authn level 足够。
2. 读取 resource 当前记录；跨 org/不可见资源统一不可见响应。
3. 检查组织硬策略、禁用、当前 Run/资源状态和 deadline。
4. 计算用户拥有者动作 OR 合法角色/Grant 的允许范围。
5. 对允许范围与项目/部门限制、Run 起始委托上限求交。
6. 检查数据来源/派生约束、连接真实外部权限和目标范围。
7. 检查是否需要审批、预算和网络义务；形成 Decision。
8. 在副作用实际派发前再次检查最新授权，记录决策版本与义务。
```

- 同一层多条 grant 可以组合允许项，但任何组织/来源硬禁止优先；不能用一条更宽 grant 覆盖明确 deny。
- `owner` 不自动拥有 declassify、administer-system、read-all-secrets 等能力。
- 项目 Viewer 可看项目公开给成员的文件，不默认能读创建者的私有 Session；Run 是否可见取决于会话/产物的独立可见性。
- 不允许从“可以看工具 schema”推导“可以调用工具”，也不允许从“可以运行 Agent”推导“可以用它所有连接”。
- 部门管理员、能力作者和业务审批人是不同职责。关系不明确时 fail closed。

## 5. 数据库授权与 GUC RLS 的准确边界

### 5.1 建议实施

- 应用使用非 owner、非 superuser、无 BYPASSRLS、不可 SET ROLE 到高权的账号。
- 每个事务从已验证 Principal 设置 transaction-local org/user；没有上下文默认无业务行。
- 租户业务表使用 RLS USING/WITH CHECK 与同 org 复合 FK；Repository 仍执行动作/资源范围过滤。
- 队列扫描角色只读可调度元数据，不顺便获得全部消息、文件、Secret。
- SQL 参数化、严格 identifier allowlist、禁用户 SQL 进入控制数据库。数据库 MCP 连接的是授权业务数据库，不是本平台管理数据库。

### 5.2 不能宣称的保证

`current_setting('app.org_id')` 不是由 PostgreSQL 独立验证的企业身份。若攻击者拿到应用 DB 密码/任意 SQL 能力，可能自己 `set_config` 为其他 org，从而让基于同 GUC 的 RLS 放行。

因此测试要区分：

1. **契约内正确上下文**下漏写 WHERE 或错外键：RLS/FK 应阻止。
2. **应用已被攻破/任意 SQL**：按凭据失陷处理，不能用第 1 类测试冒充抵御第 2 类。

更强边界可采用每安全域独立数据库/连接身份、DB 强制身份映射、受控 broker/严格函数能力等，需独立安全设计；不能只换一个 GUC 名称。

## 6. 撤权时间边界

定义时间：`T_revoke_commit` 为权威撤权事务提交；`T_decide` 为本次最新授权判定；`T_dispatch` 为网络/执行系统接受派发；`T_remote_effect` 为外部系统产生效果。

- 新的 `T_decide > T_revoke_commit` 不得使用旧缓存 allow 放行。
- 已形成 allow 但尚未派发的动作在 dispatch 入口再次检查最新版本/Run；新 capability 不能延长旧允许。
- 与撤权并发、已经派发或已进入网络缓冲的动作可能完成；必须记录先后和影响，不承诺远端原子撤回。
- SSE 关闭后仍可能存在客户端或代理已缓冲字节；测试应断言撤权后新授权读取被拒和生产端停止新增发送，而非要求用户“忘记”旧内容。
- 签名下载 URL 在到期前通常仍是 bearer 能力；严格撤销资源须走实时授权代理，不把短 TTL 说成即时撤权。

缓存允许存资源/策略编译结果，但敏感 allow 使用当前版本确认。通知丢失不能无限保留旧授权；无法确定最新权限时停新敏感动作。

## 7. Secret 和外部身份

- SecretBinding 是带用途、目标域、owner、scope、revision 的引用；审批摘要可显示连接身份标签，但不能包含原始 Key。
- 用户有权使用连接不等于有权导出 Secret；配置只写不回显，前端无“查看完整密码”。
- Secret resolver 根据服务身份、原始 actor、连接和 Run 授权；request 自报 purpose=admin 不赋予权限。
- 模型客户端 cache key 至少包含受控模型配置版本和 credential binding revision；租户可复用无身份连接设施，但不可共享 headers/Cookie/Secret 状态。
- Secret 轮换后关闭旧池；失败不回落到另一个 Provider 的 Key。原 `ModelService.get_client(provider, model)` 的身份不足，需要显式扩展，而不是增加一个模糊全局缓存参数。

## 8. 支持访问和审计最小化

SupportGrant：指定 operator、Run/资源、字段集合、有效期、理由、批准者与强认证级别。下载诊断包本身是资源操作，反复下载/到期/换 Run 都要重新验证。

审计记 actor、service actor、动作、资源 ID、policy revision、decision、outcome、trace；无权限结果不能把资源标题/文档摘要顺手写到用户可见错误中。运维可看脱敏元数据不意味着可以看任意截图和输出。

## 9. 入口审查矩阵

| 入口 | 必做检查 | 明确禁止 |
|---|---|---|
| create Run | Session/Project/模板/输入/模型/预算/委托 | body 指定实际 actor、endpoint、sandbox |
| list/read/delete Session | 当前用户和可见 scope | 全局 SessionStore.list |
| approval decision | 批准资格/强认证/摘要/期限/状态 | 只凭 confirmation_id resolve |
| download/citation | 当前资源/来源权限和 ready 状态 | 知道 path/chunk_id 就读取 |
| test connector/Skill | 同样走授权、网关和隔离 | 管理员调试旁路 subprocess/SSRF |
| internal exec | service + run delegation + target lease | 内网即信任、裸 org/user 头 |
| audit/support | 字段范围/限时授权/访问审计 | 全员管理员默认读正文 |

实现本模块前应把上表映射到实际 router/Depends/服务入口；每条都有正例和直接 API 越权负例，不能只测前端按钮。
