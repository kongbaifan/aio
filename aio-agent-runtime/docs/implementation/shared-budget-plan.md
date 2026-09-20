# 组织 / 部门共享预算：实施计划

> 2026-09-14。承接已验证的 v12 Skill 归档增量。对应 RUN-10.01/02/03/05/06、GOV-03.05/06 和 UI-08 的预算部分；不替代整个治理阶段或生产 Gate。

## 必须成立的业务语义

1. 个人预算仍是必要条件；组织、部门是附加硬上限，不是赠送额或另一个计费账本。一个 Run 的相同消费可以同时约束组织和多个部门，不能把这些重叠投影相加当成公司总账。
2. 未配置共享硬上限仍保留完整投影，管理员以后启用限额时包含已经承诺的费用。配置不是删除/重置消费，不允许下调到已消费加预留以下；支持显式撤销附加限额但保留事实和审计。
3. 所有新 Run 和独立 embedding 意图在原事务内绑定组织及提交时全部有效部门。成员调动不转移旧任务的消费/占额；新任务使用新部门。无部门成员仍受组织和个人约束。
4. Run 内主模型、planner、步骤、summary、查询 embedding 共用同一预留；独立 KB 摄取/查询 embedding 单独预留，不得遗漏成为免费旁路。
5. 完成/取消/失败/未发送退款和 unknown hold/迟到费用核对同步更新全部绑定。未知费用不当零；重复/旧代次回执不能重复收费。真实账单超过保守估计可以如实落账，后续付费动作拒绝而非篡改账单。
6. 管理员可读本组织的汇总和配置，普通用户不能读取其他成员/部门的财务明细；错误只给出受限 scope，不返回他人 prompt、调用参数或凭据。

## 数据与迁移

- v13 新增 `budget_pools` / `budget_allocations`，保留已有个人预算、Run reservation、model/embedding append-only 账本，不复制用量事实。
- Pool 是固定 scope 的投影：组织或部门、USD、累计已消费/预留、可空硬上限、revision、起算时间和迁移期初消费。Allocation 是不可变主体绑定 + 数值投影，主体只能是一个 Run 或一个独立 embedding 意图。
- FORCE RLS、复合组织外键、scope 唯一、互斥主体、非负约束；金额最多六位小数。旧快照不变；新迁移不提供丢账 downgrade。
- 升级在暂停旧版本写入的维护窗口执行：组织期初消费取既有个人预算总数；未结算 hold 按真实 reservation/独立 embedding 绑定。部门只承接升级时尚未结算的承诺（明确 `migration_hold`），不把当前成员关系伪造成历史费用归属。无法匹配的已有预留必须拒绝迁移并要求核对，不静默释放。

## 锁与原子性

- 原组织/资源/Session 前缀保持；L3 按组织 pool → department pool UUID → 个人 budget → Run/receipt/allocations。
- 只在短 PG 事务内改账；锁内不得调用模型/embedding/Docker。组织管理变更仍先取组织排他锁，不从共享锁中途升级。
- 每一条金额变化都取得同一 pool 前缀；不得在多用户间只锁各自个人 budget 而分别读相同剩余额度。
- 独立 embedding 未发送/回执路径也使用前缀，撤权后允许原始计费事实结算，不授予已撤销内容读取权。

## 执行与证据清单

- [x] v13 schema / 迁移 / 期初预留一致性 / runtime 权限。
  依据：`schema_v13.py` 两表六位小数、复合组织外键、scope 唯一（组织级偏索引）、互斥主体与非负约束；`0013_shared_budgets.py` 回填前先调用 `app/db/migration_guard.py::require_unblinded_tenant_read` 拒绝被行级安全过滤的身份（角色属性检查 + bootstrap 见证表检查），回填后再由同文件 `_reconcile` 逐项核对已写投影，期初消费取个人已消费合计、未结算 hold 按真实 reservation/独立 embedding 绑定、不匹配即拒绝迁移，downgrade 直接抛错；`provisioning.py` runtime 角色 `NOBYPASSRLS`，两表先 REVOKE UPDATE/DELETE 再按列授权，主体绑定对 runtime 不可改。
