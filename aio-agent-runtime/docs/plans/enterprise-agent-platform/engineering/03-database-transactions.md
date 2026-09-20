# 03. 数据库字段、约束、锁顺序与事务配方

> 关联 DAT、RUN、IAM、SBX、GOV。SQL 是设计示意，未运行、未作为迁移提交；实现必须生成真实 Alembic 迁移并在临时 PostgreSQL 上验证。

## 1. 类型与字段通则

| 字段类别 | 建议类型/约束 | 不能采用的替代 |
|---|---|---|
| org/resource/run 等 ID | UUID；租户实体 unique(org_id,id) | ID 难猜代替授权 |
| 时间 | timestamptz UTC；有效期基于权威时间 | 客户端时间决定 lease 是否有效 |
| 状态 | text + CHECK 或明确迁移的 enum | 任意字符串随模块新增 |
| revision/generation/seq | bigint >= 0；比较后更新 | 进程内计数器 |
| 金额/价格 | numeric 或最小货币整数单位，显式 currency/price_version | float 累加 |
| 字节/数量 | bigint >= 0，有应用/数据库范围上限 | Content-Length 自报为唯一依据 |
| 内容 | immutable object ref + sha256 + size + classification | 所有正文/Secret 塞 JSONB |
| JSONB | 有 schema_version、大小/深度限制，非权威索引字段仍有独立列 | 无结构大 JSON 万能表 |
| Secret | SecretRef/credential_binding_revision | 密码列明文/日志回显 |
| opaque 外部 ID | 按供应商语义保存，带 connection/source 命名空间 | 自行 lower/trim/Unicode 归一化导致对象变化 |

普通用户身份数据可全局标识，但组织业务关系经 membership 关联；数据库不能因 users 是共享表就允许跨组织枚举用户 PII。

## 2. V1 核心字段补充

### 2.1 Run 与队列

```text
runs:
  org_id, id, session_id, project_id, actor_user_id
  state, state_revision, execution_generation, attempt_id
  agent_version_id, manifest_snapshot_id, model_config_version_id
  workspace_base_version_id, run_delegation_id
  queued_at, queue_expires_at, started_at?, deadline_at?
  next_event_seq, next_checkpoint_seq
  stop_reason?, outcome_code?, cleanup_state
  created_at, updated_at

jobs:
  org_id, id, aggregate_kind, aggregate_id, job_kind
  state, priority, not_before, attempt_count
  lease_owner?, lease_version, lease_expires_at?
  payload_ref?, created_at
```

- 同 Session 一个未解决 Run；`recovery_required` 也占此槽，但不保留计算资源。
- queue_expires_at 与 execution deadline 分开；started_at/deadline_at 第一次开始时固定，重启不刷新总时限。
- `cleanup_state` 表示 pending/cleaning/clean/failed，不将任务成功和沙箱销毁混成一个标志。
- Job 是调度事实，不负责消息正文和外部凭据。通知发 Redis 丢失后仍能按 PG 找到 Job。

### 2.2 Invocation、Approval 和派发记录

```text
invocations:
  org_id, id, run_id, logical_call_id, tool_version_id
  action_spec_ref, action_digest, canonicalization_version
  state, state_revision, risk_class
  credential_binding_id?, credential_revision?
  current_dispatch_id?, external_operation_key, downstream_result_ref?
  outcome_certainty: not_sent|confirmed|unknown

approvals:
  org_id, id, invocation_id, action_digest
  state, revision, eligible_policy_ref
  requested_by, decided_by?, decided_at?, expires_at
  decision_reason?, strong_auth_context_ref?

dispatches:
  org_id, id, invocation_id, execution_generation
  target_slot, dispatch_state, dispatch_token_id
  prepared_at, sent_at?, result_received_at?, terminal_at?
  downstream_request_id?, result_ref?, error_code?
```

Dispatch 是一次尝试的传输事实，`external_operation_key` 是稳定的业务去重键，不能因为 generation/网络重试改变。下游支持的幂等有效期/冲突语义必须记录；超过有效期不盲重发。

### 2.3 多 cell 与待核对阻断

```text
sandbox_leases:
  org_id, id, run_id, execution_generation
  target_slot, role: compute|connector|parser
  connector_binding_id?, security_profile_id, image_digest
  node_id, backend_resource_id?, state, revision, expires_at

workspace_blockers:
  org_id, id, project_id, workspace_id?, run_id, invocation_id?
  blocker_kind, affected_resource_scope, reason
  created_at, resolved_at?, resolved_by?, resolution_ref?
```

- `(org_id,run_id,generation,target_slot)` 唯一；同 Run 可以有多个权限不同的 cell，但全部计入配额。
- `target_slot` 由平台生成，例如 compute/main、connector/<binding-version>、parser/<job-id>；用户不能自由指定挂载和凭据。
- blocker 是持久业务阻断，不是必须持续心跳的进程 lease。核对未完成时禁止在受影响范围继续写，不无限保留容器。

