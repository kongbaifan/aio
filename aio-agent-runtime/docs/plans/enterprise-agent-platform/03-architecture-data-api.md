# 03. 目标架构、数据模型与接口契约

> 工程层补充：实现时同时阅读 [工程契约索引](engineering/README.md)。其中明确了多权限 cell、RLS 威胁边界、事务锁序、审批与未知效果、当前撤权和可信资源核对；不把本页架构概览当作已实现保证。

> 所有类型、表、接口均为拟新增/拟重构契约，不代表当前项目已经支持。默认实现以 FastAPI + PostgreSQL + 独立 Worker + Sandbox Manager 为基线。

## 1. 架构决策记录

| ADR | 决策 | 原因 | 不采用的默认方案 |
|---|---|---|---|
| ADR-01 | 控制 API 先做模块化单体 | 业务边界清晰但团队有限，减少 RPC/一致性成本 | 一开始拆十几个微服务 |
| ADR-02 | Agent Worker 与 API 分进程部署 | Run 不依附 HTTP、便于资源和故障隔离 | SSE generator 直接执行整个任务 |
| ADR-03 | 本地执行与控制面分信任域 | 用户代码、第三方脚本必须被当作不可信 | 共享 Python/Node/浏览器宿主进程 |
| ADR-04 | PostgreSQL 为权威状态与初期任务队列 | 简化持久化、事务、去重、审批与回放 | 只靠 Redis Pub/Sub 或内存 Future |
| ADR-05 | Redis 只做可丢失的通知/缓存等 | Redis 重启不能丢 Run/审批/费用事实 | 多套互相矛盾的任务事实来源 |
| ADR-06 | Run 级惰性沙箱，项目数据持久化 | 兼顾隔离、依赖复用、成本与回收 | 每个注册用户永久运行容器 |
| ADR-07 | 首版项目写入单写者 | 避免文档/代码/依赖并发覆盖，降低合并复杂度 | 多 Run 同时直接改共享工作区 |
| ADR-08 | 能力目录与执行授权分开 | 防止绕过 manifest 直接调用、权限过期 | 只向模型隐藏工具 |
| ADR-09 | Skill/Agent/镜像/模型配置版本固定 | 调试、审计、回滚、审批均需明确版本 | 运行中动态读取被人修改的公共目录 |
| ADR-10 | EngineAdapter 隔离引擎差异 | 当前 Harness 先落地，后续 Codex 不重写平台 | 将某一引擎 RPC 直接当企业 API |
| ADR-11 | 外部写入按可核对的至少一次/不确定语义处理 | 无法通用保证端到端 exactly-once | 网络超时后无条件重试 |
| ADR-12 | 生产默认拒绝并禁止开发回退 | 隔离设施/密钥/身份异常不能降低安全性 | 自动 fallback 到 localhost shell/global token |

## 2. 模块职责与部署边界

| 模块 | 输入/输出 | 持久状态 | 不应该做的事 |
|---|---|---|---|
| BFF/Auth | OIDC 回调、浏览器会话 → Principal | 登录会话/成员关系 | 把管理员 Token 放 localStorage |
| PolicyService | 主体+动作+资源+上下文 → Allow/Deny/ApprovalRequired | Grant/策略版本 | 相信模型提供的 user_id 或 department |
| Session/ProjectService | 会话、项目、文件授权 | PG/对象存储 | 直接暴露宿主机目录 |
| AgentCatalog | 模板与版本 → 允许的模型/能力范围 | PG/不可变版本包 | 通过模板覆盖组织安全策略 |
| RunService | 幂等创建/查询/取消 → Run | PG | 在请求线程中长期执行用户任务 |
| JobDispatcher | 选择可运行任务 → Worker lease | PG jobs、配额 | 运行模型或用户代码 |
| AgentWorker | 已签发 RunContext → 事件、工具请求、结果 | Checkpoint、事件、账本 | 直接启动不可信 CLI |
| ToolGateway | 工具名+参数+可信上下文 → 授权后的调用 | Invocation/Approval/Audit | 只检查前端传来的工具列表 |
| SandboxManager | 固定模板 SandboxSpec → binding/lifecycle | lease/节点清单 | 接受任意 Docker 参数、挂载、特权标志 |
| WorkspaceService | project version → Run 工作副本/发布版本 | PG + 对象存储/受控卷 | 让客户端决定宿主绝对路径 |
| MCPAdapter | 授权连接和工具调用 → 标准结果 | 连接版本、外部会话绑定 | 跨用户共享有身份状态的客户端 |
| KnowledgeService | 授权检索 → 证据/引用 | 文档/ACL/chunks/index | 先给模型未授权文本后再过滤 |
| SecretService | SecretRef + 调用身份 → 内部授权访问 | KMS/Vault/受控密钥存储 | 在 API/日志/Skill 中返回原始长期密钥 |
| ArtifactService | 隔离产物 → 扫描/发布/下载 | PG + 对象存储 | 执行用户 HTML/Office 宏 |
| Audit/Observability | 脱敏事件 → 审计与指标 | PG/归档存储 | 无差别收集业务正文或 Token |

