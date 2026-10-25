# 持久审计、结构化脱敏与高风险失败策略：实施计划

> 2026-09-16。承接已验证的 v13 组织/部门共享预算增量。对应 GOV-02.01–.06；不替代 GOV-01/04/05/07、MCP-06 或任何生产 Gate。

## 0. 先修正立项理由：原判断的结论对，依据错

本计划确认 **GOV-02 是下一个增量**，但必须先纠正三处会误导实施的前提，否则会去改一个不在生产路径上的文件。

### 0.1 「生产行为是仅 JSONL 且写失败继续」——对文件的描述正确，对生产路径的判断错误

`apps/local-harness/app/audit.py` 确实是 59 行、JSON Lines、`except OSError: return`：

```python
        except OSError:
            # 审计磁盘不可写时由健康检查暴露，不在这里中断 Agent 主流程。
            return
```

但 `AuditLogger` 的全部构造点只有两处，都在旧模式：`app/main.py:94` 位于 `RuntimeContainer.__init__`，而该构造函数第一条语句是 `require_legacy_mode()`；另一处是可选旧入口 `apps/local-harness/mcp_server.py:36`。平台路径 `create_app` 在 `deployment_mode() is not LEGACY_LOCAL` 时直接转交 `create_platform_app`，`app/api/v2/` 与 `app/runtime/` 全树没有任何 `AuditLogger` 引用。

即：**卡片要替换的「仅 JSONL 且写失败继续」行为，在平台模式下已经不存在**。平台审计写的是 `aio_audit_events`，共 52 个调用点，全部通过 `AdminService.audit(c, ...)` 或 `PlatformService._audit(c, ...)` 使用**调用方传入的同一个连接**，因此与业务状态变更同事务。该表已在 `append_only` 授权集合内（runtime 角色只有 SELECT, INSERT），且属于 `TENANT_TABLES`，`0001_platform.py` 对其 `ENABLE` + `FORCE ROW LEVEL SECURITY`。

### 0.2 「GOV-02.02 是可核对真实外部写的唯一未满足前置」——依赖边真实，但该子任务大半已由 RUN-08/09 结构性满足

依赖边逐字如 `dependencies-and-gates.md` 所载：

| 后继子任务 | 必须已完成的前置子任务 | 原因 |
|---|---|---|
| MCP-06.03 | RUN-08.04, RUN-09.04, GOV-02.02 | 写请求前完成授权/意图/未知结果契约 |
| CAP-01.04 | RUN-08.03, GOV-02.02 | 高风险调用需要持久审批和意图 |
| UI-08.06 | GOV-03.06, GOV-05.06, GOV-02.06 | 管理台不是未授权正文后门 |

GOV-02.02 原文是两半：「外部写的意图/审批/调用状态在执行前可靠保存；数据库/审计不可写即拒绝新高风险动作。」

- 第一半已交付：`aio_invocations`（`action_digest`/`external_operation_key`/`risk_class`/`revision`）+ `aio_approvals`（`action_digest`/`requires_different_actor`/`expires_at`）+ `aio_dispatches`（`prepared → dispatching → succeeded|failed|not_sent|unknown`、`operation_key`、`outcome_digest`）。
- 第二半在 PG 侧**已由事务原子性结构性成立**：`prepare_dispatch` 的 `insert(s.dispatches)` 与 `self.platform._audit(...)` 在同一 `locked()` 事务内（`runtime/execution.py:915-926`），审计插入失败即整事务回滚，不会留下可消费的 dispatch 行，因此不会产生外部效果。这正是 ECASE-34 要求的「PG 意图失败时 dispatch/effect_count=0」。

所以把 GOV-02.02 描述成「未开始」是不准确的；它缺的是**一处真实空洞**和**全部负例证据**，见 0.3 与第 1 节。

### 0.3 真正未交付的部分（这才是本增量的价值）

