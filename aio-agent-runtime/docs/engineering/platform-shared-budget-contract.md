# 组织 / 部门共享预算与计费归属契约

> 当前代码契约，不是财务认证或生产 Gate。实现：`app/billing/budgets.py`、`app/runtime/{service,execution}.py`、`app/knowledge/embedding.py`、`app/admin/` 和 `web/platform/src/features/SharedBudgets.tsx`。执行清单见 [实施计划](../implementation/shared-budget-plan.md)。

## 1. 业务含义与非目标

- 所有付费任务仍必须有个人预算。组织和部门 pool 是**附加上限与用量投影**，不是额外余额、另一份费用事件或新增充值通道。
- 同一笔费用可同时出现在组织、多个部门、个人和 Run 视角。**这些重叠数值不能相加**；公司组织 pool 是公司级投影。多部门成员的新任务受提交时全部有效部门约束，用户不能在请求里挑选一个有钱的部门绕过限制。
- `hard_limit=null` 表示没有启用该共享附加上限，仍持久记录预留和消费，仍受个人 / Run 上限。启用、提高、移除上限不会清空余额，不能通过反复配置抹掉已消费；新上限不得低于 `consumed+reserved`。
- 当前为累计 USD、最多六位小数，不是日/月周期自动重置。月度周期、跨币种、供应商发票自动同步、全工具价格、告警投递、部门委派与财务分析仍属原目标剩余项。

## 2. 原始事实与数据投影

v13 `0013_shared_budgets` 新增两表，当前共 61 表；v1～v12 快照不变。

| 表 | 关键字段 / 不变量 |
|---|---|
| `aio_budget_pools` | `org_id,id,department_id?,currency=USD,hard_limit?,reserved,consumed,opening_consumed,revision,created_at`；每 org 一个组织 pool、每部门一个 pool；非负；`consumed>=opening_consumed` |
| `aio_budget_allocations` | `org_id,id,pool_id,run_id?,embedding_call_id?,reserved,consumed,origin,created_at`；一个且仅一个计费主体；每主体 / pool 唯一；原始绑定不可修改 |

已有 `aio_budgets`、Run `aio_reservations`、`aio_usage_ledger`、`aio_embedding_calls/ledger` 继续是个人预算 / 用量事实。没有为组织 / 部门复制收费 ledger。Pool 是既有计费转移的同事务投影：

```text
pool.reserved = Σ allocation.reserved
pool.consumed = pool.opening_consumed + Σ allocation.consumed
organization_pool.{reserved,consumed} = Σ personal_budget.{reserved,consumed}
```

部门投影只合计实际绑定该部门的主体。绑定后成员调动、部门停用、权限撤销不会把旧 hold/账单挪给新的部门。新 Run 或独立 embedding 意图按当时有效成员关系创建新绑定。

两表 FORCE RLS；引用使用复合组织 FK。Runtime 没有两表 DELETE 权，也没有修改 scope、币种、期初数或主体绑定的 UPDATE 权。Pool 只可更新配置 revision / 上限 / 数值，allocation 只可更新数值。此机制不被描述为可抵御 runtime DB 身份失陷后的全部恶意 SQL。

## 3. 内部接口与锁序

```python
ensure(c, org_id, department_ids=()) -> list[RowMapping]
for_actor(c, principal) -> list[RowMapping]
lock_subject(c, org_id, *, run_id=None, embedding_call_id=None) -> list[RowMapping]
check(pools, additional=Decimal(0)) -> None
reserve(c, org_id, pools, amount, *, run_id=None, embedding_call_id=None) -> None
change(c, org_id, *, release=0, charge=0, add=0, run_id=None, embedding_call_id=None) -> None
```

- 调用方先建立原组织 / 资源 / Session 授权前缀；金额前缀统一为组织 pool → 部门 pool UUID → 个人 budget → Run / receipt / allocation。组织管理写仍先取组织排他锁，不能中途由共享锁升级。
- `for_actor` 只能从本次 DB 事务读取部门；组织共享锁与管理员先取组织排他锁的规则使绑定期间成员关系稳定。`lock_subject` 使用不可变绑定，不用当前部门重算旧任务。
- 没有 pool 的付费操作默认拒绝；无额外上限也必须保留投影。相同 org 的预算变更目前通过组织 pool 串行化，临界区只含短 SQL；不能据此宣称容量、跨节点或 HA 门禁通过。
- `change` 不创建费用事件，不自行判断业务成功或重试。调用方先完成原有租约 / 代次 / 状态 / 回执幂等校验。`release/add/charge` 在所有固定绑定与个人账目同一事务提交，失败全部回滚。
- 此路径没有模型请求、embedding HTTP、容器调用、文件解析或宿主安装。