部署建议：控制节点上运行 API、Worker 的可信编排部分和服务代理；执行节点只运行管理代理与不可信执行单元；数据库/对象存储按现有公司设施部署。Worker 不执行脚本，故可与控制服务同信任级别，但应有独立账号与资源配额。

Sandbox Manager 对容器引擎有实质高权限，应独立网络身份、最小 API、镜像/挂载白名单和变更审计；不是普通 Web 服务的一段工具函数。

## 3. 必须贯穿全链路的上下文

### 3.1 Principal

由登录/服务身份验证建立，不接受请求体自由指定：

```python
@dataclass(frozen=True)
class Principal:
    org_id: UUID
    user_id: UUID
    membership_revision: int
    auth_session_id: UUID
    authentication_level: str
    service_actor_id: UUID | None
```

服务调用必须保留原始发起者和代理服务身份，不把所有审计都写为 `system`。身份组可查缓存，但敏感动作使用当前权威权限/版本。

### 3.2 RunContext

```python
@dataclass(frozen=True)
class RunContext:
    org_id: UUID
    actor_user_id: UUID
    project_id: UUID
    session_id: UUID
    run_id: UUID
    attempt_id: UUID
    execution_generation: int
    agent_version_id: UUID
    manifest_snapshot_id: UUID
    model_config_version_id: UUID
    policy_revision_at_start: int
    workspace_base_version_id: UUID
    data_classification: str
    deadline_at: datetime
    trace_id: str
```

不包含长期 Secret 明文。SandboxBinding 由 manager 单独签发/查询，绑定 run_id、generation、期限和固定 profile，不来自模型输出。初始策略快照用于解释任务，不用于绕过后续撤权。

### 3.3 内部接口契约

```text
PolicyService.authorize(principal, action, resource_ref, facts) -> Decision
CapabilityResolver.resolve(context) -> ManifestSnapshot
ToolGateway.invoke(context, tool_alias, arguments, invocation_key) -> ToolOutcome
SandboxManager.ensure_target(context, execution_target_ref, approved_profile_id) -> SandboxBinding
ExecutionClient.execute(binding, execution_spec) -> AsyncIterator[ExecutionEvent]
WorkspaceService.prepare(context, mode) -> WorkspaceLease
WorkspaceService.publish(context, expected_base_version) -> WorkspaceVersion
EngineAdapter.run(context, input_messages, tool_gateway) -> AsyncIterator[EngineEvent]
RunEventStore.append(run_id, generation, event) -> sequence
```

- `Decision` 包含允许/拒绝/需审批、reason_code、策略版本、义务（脱敏/只读/上限），不要只返回布尔值。
- `ExecutionSpec` 的程序、参数、工作目录、环境变量与限额从已批准模板构造；不允许用户上传 DockerSpec。
- 模型可生成业务参数，但 org/user/run/sandbox/credential scope/挂载列表均由后端注入。
- 工具参数先按 JSON Schema/Pydantic 验证，禁止多余授权字段、超大值和不合法资源引用。

## 4. 创建与执行一次 Run 的精确顺序

1. 验证浏览器登录、CSRF、组织成员状态、Session 和 Project 权限。
2. 验证 `Idempotency-Key`。同键同 body 返回原 Run；同键不同 body 返回冲突。
3. 加锁检查 Session 顺序和当前活跃 Run。首版同 Session 不允许两个活跃写入任务；返回 `SESSION_BUSY`，不静默混合对话。
4. 检查 Agent/模型/能力的发布状态与初步数据策略。创建版本引用而不是拷贝 Secret。
5. 在同一数据库事务里创建 user message、Run、job、起始事件和预算预留；使用客户端预期 session_revision 防丢写。
6. 提交成功才返回 202。API 与事件连接失败不回滚已提交任务；客户端按幂等键找回。
7. Dispatcher 按组织公平调度和配额选择任务，Worker 原子领取 lease，并递增 execution_generation。
8. Worker 重载当前授权，校验禁用/离职/Agent 撤回；准备项目租约和 RunContext。
9. 引擎读取受权上下文，生成工具请求；每次请求重新经 ToolGateway 检查。
10. 若工具需要本地执行，第一次才由 manager 分配沙箱、镜像、网络 profile 和工作副本。
11. 若需审批，冻结 ActionSpec、写 Approval 和事件；Worker 不持有长数据库事务等待用户。
12. 每个工具调用都记录意图、结果/不确定状态、用量与事件；禁止重跑可能已产生外部副作用的动作。
13. 回答与文件生成完成进入 persisting。先保存必要结果、引用、Artifact 与账本，再写终态。
14. 通过 Outbox 安排释放项目租约、预算结算、沙箱销毁；资源清理状态独立追踪。
15. UI 通过 Run 查询与事件回放获得最终结果。清理失败不伪装已经销毁，由运维闭环处理。