1. **`aio_outbox` 没有任何消费者**。全仓对该表只有三处 `insert`（`runtime/service.py:75`、`runtime/service.py:802`、`runtime/execution.py:1275`），`delivered_at` 与 `attempts` 在产品代码中**从未被读取或更新过**。GOV-02.03「Outbox 向归档/日志系统投递可重试」完成度为 0。
2. **`consume_dispatch` 没有审计行**。它把 dispatch 推进到 `dispatching`、`sent_at=now` 并返回 `DispatchPermit`（即真正授权对外发送的那一步），只写了 `tool.started` 事件，没有 `_audit` 调用。高风险动作最关键的一跳缺少审计事实。
3. **脱敏只有正则和字面量替换**，正是卡片明令禁止的形态：`llm/openai_compatible.py` 的 `_SECRET_PATTERN`（`sk-`/`Bearer`/`AIza`/`gh[pousr]_`/`xox[baprs]-` 前缀）与 `services/connector-gateway/.../protocol.py:117` 的 `value.replace(secret, "[credential-redacted]")`。没有任何 schema 级敏感标记。
4. **审计读取自身不留痕**。`AdminService.audit_events` 限定 `org_admin`/`auditor` 角色（这部分已达标），但不插入任何 `audit.read` 行，也没有导出端点。GOV-02.05「访问审计自身也留痕」未满足。
5. **字段集不完整且 metadata 无界**。`aio_audit_events` 只有 `actor_id`/`service_actor_id`/`run_id`/`action`/`resource_id`/`outcome`/`metadata`。全仓 grep 无 `trace_id`；没有 `decision`/`policy_revision`/`resource_kind`；`metadata` 是自由 JSONB，从未经过 `bounded_json`，`AdminService.audit` 的第五参数接受任意 `dict`。`PlatformService._audit` 则恒传 `metadata={}`，运行时审计行没有任何细节。
6. **零负例**。全仓没有任何测试涉及审计写失败、归档中断、重复投递、脱敏边界或跨组织审计列表。

### 0.4 前置条件已满足，可立即开工

- **DAT-03**（Run/审批/事件/Job/outbox/幂等键/checkpoint 持久结构）已交付：`README.md` 第 1 节「Run、消息、Job、ManifestSnapshot、预算预留、起始事件和幂等响应在同一事务提交」「严格 JSON + RFC 8785 摘要、固定 ActionSpec、持久审批、双人职责分离」，61 张表含 `aio_runs`/`aio_approvals`/`aio_invocations`/`aio_dispatches`/`aio_run_events`/`aio_outbox`/`aio_idempotency_keys`/`aio_checkpoints`。
- **IAM-04**（默认拒绝 PolicyService）已交付：`app/policy/service.py` 的 `authorize()` 返回 `Decision(kind, reason, policy_revision, resource_revision)`，facts 由 `app/policy/repository.py` 从受信仓储读取；`README.md`「不可变 Principal、当前 facts 的默认拒绝授权、用户级资源 Grant、组织策略与数据等级上限」。

因此**没有依赖阻塞**。另需诚实记录：`stages/README.md` 第 46 行「`GOV-01/02/04/07` 的数据策略、持久审计、应急禁止和模型配置安全，在 P2 开放任何执行路径前可用，而不是等 P5」——执行路径（Python compute、stdio、parser）在代码中已开放，故 GOV-02 确属逾期；但同一句里的 GOV-01（`policy/data.py` 不存在）与 GOV-04（`policy/kill_switches.py` 不存在）同样逾期，GOV-02 并非唯一逾期项。选它的理由是下游扇出最大（MCP-06.03、CAP-01.04、UI-08.06、GOV-05、GOV-08 均指向它），不是它唯一。

## 1. 必须成立的业务/安全语义

1. **审计事实是业务动作的同事务组成部分，不是旁路日志。** 高风险动作的意图行与状态变更必须同事务提交；审计插入失败即整事务回滚，不得降级为「先执行、稍后补日志」。这条对应 INV-26「高风险副作用之前有可靠授权/审批/意图审计」的反面「先执行，稍后日志失败当没发生」。
2. **权威事实在 PG，归档是投递副本。** PG 审计行写入成功即动作可继续；外部归档/日志系统不可达只产生 backlog 与告警，不阻断只读请求，也不阻断已获权动作。两类故障必须由不同的错误码与不同的指标区分，任何一方都不能冒充另一方。
3. **审计记录的字段集是封闭的。** `actor`/`service_actor`/`org`/`run`/`action`/`resource`/`resource_kind`/`policy_revision`/`decision`/`outcome`/`trace` 为固定列或封闭类型的元数据；正文（prompt、工具参数、工具结果、文件内容、模型回答、异常体、截图）与元数据分存，审计表只存元数据与摘要。
4. **脱敏由类型系统结构性保证，不由调用方自觉。** 审计元数据不接受自由 `dict`；每个 action 有一个 `extra="forbid"` 的封闭模型，字段类型限于 UUID、布尔、有界整数、枚举、摘要十六进制串与受限十进制字符串。**不存在能容纳自由文本的字段**，因此 prompt/参数/凭据/文件内容在结构上无法到达审计行；正则只作为纵深防御的二次断言，不作为主机制。
5. **敏感性在 schema 声明，覆盖全部出口。** 工具 `input_schema`、MCP 连接配置、环境变量绑定在定义处标注敏感字段；同一标记统一约束 header/query/body/env/异常链五个出口。任何未标注但命中凭据物料的值一律按敏感处理（保守方向），不因未标注而放行。
6. **审计的读取本身是被审计的动作。** 审计查询/导出限 `org_admin`/`auditor`；每次查询在同事务写入一条 `audit.read` 行（含 scope、行数、时间窗），且该行同样不含正文。普通运维（`operator`）默认无审计正文读取权；限时 support grant 属 IAM-09/GOV-05，不在本增量放开。
7. **跨组织不可见、不可推断。** 审计列表/导出/投递按 org 隔离，FORCE RLS 之外还要有正向断言：他组织身份读到零行，错误只给受限 scope，不泄漏他人 `actor_id`、资源存在性或内部路径。
8. **审计行只追加。** 已写入的审计事实不得 UPDATE/DELETE，包含管理员与 runtime 角色。投递簿记（`delivered_at`/`attempts`/`next_attempt_at`）与审计事实分列授权：前者可改，后者不可改。
9. **重复投递不产生重复事实。** 归档侧至少一次投递语义下，投递方必须携带稳定幂等键（审计行 `id` + `org_id`），重放不改变 PG 事实，也不重复计数 backlog。
10. **降级方向永远保守。** 审计不可写时拒绝新高风险动作；已经发生的外部影响必须保留为待核对事实，不因审计故障被改判为「未发生」。不得以关闭审计来恢复写工具（卡片回滚条款原文：「保留权威审计表，不以关闭审计『恢复写工具』」）。

