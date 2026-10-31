# 应急禁止开关契约（GOV-04）

> 当前代码契约，不是事故响应流程或生产 Gate。实现：`app/policy/kill_switches.py`、`app/policy/{service,repository}.py`、`app/admin/{service,routes,contracts}.py`、`app/runtime/{service,catalog}.py`、`app/db/schema_v16.py`、`migrations/versions/0016_kill_switches.py`。计划与证据见 [实施计划](../implementation/kill-switch-plan.md)。

## 1. 语义

- **scope（组织内）**：`organization`、`user`（该成员发起的工作）、`tool` / `model` / `agent`（单个资源）、`execution_class`（`python` / `mcp` / `knowledge` / `skill` 驱动类）。没有平台级「全局」scope：仓库里没有可授权的平台超级管理员角色。
- **被拦截的只有开始或推进工作的动作**：`session.run`、`agent.use`、`tool.use`、`model.use`、`embedding_model.use`、`knowledge.search`、`connection.use`、`mcp_server.use`、`skill.use`、`approval.decide`。读取、取消、核对、管理和开关本身永远可用。
- **只由人设置**：仅 `org_admin` 可启用/解除；原因码为封闭词表；附带说明只存 RFC 8785 摘要，不入审计、不在列表返回。模型、Worker、工具结果没有任何写入口。管理员不能对自己启用 `user` 开关（否则无人能解除给自己）。

## 2. 生效方式（无缓存）

- 启用与 `policy_revision` 自增在同一事务，并在组织行 `FOR UPDATE` 下完成；所有授权读取都在 `FOR SHARE` 下读 `current_facts`，因此启用提交后不存在仍按旧事实准入的事务。
- `current_facts` 每次读取未解除且未到期（以数据库时钟判断）的开关。`authorize()` 在**确认访问权之后**才检查开关，返回 `KILL_SWITCH_ACTIVE`（403）；无权访问者仍得到 `RESOURCE_NOT_FOUND`，开关不泄漏资源是否存在。
- `execution_class` 需要驱动信息，在 `current_tool()`（工具 plan/prepare/consume 都会经过）校验。
- **准入**：`create_run` 用固定 manifest 检查 agent/model/tools/驱动类，命中即拒绝，不先付一次模型调用。
- 两个独立 `Database` 实例之间不共享任何内存状态；只靠 PG 权威状态（用例覆盖）。仓库不使用 Redis。

## 3. 在途任务

启用提交后，`sweep_kill_switch` 逐个 Run（各自独立事务，走 `_system_locked` → `_stop_locked`，原因码 `KILL_SWITCH_ACTIVE`）处理本组织未终结、且其 manifest 命中 scope 的 Run：

| Run 状态 | 结果 |
|---|---|
| queued / 尚未派发 | `cancelled`，预留退回，无模型调用 |
| waiting_approval | `cancelled`，待审批项关闭，之后不能被批准 |
| 已 consume dispatch（外部效果不明） | `recovery_required`，dispatch 为 `unknown`，保留 blocker 待人工核对；旧 Worker 之后的完成回报被拒 |

sweep 失败不会撤销开关；被漏掉的 Run 下一步仍会被开关拒绝。

## 4. 解除与到期

- 解除需要**不同于启用者**的 `org_admin` 和证据（只存摘要），`expected_revision` 防并发；数据库 CHECK 也禁止 `released_by = activated_by`，表 owner 同样受约束。
- 到期由启用者显式设置；到期与解除都只让开关不再拦截**新**动作，绝不重新启动被它停止的 Run。
- 启用与解除各写一条同事务审计事实（`kill_switch.activate` / `kill_switch.release`，`resource_kind = 'kill_switch'`）。

## 5. 数据与权限

`aio_kill_switches`（v16，FORCE RLS，组织外键）。runtime 无 DELETE，只能 UPDATE `released_by, released_at, release_evidence_digest, revision`；启动校验拒绝多余授权。CHECK：scope/原因码封闭集合、按 scope 恰好有一个目标、解除三列同有同无、双人规则、到期晚于启用。降级在存在未解除开关或开关审计事实时拒绝。

## 6. API

- `GET /api/v2/admin/kill-switches`：`org_admin` / `operator` / `auditor`，不含说明正文。
- `POST /api/v2/admin/kill-switches`（201）：`org_admin` + CSRF。返回 `stopped_runs`。
- `POST /api/v2/admin/kill-switches/{id}/release`：另一位 `org_admin` + CSRF。

## 7. 未做

平台级全局开关；向 Manager 主动下发「撤销能力/停网络」指令（目前依靠既有生命周期：停止的 Run 若仍有活动 cell，按原路径发 `run.cleanup_requested` 并由 Manager/清理路径处理）；Web 管理界面；事故演练（OPS-08）。