- [x] 统一 pool 分配、锁、准入与数值投影；无额外计费事件副本。
  依据：`budgets.py` 全程行锁，`_ordered()` 固定组织 pool 优先再按部门 UUID，`ensure/lock_subject/change` 同序；全仓无 advisory lock；allocation 只存 reserved/consumed 数值，回执仍在原 append-only 账本。真 PG 通过 `test_two_users_cannot_reserve_the_same_last_shared_amount[organization|department]`、`test_distinct_departments_have_distinct_caps_and_overlap_is_not_summed`、`test_all_active_departments_apply_and_failed_admission_is_atomic`，`assert_projection` 每次校验 pool 投影等于绑定合计且组织额等于个人额。
- [x] Run 准入、取消、完成、恢复/未知费用与核对接通。
  依据：`runtime/service.py` 准入 `for_actor`→`check`→`reserve`，取消 `lock_subject`→`change(release)`；`runtime/execution.py` 结算 `change(release, add=hold, charge)`、恢复与迟到回执各自 `lock_subject`/`change`。真 PG 通过 `test_idempotent_retry_then_cancel_releases_each_scope_once`、`test_normal_worker_settlement_is_not_double_charged`、`test_unknown_late_charge_is_projected_once_even_above_cap`、`test_delayed_overage_blocks_already_admitted_runs_before_next_paid_dispatch[prepare|dispatch]`、`test_revoked_department_still_settles_the_original_charge_fact`、`test_department_transfer_preserves_old_binding_and_uses_new_scope_for_new_work`；恢复路径另行实跑 `recover_due` 确认全部 scope 各释放一次、二次扫描不重复释放。
- [x] 摄取 / 独立查询 / Run 内 embedding 的全部金额路径接通。
  依据：`knowledge/embedding.py` 由 `embedding_subject()` 分流——Run 内并入该 Run 预留（`check(pools, 0)`），独立意图单独预留（`check(pools, maximum)`→`reserve`）；未发送、未知、迟到核对各自 `lock_subject`/`change`。真 PG 通过 `test_ingestion_and_standalone_embedding_are_capped_while_preview_stays_lexical`、`test_unknown_embedding_keeps_every_scope_hold_until_distinct_reconciliation`、`test_embedding_not_sent_refund_and_rearm_are_projected`、`test_embedding_receipt_and_uncertainty_race_preserves_one_charge`。
- [x] 管理 API：组织 / 部门上限、精度、当前角色、revision、审计、汇总。
  依据：三条 `/api/v2/admin/shared-budgets*` 路由；`SharedBudgetUpdate` 强类型 revision 与 `decimal_places=6`、显式 null 撤销；`set_shared_budget` 默认仅 `org_admin`，422 精度、409 `REVISION_CONFLICT`、409 `BUDGET_BELOW_COMMITTED`，审计与更新同一连接同一事务；汇总含 warning/exhausted/remaining/opening_consumed。真 PG 通过 `test_shared_budget_http_authority_csrf_precision_and_scope`、`test_enabling_caps_accounts_for_existing_holds_and_never_resets_them`，契约用例 27 项通过。每次生效的上限变更留一条持久审计行、被拒变更不留行，已由同文件用例断言 outcome / actor / metadata（含 department_id、hard_limit、currency、revision）。
- [x] Web：共享上限配置与警告、重叠 scope 解释、个人预算不回归；生成契约。
  依据：`SharedBudgets.tsx` 与个人预算面板同挂管理页 `budgets` 页签，个人预算路径未变；重叠 scope 提示明确「不能相加当作总账」；badge 四态映射 red/amber/green/neutral，`opening_consumed` 单独成注；`shared-budgets.test.tsx` 6 项通过，前端全套 126 项通过，`tsc -b` 干净；OpenAPI 90 路径含 3 条共享预算路径，重新生成的 `generated.ts` 与仓库内容逐字节一致。