## 2. 数据与迁移

需要一个新迁移。当前 head 经本文作者独立核对为 `0013_shared_budgets`（`app/db/engine.py:17` 的 `SCHEMA_REVISION`、`migrations/versions/0013_shared_budgets.py` 的 `revision`），`metadata.tables` 实测 **61** 张表（`TENANT_TABLES` 58 + `BOOTSTRAP_TABLES` 3）。新迁移为 `0014_audit_records`，`down_revision = "0013_shared_budgets"`，v1–v13 快照保持不可变。

### 2.1 `aio_audit_events` 扩列（不重写既有行）

新增全部可空列，既有行保持原值，不回填伪造字段：

- `trace_id VARCHAR(64)`：W3C trace-id 十六进制，仅低基数关联用，不含业务语义。
- `resource_kind VARCHAR(32)`：与 `policy/service.py` 的 `OWNER_ACTIONS` 键一致的封闭集合，`CHECK` 约束枚举。
- `decision VARCHAR(24)`：`allow|deny|approval_required`，与 `DecisionKind` 对齐，`CHECK` 约束。
- `reason_code VARCHAR(64)`：复用 IAM-04.05 已固定的 `reason_code`，不新造词表。
- `policy_revision BIGINT`：决策时的组织策略版本。
- `subject_revision BIGINT`：被动作对象的 revision（Run/Invocation/Approval/Connection）。
- `risk_class VARCHAR(16)`：`R0|R1|R2`，`CHECK` 与 `aio_tool_versions.risk` 同词表。
- `metadata_schema VARCHAR(64) NOT NULL DEFAULT 'legacy'`：标明该行 `metadata` 由哪个封闭模型产出；`legacy` 仅供既有行，新写入禁止使用。

约束与索引：

- `CHECK (pg_column_size(metadata) <= 4096)`：元数据硬上限。选 `pg_column_size` 而非 `length(metadata::text)`，因为前者反映实际存储，不会被空白字符绕开。上限之外仍在应用层用 `bounded_json` 预检，给出 `AUDIT_METADATA_TOO_LARGE` 而不是让 DB 抛裸错。
- `CHECK (metadata_schema <> 'legacy' OR created_at < :migration_ts)`：结构性禁止新代码继续写自由 metadata。
- 组织外键保持 `org_column()` 的单列 FK。**不为 `run_id`/`resource_id` 添加复合组织外键**：审计事实必须能在其主体被删除后继续存在，加 FK 会让「删除 Run」被审计行阻塞，或诱使后续用 `ON DELETE CASCADE` 抹掉审计。这是对house invariant「复合组织外键」的一处有意例外，理由是同一份 invariant 里的「append-only where facts must not be rewritten」优先级更高；改为在应用层与测试中断言 `org_id` 一致性。此例外必须写进契约文档，不能只留在代码注释里。
- 新增 `INDEX (org_id, created_at DESC, id)` 支撑现有 `audit_events` 的排序分页；现状无此索引，`ORDER BY created_at DESC, id` 在真实数据量下会退化为全表排序。

### 2.2 `aio_outbox` 扩列（投递簿记）

- `next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`：退避调度点。
- `last_error_code VARCHAR(64)`：只存稳定错误码，不存供应商响应体。
- `lease_owner VARCHAR(128)`、`leased_until TIMESTAMPTZ`：relay 单飞租约，语义与既有 Job lease 一致，不引入新并发模型。
- `CHECK (attempts >= 0)`、`CHECK (last_error_code IS NULL OR delivered_at IS NULL)`。
- 部分索引 `INDEX (org_id, next_attempt_at) WHERE delivered_at IS NULL`：backlog 扫描不扫已投递行。