### 2.4 版本与 ACL

内容版本的字段不可修改：digest、bytes、manifest、parser/chunker/embedding config、model endpoint 配置。发布状态/撤回与 Grant 另列状态/事件，可以变化，但不得覆盖内容。

所有需要给模型/用户的数据保存来源 `source_refs` 和 `derived_access_policy`，包括消息摘要和 Artifact；Secret 不作为可下载 Artifact 来源。

## 3. 必须存在的约束示意

```sql
-- 设计示意：实际表名/迁移需实现后验证。
CREATE UNIQUE INDEX uq_unresolved_run_per_session
ON runs(org_id, session_id)
WHERE state IN (
  'queued','preparing','running','waiting_approval',
  'persisting','cancel_requested','recovery_required'
);

CREATE UNIQUE INDEX uq_logical_tool_call
ON tool_invocations(org_id, run_id, logical_call_id);

CREATE UNIQUE INDEX uq_run_event_sequence
ON run_events(org_id, run_id, sequence);

CREATE UNIQUE INDEX uq_execution_target
ON sandbox_leases(org_id, run_id, execution_generation, target_slot);

CREATE UNIQUE INDEX uq_idempotency_scope
ON idempotency_keys(org_id, actor_id, operation, key_hash);
```

还要逐项实现：

- Run→Session/Project、Invocation→Run、Approval→Invocation、Artifact→Run/Project 的同 org FK。
- Session/Project 的所属关系不能跨 org，Run 引用的 session.project 与 run.project 一致。
- 每 workspace 一条 active writer lease；有效期由显式状态/事务处理，不能把 `now()` 放进动态唯一索引假装到期自动删除。
- 每 invocation 最多一个 pending Approval；允许保留旧 expired/invalidated 审批历史。
- Ledger 去重键在 producer/请求/事件范围内唯一；provider_request_id 可能只在某连接/供应商内唯一，不能全局误去重。
- 金额/bytes/sequence 非负、revision 单调、状态 transition 由服务与 CAS 控制。
- 部门/项目 role/Grant subject 如果是多态引用，必须有可验证的主体登记/领域检查，不用失去 FK 的自由字符串悄悄跨 org。

## 4. Run 与 Manifest 的插入顺序

原计划 Run 引用 snapshot，snapshot 又标 run_id。实现不能插入两个互相立即 FK 引用的非空新行。

V1 建议：预分配 run_id/snapshot_id；snapshot→run 这一个 FK 设 `DEFERRABLE INITIALLY DEFERRED`，Run→snapshot 仍正常校验。同事务：先插 snapshot（含计划 run_id），再插 Run 指向已存在 snapshot，提交时延迟 FK 校验通过。也可选择单向归属 schema，但要修改契约和验证唯一关联。

- 提交后不允许运行 Run 缺 snapshot。
- 不能先提交一个不完整 Run 再后台补权限清单。
- Snapshot 内容不是最新权限；调用时重新授权。
- 使用 DB deferred constraint 的变更必须有空库、回填、失败回滚和并发测试，不只看 ORM 能实例化。

## 5. 全局加锁顺序

只锁本次需要的行，但所有涉及相同对象的事务按以下顺序。读取 ID 以便定位可以在事务前/锁前做，但加锁后必须重新检查状态/关联。

| 级别 | 对象 | 同级排序 |
|---|---|---|
| L0 | idempotency 记录 | scope/key_hash |
| L1 | org policy、membership、resource ACL anchor | 对象类型固定序 + org/id |
| L2 | Project/Session/Workspace/Document 的聚合根 | 对象类型固定序 + id |
| L3 | 预算/节点容量/资源计数行 | 固定 domain/scope_rank/period/currency/id |
| L4 | Run | run_id |
| L5 | Job | job_id |
| L6 | Sandbox/Workspace lease | lease kind/id |
| L7 | Invocation/Dispatch | invocation_id、dispatch_id |
| L8 | Approval | approval_id |
| L9 | 待发布 Artifact/Version 与其状态行 | resource type/id |

事件、Outbox、Ledger、Audit 通常追加写；如需锁其中已有行，列入统一顺序评审。业务事实出网之前提交事务，不把模型调用、对象传输、容器管理或用户等待放在行锁期间。

### 5.1 Job 领取为何不能简单先锁 Job 后锁 Run

另一条路径可能先锁 Run 再更新 Job；反向顺序会死锁。建议候选扫描只是读取，然后 `FOR UPDATE OF run SKIP LOCKED` 锁聚合根，再锁匹配 Job 并复核未领取状态。摄取类 Job 先锁对应 Document 聚合根再锁 Job。