- [x] 真 PostgreSQL：两用户最后组织额/同部门额并发、不同部门不互相扣部门额、多部门全部约束、调动保留旧绑定、同幂等键不重复预留、取消退款、unknown/超额/重复核对、embedding 旁路与恢复。
  依据：本轮在自建一次性 loopback PG 容器（`pgvector/pgvector@sha256:cf134a76…`）上实跑共享预算相关五个文件全绿（`test_shared_budgets` 21、`test_shared_budget_contracts` 27、`test_shared_budget_migration` 7、`test_budget_lock_order` 9、`test_team_shared_budget` 5，合计 69，按当前工作区 `--collect-only` 复核），另单跑 `test_knowledge_integration.py::test_hybrid_ingestion_and_worker_retrieval_use_real_pgvector_and_share_run_budget` 通过（Run 内查询 embedding 只占一份 Run allocation、`embedding_call_id is None`）。原先唯一的红点 `test_queue_expiry_recovery_releases_every_scope_exactly_once` 已修正前置常量为 manifest 的 `run_budget` 0.1：该常量在夹具 `test_shared_budgets.py:98` 的 `manifest={"run_budget": "0.100000"}`，用例断言准入持有整份已发布 Run 预算而非单次模型调用上界，并含二次 `recover_due` 不重复释放断言（不再引用行号 243，该行现为转部门用例的取消断言）。本项列举的并发/隔离/调动/幂等/退款/核对/旁路场景逐一对应具体用例，均经 `assert_projection` 校验投影恒等式。用例数量随本增量推进多次变化，故不引用中间采集值；总数以最终门控运行为准，见最后一项。
- [x] 迁移保留、RLS/跨组织、失权/普通成员 API、金额/revision/低于承诺拒绝、前端表单测试。
  已通过：迁移保留 `test_migration_preserves_original_holds_and_does_not_fabricate_past_department_spend[prepared|not_sent|unknown]` 与 `test_migration_refuses_unreconciled_balances_without_dropping_original_facts[unmatched_hold|unsupported_currency]`（拒绝后仍停在 `0012_skill_imports`、两表未建、原 reservation 金额不变）；`test_pool_rls_and_immutable_binding_permissions` 覆盖跨组织读零行、改 `run_id`/删 allocation/插他组织 pool 均被 DB 拒绝；金额/revision/低于承诺三类拒绝；前端表单 6 项。迁移守卫现已补齐用例并经本轮实跑：`test_migration_refuses_a_row_level_security_scoped_identity_instead_of_an_empty_projection` 用 `NOBYPASSRLS` 身份（另授满 DDL/DML 权以排除误判）证明 4 张源表读零行、升级被拒且错误含 row level security，配套负控 `test_migration_projects_nonzero_opening_consumption_with_an_exempt_identity` 证明豁免身份下期初 0.04 与 0.1 hold 真实落账。本轮补齐了原先三处空缺，故勾选：普通成员与操作员各自持有效 CSRF 的 PUT 均被拒（`test_shared_budget_http_authority_csrf_precision_and_scope`，并同时断言拒绝后 `hard_limit` 未被改动，区分越权与缺 CSRF 两种 403）；财务明细泄漏改为对 `AdminService._pool_view` 许可键集合的正向断言（`POOL_VIEW_KEYS`，多一个键即失败），取代原先不可能失败的子串烟测；审计行已有断言——四次被接受的改限各留一行 `budget.shared_limit`，被拒的三次不留行，并校验 outcome、actor、scope/limit/revision/currency 元数据（`test_enabling_caps_accounts_for_existing_holds_and_never_resets_them`）。