### 2.3 runtime 角色最小权限（沿用共享预算的先 REVOKE 再按列 GRANT 范式）

`aio_audit_events` 已在 `provisioning.py` 的 `append_only` 集合（SELECT, INSERT），本增量不放宽。

`aio_outbox` 当前落入默认分支，拿到 `SELECT, INSERT, UPDATE, DELETE`——事实行可被改写或删除。改为：

```
REVOKE UPDATE, DELETE ON aio_outbox FROM <runtime>
GRANT UPDATE (delivered_at, attempts, next_attempt_at, last_error_code, lease_owner, leased_until) ON aio_outbox TO <runtime>
```

`aggregate_id`/`kind`/`payload`/`org_id`/`id` 对 runtime 不可改，DELETE 收回（保留清理由独立运维身份在保留策略窗口执行，属 OPS-03，不在本增量）。

### 2.4 迁移执行方式

纯 DDL 加列加索引，无数据回填，无需维护窗口，无需 RLS 豁免身份（区别于 v13：v13 要回填跨组织投影，故需 BYPASSRLS 身份并有守卫）。`downgrade` 允许，因为只丢弃本增量新增的可空列与投递簿记，不丢审计事实本身；但必须显式拒绝在 `metadata_schema <> 'legacy'` 存在行时降级，否则新写入的结构化元数据语义会失去标记。

## 3. 锁与原子性

`docs/engineering/platform-stdio-lock-order.md` 已固定的前缀，本增量不新增、不改序：

```text
organization FOR SHARE
  -> immutable Run resource refs (Run/Project/Session/Agent), UUID order FOR UPDATE
  -> Run FOR UPDATE (or discovery target lock)
  -> exact stdio lease FOR UPDATE
  -> lifecycle mutation + Run revision/event/outbox
```

v13 追加的资金前缀：组织 pool → 部门 pool UUID → 个人 budget → Run/receipt/allocation。

本增量的规则：

1. **审计行是纯 INSERT，不取任何锁，不改变现有锁序。** 它落在上述前缀的最后一段「lifecycle mutation + Run revision/event/outbox」内，与 `_event`/outbox 插入同位置。写审计不得触发新的行锁或外键锁——这也是 2.1 不加 `run_id` 复合 FK 的第二个理由：外键会带来 `aio_runs` 上的 `FOR KEY SHARE`，而锁序契约第 8 节已记录过「外键锁不能只从 UPDATE 的表名判断」导致的反向依赖事故。
2. **投递 relay 的事务不持有任何业务锁。** 它只做 `SELECT ... WHERE delivered_at IS NULL AND next_attempt_at <= now ORDER BY id FOR UPDATE SKIP LOCKED LIMIT n`，然后更新投递簿记列。事务内不锁 organization、不锁 Run、不锁 pool，因此与两条既有前缀无交集，不可能构成锁环。
3. **网络投递发生在事务之外。** 取租约（短事务）→ 提交 → 投递 → 另一短事务记结果。锁内不调用归档/日志系统，与既有「锁内不调用模型/embedding/Docker」同一条纪律。
4. **`audit.read` 自审计行与被审计的查询同事务。** 若自审计写入失败，查询结果不得返回（读也遵守 fail-closed，否则「访问审计自身留痕」可被一次失败绕过）。该事务不取业务锁。
5. **不使用 advisory lock。** 与全仓现状一致。

## 4. Fail-closed 规则与必须改造的调用点

**定义**：高风险动作 = `risk_class == "R2"` 的工具调用，或任何目标 slot 前缀为 `connector/` 的 dispatch（外部效果面），或审批决定本身。

**规则**：高风险动作的意图审计行必须与该动作的状态推进在同一个 PG 事务内提交。审计插入失败 ⇒ 事务回滚 ⇒ 不存在可消费的 dispatch/permit ⇒ `effect_count == 0`。归档投递失败 ⇒ 动作继续 ⇒ backlog 增长并告警。两者错误码必须不同：`AUDIT_SINK_UNAVAILABLE`（拒绝，5xx，不可重试为新动作）与 `AUDIT_ARCHIVE_BACKLOG`（仅告警，不进业务响应）。

必须逐点改造/断言的调用点：