## 4. 生命周期矩阵

| 路径 | 投影变化 |
|---|---|
| 新 Run | 从已发布 Agent 取 `run_budget`；个人与全部共享 scope 同事务校验 / 预留；Run、消息、Job、快照、幂等记录一并提交 |
| 幂等重试 | 返回原 Run；不再分配 pool、不重复预留 |
| queued 取消 / 队列到期 / 未发请求失败 | 按原 reservation 释放所有 scope；重复终态操作不再退款 |
| 成功 / 失败 / 停止后的结算 | 原整笔预留释放，实际模型 + Run embedding 消费加入各绑定；不确定调用改为保守 hold |
| Run 内模型 / planner / step / summary / embedding | 共用 Run 预留，不另外加一份独立 embedding allocation；新调用及发出前检查当前共享上限 |
| 独立摄取 / 内部独立 embedding 意图 | 固定 call ID 绑定 scope，按发布模型 `max_call_charge` 单独预留；API 浏览器预览仍明确是 lexical，不声称新增了付费语义预览 |
| 独立 embedding `prepared -> not_sent` | 同前缀释放预留；重试复用同 call / scope，重新做预算检查与预留，绝不改成其他部门 |
| unknown / missing usage | 保留额度，不当零消费；不通过重试制造重复免费请求 |
| 迟到用量 / 人工核对 | 不同有权责任人、固定证据与金额；原 unknown ledger 保留，追加原有调整事实；释放对应 hold 并投影真实金额一次 |
| 账单超出估计 | 如实记录，不为了让余额好看而裁掉金额；后续新付费操作拒绝。外部延迟 / 超估计收费仍可能使既有承诺总额超过硬上限 |
| 组织 / 用户已撤权 | 结构性停止、退款和原始用量事实核对不被新业务授权阻挡；不能因此重新发布或读取已撤销内容 |

## 5. HTTP / Web 管理契约

```text
GET /api/v2/admin/shared-budgets
PUT /api/v2/admin/shared-budgets/organization
PUT /api/v2/admin/shared-budgets/departments/{department_id}
body = { expected_revision: integer, hard_limit: decimal-string | null }
```

- 仅当前有效组织管理员，写入必须通过 BFF / Origin / CSRF。不存在或跨组织部门拒绝；普通成员、运维角色不能靠 URL 读取组织 / 部门财务汇总。
- 当前 revision 冲突返回 `409 REVISION_CONFLICT`；`hard_limit` 必须显式提供，空缺不是撤销。`0..1000000`、有限数、六位小数；非法金额 / 额外字段 `422`。
- `409 BUDGET_BELOW_COMMITTED` 拒绝抹去已消费 / 预留；`429 SHARED_BUDGET_EXCEEDED` 拒绝新增付费操作；不披露其他人的余额、提示词或调用参数。异常绑定 / hold 不匹配是 `409 BUDGET_INTEGRITY_ERROR`，不能自动补零。
- 管理响应金额为十进制字符串，包含 `remaining,warning,exhausted`；80% 警戒线是页面状态，不代表告警已经投递。未设置 pool 的 scope 返回零 / 空配置的只读视图，不在 GET 中创建记录。
- Web 延用管理台组件和样式；金额提交字符串，保留当前 revision。移除上限必须明确勾选确认，保留金额与审计。关闭 / 刷新是非提交按钮，冲突不自动覆盖更新。

## 6. 升级与恢复