- [ ] 完整回归、实际 HTTP、文档/报告同步；保留尚未验证项，不能用局部通过替代全平台验收。
  依据与缺口（按证据分开陈述，不把不同时点的结论混成一次覆盖）：
  最新一次「全部镜像门 + 0 skipped」的完整平台套件为 **500 tests、0 failures、0 errors、0 skipped**，套件时间戳 2026-09-16T15:10:22+08:00，证据副本 `var/verification/postguard-gated.xml`（SHA-256 `5f53994e4f033ecb8b667e9ada3a686730f65432c501ce6d4e41ddf3c408a3ca`，与同一运行写出的 `platform-postgres.xml` 逐字节相同）。更早的 13:33:01（`shared-budget-final-gated.xml`）与 14:29:28（`ground-truth-gated.xml`）同为 500/0/0/0，可视为同结论的独立复现。该 15:10 运行确实包含迁移守卫用例（`test_migration_refuses_a_row_level_security_scoped_identity_instead_of_an_empty_projection` 及其豁免身份负控），即覆盖第一至第八项在 15:10 之前的代码状态。
  **但 15:10 之后生产代码与用例仍在改动，这些改动尚未被任何已完成的门控运行覆盖**：`app/db/migration_guard.py`（17:40，恢复了角色检查之外的 bootstrap 见证表 blinded 兜底）、`app/billing/budgets.py`（17:52）、`app/knowledge/embedding.py`（17:47）、`app/runtime/team.py`（17:56）、`migrations/versions/0013_shared_budgets.py`（15:17，`_reconcile` 落地）、`tests/platform/test_team_shared_budget.py`（18:00）。逐条对照：13:33 与 15:10 两次运行的时间戳都早于上述 mtime，故「13:33 的运行覆盖前八项全部修复」这一旧结论不成立，已作废。
  Team Run 覆盖为本轮新增且不在任何门控 XML 内：`test_team_shared_budget.py` 5 项（一个 Team Run 对每个绑定 pool 只持一份 allocation，覆盖 planner/步骤/synthesis 共用、逐步扣减、部门额中途耗尽、取消各 scope 只释放一次、Run 内查询 embedding 并入而独立摄取单独预留）；`app/runtime/team.py` 曾有一处遗留扰动在 `_start_step` 每步额外 `change(add=0.02)`，是这 5 项最初全红的原因，现已移除。已核实：在当前源码哈希（`team.py` `3525ca47`、`budgets.py` `d44239fa`、测试 `738bd099`）下，于一次性 loopback PG 容器实跑该文件 5/5 通过；连同其余四个共享预算文件为 26 项全绿。平台套件现为 505 collected（`--collect-only` 复核），与 15:10 的 500 项差额即这 5 项。
  因此本项**取消勾选**：覆盖全部 505 项、0 skipped 的门控重跑尚未完成，上述 15:10 之后的改动只有针对性实跑证据，没有全平台门控证据；在该重跑产出并留档之前，不声称完整回归已通过。
  其余非 Docker Gate 同轮全绿：ruff（CI 两种范围）、local-harness 142、sandbox-lite 24、pip check、compileall、前端 126 项 / `tsc -b` / 生产构建 / Prettier、npm audit 0 已知漏洞；`docs/api/platform-v2.openapi.json`（90 路径）与 `web/platform/src/api/generated.ts` 现场重新生成后均逐字节一致。
  实际 HTTP 已真跑并在两套独立干净栈复现：`var/verification/shared-budget-http-current.json`、`shared-budget-http-current-confirm.json` 均 `status=passed`，各 41 条断言、其中 25 条共享预算断言。首次真跑失败的缺陷在验证脚手架而非产品：`AdminService._pool_view` 返回 `str(Decimal)`，未创建的 pool 序列化为 `"0"`、已存储的为 `"0.000000"`，脚手架按原始 JSON 字符串比较，改为按 `Decimal` 数值比较后通过。
  文档同步（尚未追平本轮最后改动）：[共享预算契约](../engineering/platform-shared-budget-contract.md) 第 6 节记录迁移身份必须豁免 RLS 及守卫行为，第 7 节仍只列四个测试文件，**未收录 `test_team_shared_budget.py`**，需补；[实现进度](README.md) 已更新至 v13 / 61 表（按 `schema.py` metadata 复核为 61）/ 90 路径，但其中的 500/0/0/0 与「共享预算 64 项」对应 15:10 及更早的运行，未含新增 5 项 Team 用例，待门控重跑后一并更新。
  仍明确保留未验证项，勾选仅限本增量范围：浏览器视觉与业务旅程验收未做；公司真实 IdP / 模型供应方 / 业务系统与真实财务对账未接入（本轮身份为合成签名 OIDC 夹具、模型为本机 loopback 端点）；`implementation-progress.json` 的累计汇总由其他 agent 维护；G0–G6 生产 Gate 全部未声明通过。下节「明确剩余」列出的月度 / 跨币种周期、供应商对账、告警投递、财务导出、部门管理委派、完整用量分析、容量 / HA 均未实现。

## 明确剩余

本增量为累计 USD 投影，不声称已完成月度/跨币种周期、provider invoice 自动同步、所有工具价格、告警投递、财务导出、部门管理委派、完整用量分析、容量/HA 或生产 Gate。

上面九项中已勾选八项，最后一项（完整回归）已取消勾选：15:10 那次 500/0/0/0 门控运行不覆盖其后的 Team 用例与 `budgets.py` / `embedding.py` / `team.py` / `migration_guard.py` 改动，覆盖 505 项的门控重跑未完成。已勾选项只表示本增量自身的代码、真 PG 用例与真实 HTTP 复现已取得证据，不等于平台验收。`implementation-progress.json` 的累计同步不在本文件范围内。身份与模型仍为合成夹具，未做真实公司 IdP / 供应商发票 / 财务对账，浏览器视觉与 UAT 另行验收，原 110 父任务 / 718 子任务与 G0–G6 不因本增量整体标完成。