| 调用点 | 位置 | 现状 | 本增量要求 |
|---|---|---|---|
| `prepare_dispatch` | `runtime/execution.py:915-926` | 已在同事务写 `tool.dispatch_prepared` | 保持，补结构化元数据与负例断言 |
| `consume_dispatch` | `runtime/execution.py:1003+` | **无审计行** | 新增同事务意图审计；无审计行不得返回 `DispatchPermit` |
| `complete_dispatch` | `runtime/execution.py:1128` | 已写 `tool.result` | 保持，补 `risk_class`/`decision` |
| `plan_tool` / `authorize` | `runtime/execution.py:863`、`service.py:941` | 已写 `tool.planned` | 补 `decision`/`reason_code`/`policy_revision` |
| `decide` 审批 | `runtime/service.py:1030` | 已写 `approval.decide` | 补双人事实与 `subject_revision` |
| Run 核对/未知效果 | `runtime/execution.py:1885`、`service.py:811` | 已写 | 补 `reason_code`，纳入高风险集合 |
| MCP 凭据 prepare/activate | `connections/service.py:342,424` | 已写，metadata 含 `binding_id`/`revision` | 迁到封闭模型，禁自由 dict |
| `audit_events` 查询 | `admin/service.py:1181` | **无自审计** | 同事务写 `audit.read`，失败则不返回结果 |

**结构性保证而非约定**：`_audit` 与 `AdminService.audit` 合并为 `observability/audit.py` 的单一 `record()`，签名要求 `metadata: AuditMetadata`（封闭联合类型），不再接受 `dict`。高风险路径另加 `require_recorded(c, action, subject_id)` 守卫：在返回 permit 前于同一连接内 `SELECT 1` 校验该事实行存在，缺失即抛 `AUDIT_SINK_UNAVAILABLE`。这样「忘记写审计」会变成运行时失败而不是静默放行。

## 5. 脱敏：绝不允许进入审计记录的内容

**禁止清单**（结构上不可达，不是靠过滤）：模型 prompt 与回答正文、工具调用参数与结果正文、文件/文档/附件内容与片段、凭据与 token（含前缀片段）、Cookie/Authorization header、URL query 串、环境变量值、异常链中的上游响应体、截图与二进制。

**允许清单**：UUID、组织/部门 scope、action 与 outcome 词表、`decision`/`reason_code`、各类 revision、`risk_class`、RFC 8785 摘要十六进制串、字节数与条目计数、受限十进制金额字符串、时间戳。

**四层结构性执行**：

1. **封闭类型**：每个 action 一个 `extra="forbid"` 的 pydantic 模型，字段类型即上述允许清单，无 `str` 自由字段（短枚举用 `Literal`）。没有承载正文的容器，正文无法入库。
2. **schema 级敏感标记**：工具 `input_schema` 的属性支持 `x-aio-sensitive: true`，MCP 连接配置与环境变量绑定同标记；标记由 `catalog.py` 的 `validate_schema` 在发布时校验并冻结进 `definition_digest`，事后不可悄悄摘除。
3. **统一出口过滤器**：`observability/redaction.py` 提供唯一的 `scrub(value, *, sensitive_paths)`，统一供审计、SSE error 帧、`PlatformError.message`、诊断包与 relay payload 使用，取代 `_SECRET_PATTERN` 与 gateway 的 `value.replace(secret, ...)` 两处各自实现。覆盖 header/query/body/env/异常链五个出口。
4. **纵深断言**：写入前对序列化后的 metadata 断言不含任何当前活跃凭据物料与已知 marker；命中即拒绝写入并告警（而不是替换后放行），因为命中说明第 1 层有缺口。

DB 侧兜底：2.1 的 `pg_column_size(metadata) <= 4096` 使大段正文即使绕过应用层也无法落库。

## 6. 执行与证据清单

> 2026-10-25 进度：Slice A 已落地并有真实 PG 证据（`tests/platform/test_audit_integration.py`、`test_audit_contracts.py`），已合入 master（kongbaifan/aio#1）。Slice B 的 relay 已落地（`app/observability/archive.py`、v15、`tests/platform/test_audit_relay.py`），只验收 fake sink，未接真实适配器/进程。Slice C 未开始。逐项状态与偏差写在各条下方的「实际」行，未勾选项不代表部分完成可以当作完成。