1. 备份并验证可恢复；在隔离副本先运行迁移，暂停旧版本 API / Worker 的写入，不能混跑不维护投影的旧 Worker。
2. 用迁移身份执行 `manage_platform.py migrate`，升级至 `0013_shared_budgets`。组织期初消费取已有个人消费总额，既有有效 Run / 独立 embedding hold 全部绑定并保留。**该迁移身份必须豁免行级安全**：`rolsuper` 或 `rolbypassrls`。`0013` 是本项目唯一回填数据的迁移，它先对两张新表施加 FORCE ROW LEVEL SECURITY 再读取既有行，而 `migrations/env.py` 从不设置 `aio.org_id` GUC；租户级身份因此从 `aio_organizations`、`aio_budgets`、`aio_reservations`、`aio_department_memberships` 一律读到零行，即使另授满 DDL / DML 权限也一样。回填前调用可复用的 `app/db/migration_guard.py::require_unblinded_tenant_read`：先按 `bool_or(rolsuper OR rolbypassrls)` 校验 `CURRENT_USER`，再做一层纵深检查——若能看到 `aio_users`（bootstrap 表，自 0001 起不受 RLS 约束）却看到零个 `aio_organizations`，说明读取正在被租户策略过滤，同样拒绝；两者皆空的全新库（bootstrap 之前迁移）允许通过。不满足即抛 `RuntimeError` 拒绝迁移：事务回滚，版本停在 `0012_skill_imports`，两张新表不创建，原个人消费与 reservation 金额不变。回填后再由 `_reconcile()` 证明「确实读到了」而非「本可读到」：组织 pool 与组织集合逐一对应、`COUNT(*)` 独立复核 pool 数等于组织数、期初消费合计等于个人已消费合计且等于回填过程中累计的观测值、每笔未结算 hold 都在组织 pool 上按原金额挂到 allocation。任一不符即拒绝提交。没有这些守卫时的行为是**静默提交空投影**——期初消费记为零，未结算 hold 失去全部共享 scope，而迁移仍报告成功。
3. 部门仅承接升级时未结算承诺（`origin=migration_hold`）；不把当时成员关系假装成已完成历史任务的原始归属。旧 `not_sent` embedding 保留零 allocation，恢复后重新预留，不能成为无 scope 请求。
4. 无法从 reservation / 独立 embedding 对齐的个人预留，以及非 USD 既有预算，**拒绝迁移并回滚本迁移**；先人工查明并核对原始事实，不自动归零 / 换汇。
5. 执行 `refresh-runtime-grants --runtime-role <role>`，使新表 RLS / 更新列 / 禁 DELETE 生效。API / Worker schema 就绪检查拒绝版本不匹配。
6. 只启动兼容新 schema / 投影协议的服务。回退业务开关可撤销共享附加上限但保留个人上限和账目；无丢账 downgrade，不回退到继续写旧版个人账而不维护 pool 的代码。

## 7. 验证和局限

- `test_shared_budgets.py`：不同 Agent / Project 的两用户真实 PG 最后一份组织或部门额度并发；全部部门约束；部门不混扣；幂等 / 退款 / 转部门 / 在途启用限额 / unknown / 超额迟到账单 / 发出前复核 / embedding 未发送与回执竞争；RLS / 不可变绑定 / 实际 HTTP 权限。
- `test_budget_lock_order.py`：真实 PG 只持有部门 pool 一行，再用 `NOWAIT` 探针观测被阻塞调用方「已经持有组织 pool、尚未碰个人预算」；配套两条就地负控（部门先于组织、完全不锁 pool）各留下规范顺序不可能产生的签名，另含跨部门/多部门并发、规范序不死锁而反序死锁（40P01）、准入与结算重叠。
- `test_shared_budget_migration.py`：真实 v12 -> v13，queued Run 加 prepared / not_sent / unknown embedding 的迁移、原 ID / 原 hold 保留与新代码结算；不匹配预留 / 非 USD 拒绝并保持原数据库版本与事实；租户级身份触发第 6 节第 2 步的行级安全守卫而非提交空投影，并以豁免身份的非零期初投影作负控。
- `test_shared_budget_contracts.py`：非有限 / 精度 / 上下界 / 空值 / revision / 禁额外字段 / 不可变旧快照。
- 原 `test_knowledge_integration.py` 补充真实 Run 内 hybrid embedding 与组织投影，只占一份 Run allocation；`shared-budgets.test.tsx` 验证真实组件表单和关闭不提交。
- `verify_budget_http.py` 只提供 `verify_shared_budgets(admin, employee, other_employee, check)`，没有 `main()` / argparse，不能单独运行；它由 `verify_workbench_http.py` 在末段导入执行，凭据、部门与 Agent 夹具均来自该宿主脚本。在有期限、本机合成 SSO / 模型栈里验证真实 HTTP 准入、Worker 结算、两个部门隔离、重试不再收费和移除限额不清账。金额断言按 `Decimal` 数值比较而非原始 JSON 字符串：`_pool_view` 返回 `str(Decimal)`，未创建的 pool 是 `"0"`、已存储的是 `"0.000000"`。
- 该 HTTP 验证已真实执行并在两套独立干净栈复现：`var/verification/shared-budget-http-current.json`、`shared-budget-http-current-confirm.json` 均 `status=passed`，各 41 条断言、其中 25 条属共享预算。真实参与的组件是 HTTP、PostgreSQL、授权、Worker 与 Docker；身份是合成签名 OIDC 夹具，模型是本机 loopback 端点。两份证据自记 `synthetic_identity_provider`、`synthetic_model` 为真，`real_financial_reconciliation_verified`、`browser_visual_verified` 为假。不冒充公司真实 IdP、真实模型供应方或真实财务对账。
- 原始 110 父任务 / 718 子任务 / 40 需求 / 119 验收场景保留。完整范围、浏览器视觉 / 原生文件交互、真实公司提供方、UAT、容量和生产 Gate 另行验收。