## 5. 状态机

### 5.1 Run 状态

| 状态 | 进入条件 | 允许的后续状态 | 核心不变量 |
|---|---|---|---|
| queued | 持久创建成功 | preparing/cancelled/timed_out/failed | 不能已有未记录的外部执行 |
| preparing | 获得 Worker lease | running/cancel_requested/failed/timed_out | 当前 generation 唯一有效 |
| running | 引擎执行中 | waiting_approval/persisting/cancel_requested/failed/timed_out/recovery_required | 每次工具调用均重新授权 |
| waiting_approval | 存在未决 Approval | running/cancel_requested/failed/timed_out/recovery_required | 不执行被审批动作；无长事务；环境不可恢复时明确失效 |
| persisting | 推理已结束，保存结果 | succeeded/failed/cancel_requested/recovery_required | 没有持久产物不能声称成功 |
| cancel_requested | 用户/策略发起取消 | cancelled/recovery_required/failed | 立即阻止新增工具；尝试停止正在执行动作 |
| succeeded | 结果、必要账本和引用已保存 | 无 | 修改需另建 Run，不覆写历史 |
| failed | 明确失败且没有未决副作用 | 无 | 失败码可解释；资源必须进入回收 |
| cancelled | 执行停止并记录已知影响 | 无 | 取消不等于撤销外部业务操作 |
| timed_out | 超过任务截止且无不明副作用 | 无 | 不再自动续租或继续工具 |
| recovery_required | 外部效果不明/无法安全恢复 | 人工核对后终结；新任务使用新 Run | 无自动重试、无活跃执行授权 |

首版不实现任意 checkpoint 自动恢复。Worker 崩溃时，只对明确可重入的只读步骤或未开始的动作接管；已有 STARTED 的外部写动作进入核对。重新执行默认创建新 Run，并记录 source_run_id。将来支持原 Run 安全 resume 必须新增明确状态迁移与测试。

### 5.2 ToolInvocation 状态

`planned → authorized → waiting_approval(optional) → executing → succeeded | failed | denied | cancelled | outcome_unknown`

- 执行前保存 ActionSpec 摘要、调用键、目标、外部身份、deadline、策略版本与意图审计。
- `executing` 后 Worker 失联或请求超时，不自动判定失败；先判断外部结果可否查询。
- 对支持下游幂等的写接口复用同一业务幂等键；新的 Worker generation 不产生第二份业务操作。
- `outcome_unknown` 需要查询、人工核对或补偿流程，不能简单变为 queued。
- 外部服务不支持幂等且无法核对的高风险写工具，首版拒绝上线。

### 5.3 Approval 状态

`pending → approved | rejected | expired | invalidated | cancelled`，终态不可反复修改。

ActionSpec 至少覆盖：run_id、invocation_id、tool_version、canonical_arguments_hash、resource_scope、credential_binding_version、workspace/input/script 摘要、有效期、当前执行代次绑定策略。

改变参数、脚本、输入文件、工具版本、连接身份或执行环境关键配置，应重新生成动作并审批。不能批准一份代码，然后允许后续步骤修改同一路径内容再执行。

审批后的瞬间仍可能发生撤权，因此执行前再次检查当前权限、Run 状态与摘要。高风险操作按策略要求不同审批人与发起者。

### 5.4 Sandbox lease 状态

`requested → provisioning → ready → leased → destroying → destroyed`

异常可进入 `failed` 或 `quarantined`；后台 reaper 根据 DB 和实际运行时标签对账。`destroyed` 只有运行时确认并释放数据挂载后才成立。创建成功但 API 回复丢失，通过 run_id+generation 幂等查询找回，不创建孤儿重复实例。

### 5.5 Local Harness 的可恢复 checkpoint

要摆脱现有 Python generator/Future 的内存状态，不能只把 Run 状态写进表。每个安全边界需要持久 checkpoint：

- engine/checkpoint schema 版本、Run/generation、round/step 序号。
- 受控内容引用：system/用户/assistant/tool 消息序列及来源，不包含 Secret。
- 当前完整模型回合的 tool_calls、已完成 logical_call_id 集合、下一个待执行位置。
- waiting_approval 的 invocation_id、action_digest、输入/脚本/环境版本、截止时间。
- 工具结果引用、usage 状态、Manifest/Agent/模型/工作区版本。
- `restartability` 标记：stateless/reconstructible/process_state_dependent/unknown。

模型完整回合在调工具前保存；每个工具结果、游标更新和相关事件在同一事务提交。恢复使用已保存的工具调用，不重新询问模型生成一份可能不同的写操作。