- [x] v14 迁移、审计扩列、outbox 投递簿记与 runtime 最小权限。
  **实际**：真 PG 从 `0013_shared_budgets` 升级、legacy 行逐字段不变、新自由 metadata 被拒、仅 legacy 时可降级、存在结构化行时降级拒绝；runtime 对审计 UPDATE/DELETE 及 outbox `payload`/`kind`/`aggregate_id` UPDATE、DELETE 均为 `42501`，六个簿记列可改；启动校验对多授的审计列 UPDATE 报错（负控）。4 KiB 上限实测按未压缩值计算，可压缩大字段同样被拒。实施中发现并修复：CHECK 字符串中的 `':v1'` 被 SQLAlchemy 当作绑定参数渲染为 `'NULL'`，导致全部结构化写入失败；已加不依赖 PG 的 DDL 渲染回归用例。
  **证明**：`0014_audit_records.py` 只加可空列/索引/CHECK，`v1`–`v13` 快照字节未变；真 PG 从 `0013_shared_budgets` 升级后 `alembic_version` 为 `0014_audit_records` 且既有审计行 `metadata_schema='legacy'`、原值逐字段未变；`NOBYPASSRLS` runtime 身份对 `aio_audit_events` 的 UPDATE/DELETE 被 DB 拒绝，对 `aio_outbox` 的 `payload`/`kind`/`aggregate_id` UPDATE 与 DELETE 被拒、仅六个簿记列可改；`pg_column_size` 上限用一条 4KB+ metadata 实测被 DB 拒绝；存在 `metadata_schema<>'legacy'` 行时 downgrade 抛错。
- [x] 统一 `observability/audit.py` 的 `record()`，全部 52 个调用点迁移，自由 dict 入口消失。
  **实际**：`insert(s.audit)` 仅存在于 `observability/audit.py`；`AdminService.audit` 与 `PlatformService._audit` 已删除；12 个文件共 55 处 `record()`（原 52 处 + `tool.dispatch_consumed`、`audit.read`、`run.reconcile`），54 个 action 契约。约束由运行时 `type(metadata) is contract.metadata` + pydantic 重新校验保证（本仓库未启用 mypy）。
  **证明**：全仓 grep `insert(s.audit)` 仅出现在 `observability/audit.py`（现状散落 `admin/service.py`、`runtime/service.py`、`workspaces/service.py:244` 三处）；`record()` 的 `metadata` 形参类型为封闭联合，传入 `dict` 被 mypy/pydantic 拒绝；一条用例对每个 action 断言其模型的允许键集合（多一个键即失败，取 v13 `POOL_VIEW_KEYS` 正向断言范式）。
- [x] 高风险 fail-closed：PG 审计不可写即无外部效果，且 `consume_dispatch` 补齐意图审计。
  **实际**：用按租户+action 限定的 BEFORE INSERT 触发器注入真实 DB 失败：`prepare_dispatch` 无 dispatch 行；`consume_dispatch` 回滚为可再消费的 `prepared`、无 `tool.started` 事件；Worker 路径 run `failed`、dispatch `not_sent`、`EffectSink.requests == []`；错误为 503 `AUDIT_SINK_UNAVAILABLE` 且无异常链、无触发器消息。`require_recorded` 负控：跳过写入或写到另一 event_id 均被拒。另补齐计划表中的 Run 核对：新增 `run.reconcile`（只存 `evidence_digest`），审计失败时 blocker 保持未解除。
  **证明**：真 PG 用例注入审计插入失败（对 `aio_audit_events` 的 INSERT 权限剥离或触发器抛错）后尝试 `prepare_dispatch` 与 `consume_dispatch`，断言事务回滚、`aio_dispatches` 无新行、`EffectSink.effect_count == 0`、错误码为 `AUDIT_SINK_UNAVAILABLE`；删除 `consume_dispatch` 的新增审计调用会使 `require_recorded` 守卫用例失败（守卫本身有负控）。对应 ECASE-34 前半。
- [x] 归档投递可重试、有界退避、单飞租约、重复投递不产生重复事实。
  **实际**：真 PG：sink 依次失败/超时/抛含 marker 的异常/成功，`attempts` 1→4、`next_attempt_at` 按 5/10/20s 推进、未到期不重领、`last_error_code` 只含固定码且无 marker；两 relay 一方持锁未提交时另一方领到不相交的行，并发排空无重复投递；租约过期后接管，旧 relay 在新 relay 持租约期间与完成后 `finish` 均不改任何列，重发携带同一幂等键；claim 事务内 `pg_locks` 只有 outbox/审计表，无 `aio_runs`/`aio_organizations`/`aio_budget_pools`/`aio_budgets`/`aio_jobs`/`aio_resources`；发送时连接池占用为 0；claim 语句 `EXPLAIN` 命中 `ix_aio_outbox_audit_pending` 且无 Sort。变异测试 9 项杀死 8 项；存活的「claim 去掉 org 谓词」被 FORCE RLS 兜住，结果不变（该谓词保留用于索引前缀）。**偏差**：计划写的「sink 侧以 `(org_id, id)` 去重」由契约要求 + fake sink 实现，不是平台能保证的；PG 侧 `delivered_at` 只设置一次由栅栏保证。新增 v15 迁移（计划原写「无需新迁移」）：v14 的待投递索引不区分 kind，relay 会扫过永远待投递的 `run.event.available` 行。
  **证明**：fake 归档 sink 依次返回失败/超时/成功，断言 `attempts` 单调递增、`next_attempt_at` 按退避推进、`last_error_code` 只含稳定码；两个 relay 实例并发下 `FOR UPDATE SKIP LOCKED` 使每行只被一方投递；sink 收到重复投递时以 `(org_id, id)` 幂等键去重，PG 侧 `delivered_at` 只被设置一次；relay 事务内 `pg_locks` 快照证明未持有 `aio_runs`/`aio_organizations`/`aio_budget_pools` 上的锁。
