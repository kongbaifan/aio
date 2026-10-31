# 平台持久审计与结构化元数据契约

> 当前代码契约（GOV-02 Slice A + B），不是合规认证或生产 Gate。实现：`app/observability/{audit,redaction,archive}.py`、`app/db/schema_v1{4,5}.py`、`migrations/versions/001{4_audit_records,5_audit_archive}.py`、`app/db/{engine,provisioning}.py`。计划与证据见 [实施计划](../implementation/audit-redaction-plan.md)。

## 1. 语义

- 审计事实写在 `aio_audit_events`，与业务状态变更**同一 PG 事务**提交。审计插入失败即整事务回滚，不存在“先执行、稍后补日志”。
- 唯一写入口是 `audit.record(c, principal, action, resource_id, outcome, metadata, ...)`。`action` 必须在 `CONTRACTS` 中登记，`outcome` 必须属于该 action 的封闭词表，`metadata` 必须**恰好**是该 action 的封闭 pydantic 模型实例（`extra="forbid"`，实例也会重新校验）。传 `dict`、错模型、未知 action/outcome、`model_copy` 篡改值都在写库前被拒为 `AUDIT_METADATA_INVALID`，错误不回显输入。
- 元数据字段只允许 UUID、角色/权限/结论等枚举、revision、计数、RFC 8785 摘要和受限十进制金额；没有任何自由文本字段。prompt、工具参数/结果、文件内容、凭据、header、异常体在结构上无法进入审计行。需要关联自由文本时只存其摘要（例如核对的 `evidence_digest`）。
- `trace_id` 只取边界中间件为每个 HTTP 请求生成的 UUID（与 `X-Request-ID` 响应头一致），忽略客户端 `traceparent`/`X-Request-ID`；Worker 路径为 NULL。这不是分布式追踪（GOV-08）。
- 历史行不回填：v14 之前的行 `metadata_schema='legacy'`，新列为 NULL。

## 2. 高风险 fail-closed

以下路径在写入事实后，于同一连接内用 `require_recorded(c, ..., event_id=...)` 校验**本次**新事实行（精确 id/action/主体/actor/run/schema）存在，缺失即 `AUDIT_SINK_UNAVAILABLE`（503），不返回结果：

| 路径 | action |
|---|---|
| `prepare_dispatch` | `tool.dispatch_prepared` |
| `consume_dispatch`（返回 `DispatchPermit` 前） | `tool.dispatch_consumed` |
| 审批决定 | `approval.decide` |
| 未知效果核对（清除 blocker 前） | `run.reconcile` |
| 审计查询（返回行前） | `audit.read` |

数据库错误一律映射为 `AUDIT_SINK_UNAVAILABLE`，`from None` 截断异常链，不回显 SQL/参数/触发器消息。Worker 在 consume 审计失败时 abort 为 `failed`，dispatch 为 `not_sent`，外部 sink 未收到请求。

`record()` 还校验事务的 `aio.org_id` 与 principal 的组织一致；不一致按不可用拒绝，特权连接也不能替另一个租户写审计。

## 3. 数据库约束（v14）

- 新列：`trace_id, resource_kind, decision, reason_code, policy_revision, subject_revision, risk_class, metadata_schema`。
- CHECK（`NOT VALID`：不校验历史行，但约束所有新 INSERT，含表 owner）：`metadata_schema = action || ':v1'` 且非 `legacy`；`metadata` 为 JSON object 且 `pg_column_size <= 4096`；trace 为 32 位小写十六进制且非全零；decision / risk_class / resource_kind 为封闭枚举；revision 非负。实测 4 KiB 上限按未压缩值计算，可压缩的大段正文同样被拒。
- 索引 `ix_aio_audit_org_created_id (org_id, created_at DESC, id)` 支撑分页，`EXPLAIN` 断言无 Sort 节点。
- **有意例外**：`run_id`/`resource_id` 不加复合组织外键。审计事实必须在主体删除后继续存在；外键会阻塞删除或诱导 `ON DELETE CASCADE` 抹掉审计，且会在 `aio_runs` 上引入 `FOR KEY SHARE` 改变锁序。组织一致性由 `record()` 的 scope 校验和 FORCE RLS 保证。
- `aio_outbox` 增加投递簿记列 `next_attempt_at, last_error_code, lease_owner, leased_until` 与对应 CHECK/部分索引。v15 另加只覆盖 `kind='audit.archive'` 待投递行的 `ix_aio_outbox_audit_pending (org_id, next_attempt_at, id)`：其他 kind（`run.event.available` 等）目前无消费者、会一直待投递，不能让 relay 每次扫过它们。