API 重启不影响已持久审批。Worker 重启后，仅当 pending 动作未开始、输入/权限/摘要仍有效、所需环境可安全重建时恢复审批等待；更换 Worker 的 generation 必须重新验证执行 binding，不借旧能力继续执行。依赖 Python/Node 内存、浏览器临时状态或无法复现输入时，保留审批记录但使执行授权失效，进入 `recovery_required`/明确失败并由用户发起新任务。

模型仅输出了一半且完整回合未提交时，标记本次输出不完整及 usage 未知，不把两个尝试的文本拼成一个假完成答案。首版不实现任意进程/模型流透明断点续跑。

## 6. 调度、租约与幂等

### 6.1 PostgreSQL 初期任务队列

- `jobs` 存 job_type、org_id、run_id、priority、not_before、lease_owner、lease_expires_at、lease_version、attempt、状态。
- 领取采用短事务与 `FOR UPDATE SKIP LOCKED`，更新租约后立即提交。
- 权威租约时间使用数据库/受控服务时间，节点同步时钟；执行时长计量用单调时钟。客户端时间不决定审批/Token/租约是否过期。
- 心跳建议 10 s，租约初始 45 s，超时阈值必须在故障测试后确认。
- 排队与执行超时分开：初始 queue TTL 可为 15 min；执行总时限从 preparing 开始，工具时限取 profile、Run 剩余时间、用户已获准业务 deadline 的最小值。审批等待计入执行时限，不因重试/重启无限续期。
- 扫描过期 lease 时先撤销旧 generation 的新调用资格，再按重入策略接管。
- Redis 发送 job/event 唤醒提示；丢失提示由定期扫描兜底，不丢任务。
- 队列公平性：组织配额与每用户并发限制优先，队列等待时间老化；不能让一个部门批量提交占满整个节点。
- 解析、嵌入、模型任务、代码执行分别设池和并发，避免大批入库挤占交互 Run。

### 6.2 Fencing 的边界

每次 manager 操作、工具执行与事件提交验证 generation/lease。旧 Worker 即使恢复，也不能操作新租约。**这只能拒绝新的过期动作，不能撤销已经发到外部服务的请求。** 外部一致性依赖稳定幂等键、查询结果和人工核对。

### 6.3 幂等范围

| 操作 | 幂等键 | 规则 |
|---|---|---|
| 创建 Run | org+user+API+client key | 同 body 返回同 Run；不同 body 409 |
| 创建执行 cell | org_id+run_id+generation+target_slot | 已创建则返回原 binding；profile/镜像/身份等配置不同拒绝 |
| 执行工具 | run_id+logical_call_id | 重复请求返回原状态/结果，不重复产生写副作用 |
| 审批 | approval_id+decision nonce | 同决定稳定返回；冲突决定 409 |
| 保存产物 | run_id+logical_artifact_id+content hash | 上传可重复，发布记录只有一个有效版本 |
| 计费 | provider_request_id 或 run+call_id+usage_type | 不重复入账；unknown 不当作免费 |
| Outbox 消费 | outbox_event_id | 消费端去重；允许至少一次投递 |

## 7. 数据模型

### 7.1 通用约束

- ID 使用 UUID 等非顺序标识，但 ID 不承担授权功能。
- 所有租户业务表必须有 org_id；创建/修改时间使用 UTC timestamptz；并发实体带 revision。
- 业务跨表引用使用 `(org_id, resource_id)` 复合唯一键和外键，避免跨组织关联。
- 公共平台模板是单独类型的只读模板，不通过 org_id=null 给普通业务查询制造旁路。
- 可授权资源统一注册到 resources，域实体保留类型专用字段。资源类型与实体一致性需要约束/服务校验。
- 敏感内容与审计元数据分存；日志不存 Secret 明文；对象存储键由服务生成。

### 7.2 身份与权限表

| 表 | 关键字段 | 约束/索引 |
|---|---|---|
| organizations | id, name, status, policy_revision, data_policy | status 控制全组织新增调用 |
| users | id, oidc_issuer, oidc_subject, display_name, status | unique(issuer, subject)，不以邮箱当永久主键 |
| org_memberships | org_id, user_id, status, role, revision | unique(org,user)；离职不删审计身份 |
| departments | org_id, id, parent_id, external_group_id | 外部组映射唯一，父子同组织 |
| department_memberships | org_id, department_id, user_id, source, valid_until | 多部门成员、来源可追踪 |
| projects | org_id, id, owner_id, name, visibility, data_classification, revision | 默认 private；owner 必须是组织成员 |
| project_memberships | org_id, project_id, user_id/group_id, role | Viewer/Editor/Admin 分开 |
| resources | org_id, id, type, owner_id, project_id?, status, acl_revision, labels | unique(org,id)，类型/归属不可由模型改 |
| resource_grants | org_id, resource_id, subject_type, subject_id, action, expires_at | scope/action 索引；默认拒绝；变更增 ACL revision |
| auth_sessions | id, user_id, org_id, expires_at, revoked_at, auth_level | Cookie 只含随机会话引用；存 hash/安全会话信息 |
| support_grants | org_id, id, run_id, operator_id, allowed_fields, expires_at, approver_id | 支持访问限资源、限时、可撤销 |