`SKIP LOCKED` 只提供并发协调，不自动保证组织公平或权限。候选选择仍要有队列配额和长期等待老化。

### 5.2 重试范围

- 只对明确未发生外部副作用的纯 DB 事务，在 serialization/deadlock 等暂时性错误时有限重试，建议最多 3 次且受总期限限制。
- 不把整个“调 MCP 然后写库”函数套进数据库 retry decorator。
- 唯一键冲突属于业务幂等/资源忙，不随便换 ID 重发。
- 锁超时给稳定错误和 retry-after，不能放开唯一约束“解决并发”。

## 6. 十个事务配方

<a id="tx-01"></a>
### TX-01 — 原子创建 Run

**输入**：验证过的 Principal、Session、message/input refs、expected_session_revision、Idempotency-Key。**外部 IO**：事务外准备模型/能力元数据，事务内只重新确认不可变版本与当前权限。

1. 校验输入 schema/大小、当前身份/资源；计算带 canonicalization_version 的请求摘要。
2. `INSERT ... ON CONFLICT` 建幂等 scope，并锁 L0；已有同摘要记录须再次授权后返回原 Run，异摘要 409。
3. 依序锁授权 anchor、Session/Workspace anchor、预算行；复核当前权限、active Run/blocker、revision。
4. 预分配 IDs；插 snapshot、消息、Run、预算 reservation、Job、起始事件、Outbox/audit。
5. 更新 session revision、next message seq；保存 idempotency response_ref。
6. 提交成功才返回 202。提交前失败整批回滚；提交后响应丢失靠相同 key 找回，不重复任务。

**断言**：一个成功事务产生一份完整任务事实；没有 Job/预算/事件的半 Run 不可见。失败的 4xx 输入不消耗 Run 配额。

<a id="tx-02"></a>
### TX-02 — 领取 Job 与 execution_generation

1. 公平候选扫描（不占长期锁）；按 L4/L5 锁 Run/Job。
2. 验证 queued/not_before/queue TTL、未被取消；原 Job lease 有效则不抢。
3. 递增 generation、创建 attempt、写 lease owner/expiry，首次开始时固定 deadline。
4. 按任务阶段设置 preparing 或可恢复状态，追加领取事件。
5. 提交后 Worker 才可请求 manager。后续动作带当前 generation；DB 不可达不继续新增危险动作。

**断言**：同一 Run 同时最多一个有效执行代次；旧 Worker 不能凭进程仍活着继续调用。

<a id="tx-03"></a>
### TX-03 — 计划工具与审批请求

1. 校验新 logical_call_id 或读取已有调用；同 ID 不同 action_digest 是冲突，不重定义。
2. 按锁序读取/锁当前授权、Run、Invocation，确认代次和期限。
3. 固定 ActionSpec 内容引用和摘要、工具/凭据版本、risk、资源范围；创建 invocation。
4. 需审批则创建 pending Approval、checkpoint、run.waiting_approval 和事件；不需则状态 authorized。
5. 同事务写意图/审批事实。提交后向 UI 发通知，不持事务等待用户。

**断言**：审批 UI 所见动作与之后派发动作摘要一致；旧审批不能批准另一份代码。

<a id="tx-04"></a>
### TX-04 — 审批决定

1. 当前批准者验证身份、强认证、资源范围；定位记录但不暴露无权内容。
2. 依序锁授权 anchor、Run、Invocation、Approval；重新检查 pending、期限、Run 状态和摘要。
3. CAS 写 approved/rejected、decided_by/at/reason；职责分离和当前政策必须满足。
4. 更新 Invocation/Run/checkpoint 可继续状态和事件/Outbox；重复同决定返回同事实，冲突决定 409。
5. 提交后唤醒 Worker；决定 approved 不等于已经发出业务请求。

**断言**：审批中并发撤权/取消后不得凭旧结果派发；执行前仍走 TX-05。

<a id="tx-05"></a>
### TX-05 — 派发前最终授权与稳定操作键

1. 当前身份/资源、预算、Run、lease、Invocation、Approval 按锁序校验。
2. 比对 ActionSpec、输入/代码/连接/工具版本；已过期或被替换则 invalidated，不执行。
3. 创建唯一 dispatch attempt 与稳定 external_operation_key；持久 state=prepared 和意图审计。
4. 提交后 dispatcher 检查 deadline/授权版本与目标 lease，再把请求发往受控执行边界。
5. 请求可能发出后发生连接错误，不能假设 not_sent；按已知事实进入 TX-06/待核对。

**断言**：数据库记录必须先于副作用；事务外的网络不可能与提交成为通用原子操作，不承诺 exactly-once。

<a id="tx-06"></a>
### TX-06 — 记录工具结果和 checkpoint