- [x] 两类故障不混淆：归档中断不阻断只读请求与已获权动作。
  **实际**：sink 全程 `ARCHIVE_UNAVAILABLE` 时，Worker 完成含已获权 dispatch 的 Run（外部 sink 恰好一次）、Run 详情与会话列表正常，业务响应中无 `AUDIT_ARCHIVE*`；`backlog()` 为 `AUDIT_ARCHIVE_BACKLOG`，待投递数等于 PG 事实数，错误计数只有 `ARCHIVE_UNAVAILABLE`；恢复后全部事实补投、无内容泄漏；PG 审计写失败时为 `AUDIT_SINK_UNAVAILABLE` 且不产生指针；`serve()` 的告警日志含码与计数、不含 sink 异常文本。**未做**：「只读 API 包括事件回放/知识检索」只覆盖了 Run 详情与会话列表；backlog 未导出为指标，没有管理 API；`run_worker.py` 未启动 relay（无真实适配器可接）。
  **证明**：sink 全程不可用时，只读 API（Run 列表/事件回放/知识检索）与已获权高风险 dispatch 仍成功，`AUDIT_ARCHIVE_BACKLOG` 只出现在指标/告警而不进业务响应；同一用例断言 PG 审计行仍然写入且 backlog 计数增长。对应 ECASE-34 后半「不混淆两种故障」。
- [ ] 脱敏边界：五个出口、schema 级标记、正文不可达。
  **实际（仅审计出口）**：审计 metadata 封闭类型 + 真实 approved Run 的事实不含 prompt/回答/参数值；`x-aio-sensitive`、统一 `scrub()`、SSE/错误/relay 出口与替换 `_SECRET_PATTERN`、网关 `replace` 均未做（Slice C）。
  **证明**：合成 secret marker 分别嵌入 header、query、body、env、嵌套异常链与工具结果，触发失败/SSE error/审计查询/relay 投递四条出口，断言各出口均无 marker；对标注 `x-aio-sensitive` 的工具参数，审计行不含该字段任何形态（含摘要外的原值）；摘除标记会改变 `definition_digest` 并使发布校验失败；纵深断言层在人为构造的绕过用例中拒绝写入而非替换后放行。对应 ECASE-33。
- [x] 审计访问受限且自身留痕，普通运维默认无正文。
  **实际**：服务层与 HTTP 层 `operator`/成员 403 `ADMIN_FORBIDDEN`，auditor 200 且无 `metadata` 列；每次读取一条 `audit.read`（含 scope/limit/行数/时间窗/游标与 HTTP trace），自审计写失败时查询失败且不新增行。偏差：审计端点是 GET，CSRF 只约束变更请求，「缺 CSRF 的 403」不适用；当前没有导出端点。
  **证明**：`operator` 角色对审计查询/导出返回 403（持有效 CSRF 亦然，且区分越权与缺 CSRF 两种 403）；`org_admin`/`auditor` 每次查询留一条 `audit.read` 行含 scope/行数/时间窗；人为让自审计插入失败时查询返回错误且不返回任何行；`audit.read` 行本身不含正文。
- [x] 跨组织隔离与列表分页。
  **实际**：他组织 auditor 结果与本组织事实零交集；越权 403 响应不含他人 user id；`record()` 拒绝为非当前事务租户写入；7 条/页游标遍历固定 `until` 窗口无重复无遗漏；`EXPLAIN` 命中 `ix_aio_audit_org_created_id` 且无 Sort 节点（`enable_seqscan=off` 下断言，小表默认会选顺序扫描）；半个游标和无时区时间 422。
  **证明**：他组织身份读到零行（FORCE RLS）之外，另有正向断言：错误只给受限 scope，不返回他人 `actor_id`/资源存在性/内部路径；新索引下 `ORDER BY created_at DESC, id` 分页在无重复无遗漏的前提下走 `Index Scan`（`EXPLAIN` 断言，避免退化排序被当作通过）。