### 7.3 会话、运行与执行表

| 表 | 关键字段 | 约束/索引 |
|---|---|---|
| agent_templates | org_id, id, name, owner_id, active_version_id, status | 当前版本指针而非修改旧版本 |
| agent_versions | org_id, id, template_id, version, manifest_policy, model_policy, instruction_ref, digest | unique(template,version)，发布后不可变 |
| sessions | org_id, id, project_id, owner_id, agent_version_id, title, revision, status | (org,owner,updated_at) 分页；不在缓存淘汰时删除 |
| messages | org_id, id, session_id, run_id?, seq, role, content_ref, provenance, visibility | unique(session,seq)；工具与正文可分存但需可恢复 |
| runs | org_id, id, session_id, project_id, actor_id, state, attempt_id, generation, version_refs, deadline, outcome_summary | 活跃 Run 唯一约束/事务；(org,actor,created_at)、状态索引 |
| run_steps | org_id, id, run_id, ordinal, state, input_ref, output_ref, resumability | unique(run,ordinal)，team 作为同一 Run 步骤 |
| run_checkpoints | org_id, id, run_id, checkpoint_seq, engine_schema_version, cursor, payload_ref, restartability, digest | unique(run,checkpoint_seq)，恢复只读取完整已提交 checkpoint |
| tool_invocations | org_id, id, run_id, logical_call_id, tool_version, action_digest, arguments_ref, state, external_id, result_ref | unique(run,logical_call_id)，记录 unknown |
| approvals | org_id, id, invocation_id, action_digest, requester_id, eligible_policy, decided_by, state, expires_at, revision | 一次有效 pending；更新用 CAS；审批人独立审计 |
| jobs | org_id, id, kind, run_id?, payload_ref, state, lease_owner, lease_version, lease_expires_at, not_before | 领取索引(state,not_before,priority)，载荷不含 Secret |
| run_events | org_id, run_id, sequence, type, schema_version, payload_ref/jsonb, created_at | PK(run,sequence)，按时间归档；写入验证 generation |
| outbox | id, org_id, aggregate_id, event_type, payload, delivered_at, attempts | 与业务变化同事务；消费者去重 |
| idempotency_keys | org_id, actor_id, operation, key_hash, request_hash, response_ref, expires_at | unique(org,actor,operation,key_hash) |
| sandbox_leases | org_id, id, run_id, generation, target_slot, role, connector_binding_version?, node_id, backend_id, profile_id, image_digest, state, expires_at | 每 org/run/generation/target_slot 唯一；不同权限 cell 不合并 |

### 7.4 工作区与产物

| 表 | 关键字段 | 约束/索引 |
|---|---|---|
| workspaces | org_id, id, project_id, head_version_id, quota_bytes, used_bytes | 项目默认一主 workspace |
| workspace_versions | org_id, id, workspace_id, parent_version_id, manifest_object_key, digest, created_by_run | 内容清单不可变；原始路径只是清单数据 |
| workspace_leases | org_id, workspace_id, run_id, generation, mode, expires_at, base_version_id | 首版同 workspace 单一写 lease；只读指向提交版本 |
| artifacts | org_id, id, project_id, run_id, owner_id, object_key, filename, mime, bytes, sha256, scan_state, visibility, source_refs, classification, derived_access_policy, expires_at | object_key 唯一；ready 之前不可下载 |
| upload_slots | org_id, id, actor_id, project_id, purpose, max_bytes, expires_at, state | 一次完成确认，验证内容 hash 和实际大小 |

### 7.5 能力、连接、知识与费用