1. 验证结果所属 dispatch，来源通道、generation 与当前调用是否匹配；沙箱 stdout 只作不可信输出。
2. 结果大对象先以不可变 key 安全保存；数据库事务内只保存校验后的引用。
3. 按锁序记 outcome confirmed/unknown、Invocation 状态、工具结果引用、usage 事实和下个 checkpoint/事件。
4. 旧代次的迟到结果可以作为隔离审计/核对证据，但不能修改新代次状态或推进游标。
5. 结果记录失败保留可核对事实，不自动重发工具。

**断言**：输出接收、工具成功、业务效果已确认是不同概念；不能因为 HTTP 200 就把不明写判成功。

<a id="tx-07"></a>
### TX-07 — 取消与创建待核对阻断

1. 按授权与聚合根顺序锁资源、Run/Job/Invocation，验证请求者可取消。
2. queued/未开始任务可直接 cancelled；运行中变 cancel_requested，禁新调用并发 Outbox stop。
3. 若存在效果不明写或环境无法安全恢复，设置 recovery_required，创建必要 resource blocker。
4. manager 外部终止 cell；确认结果另事务更新 cleanup，不以 stop 消息投递成功当销毁成功。
5. 核对者提供证据终结 Run/blocker；解除 blocker 不自动重新运行旧任务。

**断言**：取消不等于回滚外部业务；计算资源释放不等于未解决业务约束全部释放。

<a id="tx-08"></a>
### TX-08 — 发布 Artifact 与 WorkspaceVersion

1. 停止/冻结相关 writer；可信 collector 验证候选文件/类型/hash/大小/来源策略并存 quarantine。
2. 扫描完成后按 L1/L2/L4/L6/L9 锁权限、Workspace、Run、writer lease、candidate。
3. 确认当前授权、generation、base head、lease、scan ready 和来源/分享范围。
4. 创建 immutable version/Artifact 引用，CAS 更新 head；状态/事件在同一事务发布。
5. 失败不公开候选；孤儿对象走限定 TTL 和引用检查后清理。发布冲突不覆盖别人的新版本。

**断言**：数据库是可见性的开关，传到对象存储不等于已对用户发布。

<a id="tx-09"></a>
### TX-09 — 用量记账、预留结算与调整

1. 定位明确 budget scope/price_version，按 L3→L4 顺序锁预算和 Run。
2. 根据 producer/request/event 键插唯一 Ledger；重复事实不再次 charge。
3. actual/estimate/unknown 分开，未知费用保守占额并进入对账，不能释放成免费。
4. 终态释放未使用的明确预留，必要后续调整追加 ledger event，不覆盖原始量。
5. 与状态/usage event 事务一致；外部账单超出预留时记录 debt/overage 并阻止新调用，不能拒收真实费用事实。

**断言**：预算上限约束新增调用，不保证外部延迟收费绝无偏差；所有差额可核对。

<a id="tx-10"></a>
### TX-10 — 权限/文档删除和不可复活发布

1. 以 L1/L2 锁授权或文档 anchor，验证管理动作和当前 revision。
2. 递增 ACL/deletion epoch，状态不可读，记录当前 tombstone/审计/Outbox。
3. 提交后拒绝新的读取/调用；异步取消相关任务、失效缓存、清除索引/对象/派生内容。
4. 任何旧 Job 发布前比较 epoch，旧版本不能重新 ready。
5. 备份恢复先重放当前撤权/删除事实；无法确认则保持关闭。

**断言**：物理清理失败不恢复访问；旧备份不意味着重新授予权限。

## 7. 迁移批次与数据回填

| 批次 | 主要对象 | 先决/验证 |
|---|---|---|
| DB-A | 角色、连接、迁移锁、identity/org/project/resource | 空库升级、非高权账号、复合 FK |
| DB-B | Session/版本引用、Run/Job/events/outbox/idempotency | 延迟 FK 顺序、状态/唯一约束、旧数据映射 |
| DB-C | Invocation/Approval/Dispatch/checkpoint/delegation | 重复 logical call、审批历史、未知效果 |
| DB-D | 多 cell lease、writer lease/blocker、Artifact/version | target_slot 唯一、旧 lease 补默认 compute/main、CAS |
| DB-E | Budget/reservation/ledger | numeric/货币/去重键/unknown 状态 |
| DB-F | KB/chunks/ACL/deletion、连接/SecretRef、治理 | 增量 epoch、引用完整性、没有明文 Secret |
| DB-G | RLS 强化、索引优化、非空约束收紧 | 回填完成后 VALIDATE，不在线删新事实 |

批次是依赖层次，实际迁移可细分；RLS 默认拒绝必须随租户表一起建立，DB-G 不是允许前面无 RLS 对外运行。

每次迁移：导出 schema/行计数与一致备份→干净库升级→旧 fixture 升级→双组织负例→版本兼容测试→回滚/前向修复演练。不能把修改 Python ORM 当成数据库已经迁移。
