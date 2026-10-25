# 平台持久审计与结构化元数据契约

> 当前代码契约（GOV-02 Slice A），不是合规认证或生产 Gate。实现：`app/observability/{audit,redaction}.py`、`app/db/schema_v14.py`、`migrations/versions/0014_audit_records.py`、`app/db/{engine,provisioning}.py`。计划与证据见 [实施计划](../implementation/audit-redaction-plan.md)。

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
- `aio_outbox` 增加投递簿记列 `next_attempt_at, last_error_code, lease_owner, leased_until` 与对应 CHECK/部分索引；**当前没有 relay 消费者**（Slice B）。

## 4. 权限

- Runtime 角色对 `aio_audit_events` 只有 SELECT/INSERT；对 `aio_outbox` 无 DELETE，仅可 UPDATE 六个投递簿记列。`grant_runtime_access` 每次刷新先 REVOKE 表级与全部列级 UPDATE/DELETE 再授予，旧授权不会残留。
- `Database.verify_runtime_role()` 启动时拒绝任何审计 UPDATE/DELETE 或 outbox 事实列 UPDATE 授权（`PlatformConfigurationError`）。
- 审计查询限 `org_admin` / `auditor`；`operator` 与普通成员 403。返回列不含 `metadata`。每次查询同事务写一条 `audit.read`（scope、limit、实际行数、时间窗与游标），写入失败则查询失败。
- 分页：`limit<=200`，`since`/`until`/`before_created_at` 必须带时区，游标 `(before_created_at, before_id)` 必须成对，`since < until`；否则 422 `AUDIT_QUERY_INVALID`。

## 5. 迁移

`0014_audit_records` 只加列、CHECK、索引，不回填、不需要 RLS 豁免身份。`downgrade` 要求 RLS 豁免身份（防止空视图被当成“没有新事实”），存在任何非 `legacy` 行即拒绝，避免丢失结构化事实的语义标记。

## 6. 未包含（见计划第 7、8 节）

Outbox relay 与归档投递、两类故障分离（Slice B）；`x-aio-sensitive` schema 标记、五出口统一 `scrub()`、替换 `_SECRET_PATTERN` 与网关 `replace`（Slice C）；保留策略（OPS-03）；support grant（GOV-05）；kill switch（GOV-04）；真实 SIEM/归档后端。