| 表 | 关键字段 | 约束/索引 |
|---|---|---|
| capabilities | org_id, id, kind, name, owner_id, scope, status, active_version_id | kind=skill/mcp/knowledge/builtin；权限用 resources/grants |
| capability_versions | org_id, id, capability_id, version, artifact_ref, schema_digest, requirements, risk, status | immutable；记录审核/发布人 |
| manifest_snapshots | org_id, id, run_id, capability_versions, allowed_scopes, digest | 起始能力上限；不替代实时撤权 |
| connections | org_id, id, owner_id, connector_version_id, sharing_scope, endpoint_ref, credential_binding_id, state | endpoint/credential changes 增版本并触发重新授权 |
| secret_bindings | org_id, id, external_secret_ref, owner_id, purpose, allowed_hosts, revision, expires_at | 只有引用；原始秘密在密钥服务 |
| model_config_versions | org_id, id, provider, model_id, approved_endpoint_ref, credential_binding_id, compat, data_policy, digest | 现有 provider/model 缓存必须新增授权与凭据 scope |
| knowledge_bases | org_id, id, owner_id, classification, embedding_config, state | 不默认继承所有用户读权 |
| documents | org_id, id, kb_id, source_key, active_version_id, acl_revision, state | ACL 可比 KB 更窄；source_key 去重 |
| document_versions | org_id, id, document_id, content_hash, source_revision, object_key, parser_version, state | 更新/删除 epoch 防旧任务复活旧内容 |
| chunks | org_id, id, document_version_id, ordinal, text_ref, embedding, metadata | 继承文档 ACL；按版本整体切换 |
| ingestion_records | org_id, id, document_version_id, job_id, stage, error_code, retry_count | job 队列统一；stage 可观察 |
| budgets | org_id, id, scope_type, scope_id, period, currency, hard_limit, reserved, consumed | 组织/部门/用户层级检查，事务防并发超支 |
| budget_reservations | org_id, id, run_id, estimate, state, expires_at | reserve/settle/release 幂等 |
| usage_ledger | org_id, id, run_id, invocation_id?, provider_request_id, usage_status, quantities, cost_estimate, price_version | 追加事实；unknown 不用 0 冒充精确值 |
| audit_events | org_id, id, actor_id, service_actor_id, run_id?, action, resource_ref, policy_version, decision, outcome, trace_id, timestamp | 追加写，访问审计，敏感字段分离 |
| memory_entries（后续） | org_id, id, owner/scope, source_refs, acl_revision, content_ref, expires_at | 默认关闭；无可追踪来源不可跨会话共享 |

不是要求第一个 PR 建完所有表。迁移按身份→Run→沙箱→能力→知识→治理顺序落地；通用 resources 与审计字段先冻结。

### 7.6 PostgreSQL RLS 与 Repository

RLS 作为防误用层，不能替代对象动作授权。使用 app.org_id 这类应用设置的 GUC 时，不能声称能抵御应用数据库凭据失陷或任意 SQL 攻击者自行设置上下文；详细边界见 [工程授权契约](engineering/02-identity-authorization-contracts.md)。建议：

- 应用数据库角色不是表 owner、superuser 或 BYPASSRLS，不能提升角色；核心业务表 `ENABLE/FORCE ROW LEVEL SECURITY`。
- 每次数据库事务用参数化 `set_config(..., true)` 设置 org/user 上下文，连接池归还前确保事务结束。
- 无组织上下文默认不返回业务行；跨组织 FK 由数据库拒绝。
- Repository 仍显式过滤 scope，并调用 PolicyService 校验动作/共享 Grant。
- 调度器需要跨组织发现任务时使用只可访问队列元数据的专用角色，不给普通 API 跨组织查询能力。
- 测试覆盖连接池复用、空上下文、事务取消、后台 Job、管理员查询与批量导出。

示意策略仅说明 org 隔离，不是完整用户授权实现：

```sql
USING (
  org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
)
WITH CHECK (
  org_id = NULLIF(current_setting('app.org_id', true), '')::uuid
)
```

## 8. 对外 API v2

所有业务接口同源 BFF、TLS；Cookie 登录使用 HttpOnly/Secure/SameSite，写请求额外 CSRF 防护。服务间采用独立短期身份或 mTLS。客户端提交的是资源选择，不是可信身份声明。