## 3a. 归档投递（v15，GOV-02 Slice B）

- `record()` 在写事实的同一事务里插入一条 `aio_outbox(kind='audit.archive', aggregate_id=<audit id>, payload={})`。它只是指针：relay 投递时重新读审计行，不复制内容。事实回滚则指针一起回滚；审计写失败（`AUDIT_SINK_UNAVAILABLE`）时不会有指针。
- `0015_audit_archive` 为 v14 已写入的结构化事实补指针（`NOT EXISTS` 防重复，需 RLS 豁免身份）；`legacy` 行没有封闭契约，不归档。降级只删索引，保留指针。
- 投递单元 `ArchiveRecord` 恰好是审计行的类型化列 + 按 action 契约重新校验的 metadata（`extra="forbid"`）。指向的事实不存在或不能投影为封闭记录时不发送，记 `ARCHIVE_RECORD_INVALID`。
- `AuditRelay` 三段式，每段独立：
  1. **claim**：短事务内 `SELECT ... FOR UPDATE OF aio_outbox SKIP LOCKED LIMIT n` 取到期且租约空/过期的行，写 `lease_owner/leased_until`。只锁 outbox 行，不取组织/Run/预算锁，与既有锁序前缀无交集（`pg_locks` 测试断言）。
  2. **send**：事务外、不占用连接池连接，调用 sink，带超时。sink 必须按 `idempotency_key = "<org_id>:<audit_id>"` 去重；投递语义是至少一次。
  3. **finish**：短事务，**以 `lease_owner` 为栅栏**：失去租约（已被另一 relay 接管）的旧 relay 什么都改不了。成功写 `delivered_at`；失败 `attempts+1`、`next_attempt_at` 指数退避（5s 起翻倍，上限 15 min，无上限次数，不丢弃事实），`last_error_code` 只存固定词表（`ARCHIVE_UNAVAILABLE / REJECTED / TIMEOUT / DELIVERY_FAILED / RECORD_INVALID`），sink 的异常文本从不入库或写日志。
- 租约必须长于发送超时（构造时校验），否则另一个 relay 可能在发送中途接管。
- **两类故障分离**：PG 审计写失败是 `AUDIT_SINK_UNAVAILABLE`，拒绝动作；归档不可达只表现为 backlog。`backlog()` 返回待投递数、重试中数、最老待投递秒数和错误码计数；超过 `backlog_alert_seconds` 时为 `AUDIT_ARCHIVE_BACKLOG`，`serve()` 只记一条 warning（组织与计数，无内容）。这个码不进入任何业务响应。
- **当前边界**：只有契约一致的 fake sink；**没有真实归档/SIEM 适配器，`run_worker.py` 也未启动 relay**，因此部署后指针会累积在 outbox 中（PG 事实不受影响），接入适配器后从最早的事实开始补投。backlog 未导出为指标，也没有管理 API。

## 3b. 出口脱敏（GOV-02.04，Slice C）

`app/observability/scrub.py` 提供唯一的 `scrub()`，两条规则同时生效，**都不靠密钥前缀正则**（未标记、也不是已知密钥的 `sk-…` 之类原样保留）：