- [x] 完整回归与文档同步，保留未验证项（Slice A 范围）。
  **实际**：远程 Linux 主机上 `test_sandbox.py` 注入全部镜像，平台 583/0/0/0，Manager 136、runtime-policy 15、document-parser 16 全绿；connector-gateway 在 CI 同版本 3.12 下 82 passed（3.13 下 1 项 TLS 严格校验失败，与本增量无关）。本机 ruff、local-harness、sandbox-lite、Web、`tsc -b`、compileall、pip check 通过；OpenAPI/`generated.ts` 已重新生成。契约 `docs/engineering/platform-audit-contract.md` 已记录复合外键例外。**未做**：`npm audit`、真实 HTTP 端到端脚本重跑、CI 远程运行。证据 `var/verification/audit-v14/`。
  **证明**：`scripts/platform/test_sandbox.py` 现场构建四个镜像并注入全部 `AIO_TEST_*` 后完整平台套件 0 failures/0 errors/0 skipped，套件时间戳晚于本增量最后一次源码改动；Manager/runtime-policy/connector-gateway/document-parser 四套同批次全绿；ruff、local-harness、sandbox-lite、pip check、compileall、前端与 `tsc -b`、npm audit 通过；OpenAPI 与 `generated.ts` 现场重新生成后逐字节一致；新增 `docs/engineering/platform-audit-contract.md` 记录 2.1 的复合外键例外及其理由；`docs/implementation/README.md` 更新至 v14 与实际用例数。

## 7. 规模估算

以 v13 共享预算增量为「一个中偏大 slice」的标尺（1 迁移 + 1 模块 + 约 64 用例 + 1 契约文档）。GOV-02 完整六个子任务约 **2.5–3 slices**，因为它额外要动 52 个既有调用点、引入一个新的后台投递循环（自带生命周期与租约）、并改造两处既有脱敏实现。建议按下列顺序切分，每片独立可验收：

- **Slice A（1 slice，建议先做）**：`0014_audit_records` + `observability/audit.py` + `redaction.py` 封闭类型 + `consume_dispatch` 补审计 + `require_recorded` 守卫 + 审计读取自留痕 + 跨组织断言。覆盖 GOV-02.01、.02、.05 及 .04/.06 的一部分。**这一片就是 MCP-06.03 实际需要的前置**；做完即可解除 `MCP-06.03 <- GOV-02.02` 与 `CAP-01.04 <- GOV-02.02`。约 40–50 条新用例。
- **Slice B（1 slice）**：outbox relay（租约、退避、backlog 指标、幂等投递）+ 两类故障分离 + 归档中断负例。覆盖 GOV-02.03 与 .06 剩余部分。约 20–25 条新用例。
- **Slice C（0.5–1 slice）**：`x-aio-sensitive` schema 标记贯通工具/MCP/env 五出口，替换 `_SECRET_PATTERN` 与 gateway `replace` 两处实现，导出权限与保留策略边界。覆盖 GOV-02.04 收尾。约 15–20 条新用例。

Slice A 之后 `UI-08.06 <- GOV-02.06` 仍未解除，需 B、C 完成；且 UI-08.06 另依赖 GOV-03.06 与 GOV-05.06，后者属 P4，不因本增量就绪。

## 8. 明确剩余（本增量不含）

- **不含真实归档/日志系统接入**。Slice B 的 relay 面向 fake sink 与契约一致的适配器验收；没有部署 SIEM/对象归档/长期保留后端，不声称已有企业级审计留存。
- **不含 GOV-05 的限时 support grant、诊断包与安全回放**，也不含 IAM-09 的支持授权边界。「运维查看正文」这条开放条件保持关闭。
- **不含 GOV-04 kill switch**（`policy/kill_switches.py` 仍不存在），不含 GOV-01 的 `policy/data.py` 数据分级与外发策略，不含 GOV-08 的 OpenTelemetry/metrics 关联。`trace_id` 只是预留列与透传，不等于已有分布式追踪。
- **不含 MCP-06 本身**。本增量解除 MCP-06.03 的审计前置，不实现可核对真实外部写；真实写 feature flag 保持关闭，逐工具准入属 P5。
- **不含审计保留策略、归档裁剪与孤立行清理**（属 OPS-03），故 2.3 收回 runtime 的 outbox DELETE 而不提供替代清理路径；保留窗口内表会持续增长，这是已知且被接受的状态。
- **不含旧模式 `app/audit.py` 的删除**。它仍是 legacy-local 与可选 `mcp_server.py` 的实现；本增量不改动旧模式行为，也不把旧模式的 JSONL 写入称为平台审计。若要删除需先移除 legacy 入口，属 CAP-07.02 范围。
- **不含浏览器视觉验收与业务旅程 UAT**，不含公司真实 IdP/模型/业务系统接入。
- G0–G6 生产 Gate 全部不因本增量声明通过；原 110 父任务 / 718 子任务的完成状态不因本增量整体推进。