| API | 作用 | 核心检查 |
|---|---|---|
| `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout` | 企业登录退出 | state/nonce/issuer/aud/CSRF/重定向白名单 |
| `GET /api/v2/me` | 当前用户和可用范围 | 不回显 Secret、内部 Token |
| `GET/POST /api/v2/projects` | 项目列表/创建 | org/owner/创建配额 |
| `GET/PATCH /api/v2/projects/{id}` | 项目读取修改 | revision 与项目授权 |
| `GET/PUT /api/v2/projects/{id}/members` | 项目成员管理 | 管理员范围、不能超授 |
| `GET /api/v2/agents` | 已授权发布模板 | 只列可见可用版本 |
| `GET/POST /api/v2/sessions` | 会话分页/创建 | 私有归属与项目授权 |
| `GET/PATCH/DELETE /api/v2/sessions/{id}` | 会话操作 | owner/grant；活跃 Run 删除策略明确 |
| `POST /api/v2/sessions/{id}/runs` | 创建任务 | 幂等、顺序、Agent/模型/预算/项目 |
| `GET /api/v2/runs/{id}` | 状态与结果摘要 | Run owner/项目和会话可见性 |
| `GET /api/v2/runs/{id}/events` | SSE/回放 | seq、授权、撤权、订阅配额 |
| `POST /api/v2/runs/{id}/cancel` | 请求取消 | 授权、幂等、状态允许 |
| `POST /api/v2/runs/{id}/retry` | 创建关联的新任务 | 只允许明确安全重试；unknown 阻止直接重试 |
| `POST /api/v2/runs/{id}/reconcile` | 人工核对不明结果 | 高权限、证据、审计；不是任意改状态接口 |
| `GET /api/v2/approvals` | 我能处理/查看的审批 | 审批权限与内容最小化 |
| `POST /api/v2/approvals/{id}/decision` | 批准/拒绝 | digest/revision/批准者/期限/Run 当前状态 |
| `POST /api/v2/projects/{id}/uploads` | 创建上传槽 | 大小/用途/数据分类 |
| `POST /api/v2/uploads/{id}/complete` | 完成上传确认 | hash/实际大小/扫描状态 |
| `GET /api/v2/projects/{id}/files` | 已提交项目文件清单 | 版本、路径规范化、权限 |
| `GET /api/v2/artifacts/{id}` | 元数据/预览状态 | artifact ACL/ready/retention |
| `POST /api/v2/artifacts/{id}/download-link` | 短期下载能力 | 再授权、范围、到期；严格撤回场景走代理下载 |
| `PUT/DELETE /api/v2/resources/{id}/grants/{grant}` | 授权/撤销 | 资源管理权、上限、审计、cache invalidation |
| `GET /api/v2/capabilities` | 授权目录 | 不能列出秘密资源名 |
| `POST /api/v2/skills/versions` | 提交包 | 维护者、隔离扫描、配额 |
| `POST /api/v2/skills/versions/{id}/publish` | 审核发布 | 双人/版本/策略/测试证据 |
| `POST /api/v2/capabilities/{id}/disable` | 能力禁用 | 管理范围与应急传播 |
| `GET/POST/PATCH /api/v2/connections` | 个人/部门连接 | endpoint 模板、scope、SecretRef |
| `POST /api/v2/connections/{id}/authorize` | 绑定 OAuth 等 | 连接专属 state、scope、回调白名单 |
| `POST /api/v2/connections/{id}/test` | 测试连接 | 同样经网络与权限策略，不能直接 socket |
| `POST /api/v2/connections/{id}/revoke` | 撤销 | 凭据失效、连接池清除、排队任务校验 |
| `GET/POST /api/v2/knowledge-bases` | 知识库管理 | owner/grant/data policy |
| `POST /api/v2/knowledge-bases/{id}/documents` | 入库任务 | upload slot/文档 ACL/配额 |
| `GET/DELETE /api/v2/documents/{id}` | 读取/删除 | 文档权限、删除传播、索引状态 |
| `GET /api/v2/ingestions/{id}` | 入库进度 | 文档权限；错误脱敏 |
| `GET /api/v2/admin/runs` | 运维任务列表 | 管理范围、仅元数据 |
| `GET /api/v2/admin/usage`, `/audit` | 用量、审计 | 最小字段、分页、导出审批 |
| `POST /api/v2/admin/kill-switches` | 应急禁止 | 强认证、范围、立即阻止新增执行 |
| `POST /api/v2/support-grants` | 限时排障授权 | 数据权利人/安全批准、有效期、字段范围 |

不提供公共 `/execute arbitrary shell` 或接收 sandbox_url 的接口。内部工具入口仅接受服务身份和绑定 Run 的能力，外部 MCP Server 如需保留也必须翻译到同一权限域。

### 8.1 创建 Run 请求示例

```json
{
  "message": "分析上传的销售表并生成报告",
  "agent_version_id": "uuid",
  "expected_session_revision": 12,
  "input_artifact_ids": ["uuid"],
  "mode": "single"
}
```

org_id、actor_id、sandbox_id、endpoint、挂载、权限策略和凭据不由此请求控制。工具/模型选择若开放，只能从后端返回的授权版本 ID 中选择。

### 8.2 错误契约

```json
{
  "error": {
    "code": "PROJECT_BUSY",
    "message": "该项目已有任务正在写入，请等待完成后重试。",
    "request_id": "uuid",
    "retryable": true,
    "details": {"retry_after_seconds": 5}
  }
}
```

- 401 登录无效；403 已知范围内动作禁止；对敏感的跨用户资源用统一 404，不暴露存在性。
- 409 版本/状态/幂等冲突；413 大小；422 参数；429 配额；503 依赖不可用且不得降级越权。
- 稳定错误码包括 `SESSION_BUSY`、`PROJECT_BUSY`、`QUOTA_EXCEEDED`、`POLICY_DENIED`、`APPROVAL_EXPIRED`、`SANDBOX_UNAVAILABLE`、`CAPABILITY_REVOKED`、`OUTCOME_UNKNOWN`、`EVENT_CURSOR_EXPIRED`。
- 审批超时是明确业务状态；上游 raw body、Shell stderr、SQL、SecretRef 内容不得原样返回用户。