1. **结构规则**：工具 `input_schema` 中 `"x-aio-sensitive": true` 的字段（跟随 `#/$defs` 引用、allOf/anyOf/oneOf、数组与对象子树）。标记必须是布尔 `true`。标记在 `input_schema` 里，所以进入 `definition_digest`：发布后摘掉标记，Run 清单校验失败（`TOOL_VERSION_CHANGED`），不会悄悄停止脱敏。
2. **已知密钥规则**：本次调用中被标记字段的实际值 + 进程登记的凭据（`register_material`：OIDC client secret、Manager/Connector token、数据库口令、运行时解析的模型 key），以原文、percent、base64、base64url 出现在任意字符串或字典键中都替换为 `[credential-redacted]`。短于 8 字符的值不当作密钥。

接入点：

| 出口 | 处理 |
|---|---|
| 工具结果（`complete_dispatch`） | 写 dispatch/invocation 行、检查点 tool 消息（下一轮发给模型）、`tool.completed/failed` SSE 事件之前统一 scrub 一次，再重新做大小上限 |
| 驱动异常 | 原本就只存固定码（`EXECUTION_FAILED` / `NotDispatched.code`）；新增用例证明异常文本里的密钥不进任何行、事件或日志 |
| 审计 `record()` | 封闭模型之外再做纵深断言：序列化后含已知密钥即拒绝（`AUDIT_METADATA_INVALID`），不替换后放行 |
| 归档投递 | `ArchiveRecord` 含已知密钥即不发送（`ARCHIVE_RECORD_INVALID`） |
| 日志 | API 与 Worker 启动时给根 logger 装 `MaterialLogFilter`，消息参数与 traceback 中的已知密钥被替换 |
| 连接器网关 | `normalize_result` 与发现阶段的回显检查改为覆盖凭据的四种编码（网关不导入平台代码，独立实现同一规则） |

**不处理（有意）**：`invocations.arguments`、检查点里助手自己的 `tool_calls` / `pending_calls`、`model_calls.response` 保留模型产生的原始参数。它们是派发与模型续轮必需的内部状态，不经 SSE、API 响应、审计或归档出口；值本来就是模型给出的。

**未做**：MCP 服务器发布的工具 schema 来自服务器本身，目前没有操作员侧给它们加标记的入口；沙箱导出文件内容不扫描；环境变量绑定的 stdio 凭据在网关内按同一规则处理，平台进程不持有其值，因此不在平台登记。

## 4. 权限

- Runtime 角色对 `aio_audit_events` 只有 SELECT/INSERT；对 `aio_outbox` 无 DELETE，仅可 UPDATE 六个投递簿记列。`grant_runtime_access` 每次刷新先 REVOKE 表级与全部列级 UPDATE/DELETE 再授予，旧授权不会残留。
- `Database.verify_runtime_role()` 启动时拒绝任何审计 UPDATE/DELETE 或 outbox 事实列 UPDATE 授权（`PlatformConfigurationError`）。
- 审计查询限 `org_admin` / `auditor`；`operator` 与普通成员 403。返回列不含 `metadata`。每次查询同事务写一条 `audit.read`（scope、limit、实际行数、时间窗与游标），写入失败则查询失败。
- 分页：`limit<=200`，`since`/`until`/`before_created_at` 必须带时区，游标 `(before_created_at, before_id)` 必须成对，`since < until`；否则 422 `AUDIT_QUERY_INVALID`。

## 5. 迁移

`0014_audit_records` 只加列、CHECK、索引，不回填、不需要 RLS 豁免身份。`downgrade` 要求 RLS 豁免身份（防止空视图被当成“没有新事实”），存在任何非 `legacy` 行即拒绝，避免丢失结构化事实的语义标记。

## 6. 未包含（见计划第 7、8 节）

真实归档适配器、relay 进程接入与 backlog 指标导出（见 3a）；`x-aio-sensitive` schema 标记、五出口统一 `scrub()`、替换 `_SECRET_PATTERN` 与网关 `replace`（Slice C）；保留策略（OPS-03）；support grant（GOV-05）；kill switch（GOV-04）；真实 SIEM/归档后端。