## 9. SSE 与事件契约

```text
id: <run_id>:42
event: tool.completed
data: {"schema_version":1,"run_id":"...","seq":42,"timestamp":"...","payload":{"invocation_id":"...","status":"succeeded","summary":"已生成分析表"}}
```

事件类型：`run.queued`、`run.preparing`、`run.started`、`answer.delta`、`step.started/completed`、`tool.planned/started/completed/failed`、`approval.required/resolved`、`artifact.ready`、`usage.updated`、`run.cancel_requested`、`run.completed/failed/cancelled/timed_out/recovery_required`。

契约要求：

1. 序号在每个 Run 内严格递增；事件持久化后才对外宣布可恢复。
2. 模型 token 按约 100–250 ms 合并为事件，不每 token 一次事务；所有缓冲有大小上限。
3. SSE 至少一次投递，前端按 run_id+seq 去重，不假设只收到一次。
4. 支持 `Last-Event-ID` 或明确的 after_seq 参数；两者冲突拒绝。事件游标过期提供授权后的 snapshot 获取流程，不伪装无事件。
5. 心跳不分配业务序号；慢消费者达到缓冲上限即断开并引导回放，不能挤爆 API 内存。
6. 每次订阅、恢复和持续发送都受当前权限/会话有效期控制；撤权时立即停止敏感内容发送。
7. 模型调用失败后，流以结构化失败事件结束；不能由于 HTTP 已是 200 就在 UI 显示成功。
8. 浏览器断线默认任务继续；取消是独立 POST，并由后端状态确认。
9. run_events 中敏感正文按内容策略存引用/加密；审计日志不复写完整事件载荷。

## 10. 工作区的一致性与发布

首版写任务流程：

1. 取得 project/workspace 写 lease，绑定 run/generation 和 base_version。
2. 从已提交版本准备工作副本，只包含当前用户获权文件；私有临时目录与公共只读 Skill 分开。
3. 脚本只改工作副本，不能直接覆盖对象存储里已发布版本。
4. 结束执行/冻结可写进程后，由可信文件收集器读取候选产物，拒绝逃逸链接、异常类型与超额输出。
5. 对象存储先写不可变候选对象；扫描通过后，PG 事务创建 Artifact/WorkspaceVersion，并以预期 head_version 做 CAS 更新。
6. CAS 冲突不覆盖别人结果，保留隔离候选产物并提示冲突；首版单写者仍需用 CAS 防租约失效后的旧 Worker。
7. 发布成功后才使文件出现在正常项目列表；孤儿候选对象由生命周期任务清理。
8. 清理 workspace lease 与沙箱是可重试、幂等的后台操作，不删除已发布对象。

只读 Run 读取不可变提交版本，可与一个写 Run 并存，不直接看到未发布脏文件。多人共享项目不等于共享私有 Session。

## 11. 模型、上下文与预算契约

- 每个模型调用前检查数据分类是否允许该模型端点、是否有预算、Run 是否仍活跃。
- 工具结果和文档都有来源标记；上下文构建不能把其他 Session、被撤权知识或不属于该调用者的缓存拼进去。
- 会话内容被用户看过不等于可以永久继续发送给外部模型。撤权后新 Run 重建授权上下文；已披露给模型/人的内容无法承诺物理收回。
- ModelClient 缓存键包含授权模型配置/连接身份/凭据版本，不只 provider/model；撤销时关闭关联池。
- 预算按组织/部门/用户上限检查，PG 事务预留；每个模型调用记账，最终结算并释放未用额度。
- 没有 usage 的响应记 `unknown`/估算，失败前已经发生的计费也要记录；不能令 unknown=0。
- 自动重试只限明确暂时性网络/限流错误，遵守总 deadline、次数与剩余额度；已开始输出的调用是否重试必须显式处理重复内容和重复费用。
- 禁止为了“任务成功率”自动切换到不允许的数据地域、供应商或更高权限模型配置。

## 12. 版本与兼容迁移

- 当前 `/api/chat*` 继续作为明确标识的本地开发入口；生产路由仅开放 v2，不能保留旧 Token 的旁路。
- 若需短期兼容旧 UI，由服务端适配到 Run API，同样建立身份与权限，不直接调用旧 runner。
- 数据迁移采用 expand→回填→验证→切换→contract，旧版本兼容窗口至少覆盖一次灰度回滚。
- OpenAPI v2 从真实路由生成并纳入契约测试；不要直接把归档 `docs/api/openapi.yaml` 改成未经验证的“完整平台接口”。
- 关键字段和状态的变更必须同时修改后端、前端事件解析、DB 迁移、Worker 与测试矩阵。
