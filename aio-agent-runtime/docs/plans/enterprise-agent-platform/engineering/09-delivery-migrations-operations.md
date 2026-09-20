# 09. PR、迁移、交付证据与运维执行配方

> 沿用 110 父任务/718 子任务和 P0–P6，不引入未经估算的业务范围。以下是提交方式与证据标准，所有 PR、测试和发布动作尚未执行。

## 1. 交付证据画像

每个子任务由所属领域绑定最低证据画像，实际领取时再确认具体文件/命令/样本。不能自动把“写了文档”当作实现代码，也不能给所有决策任务机械要求修改业务源代码。

| 画像 ID | 适用工作 | 必须提交的证据 | 不可冒充完成的替代 |
|---|---|---|---|
| EP-DESIGN | 业务范围、ADR、来源、协议设计 | 具体决定、备选、风险、责任人/批准范围、可验收正负例 | 只有大图或“待考虑”清单 |
| EP-DATA | 表/约束/RLS/事务/回填 | 迁移、旧/新 fixture、角色权限、冲突/回滚/负例、恢复点 | 只修改 ORM 类 |
| EP-SERVICE | API/策略/Run/账本服务 | 接口/schema、授权/失败/并发测试、版本兼容、结构化错误 | happy path 200 或纯 mock 所有依赖 |
| EP-RUNTIME | manager/executor/网络/存储/镜像 | 实际环境 fingerprint、配额/隔离/进程树/清理/泄漏证据 | 只列安全配置未运行 |
| EP-INTEGRATION | Skill/MCP/KB/引擎 | 版本/身份/数据/外部效果契约、互操作/故障/撤权测试 | 测试连接成功或最终文本看似正确 |
| EP-UI | 前端和交互 | 真实契约、状态/权限/并发响应、键盘/错误/XSS、浏览器证据 | 只有截图或隐藏按钮 |
| EP-VERIFY | 集成/安全/性能/质量验收 | 测试样本、环境、断言、原始结果、失败/skip 说明与复测 | 汇总通过率无原始记录 |
| EP-OPERATE | 备份/恢复/告警/升级/演练 | 已执行时间线、目标资源、责任人、回滚、权限与数据核对 | 仅脚本文件存在 |
| EP-RELEASE | 迁移切换/灰度/生产放行 | 范围与版本 manifest、Gate 链接、批准/停止条件、值班和回滚证据 | 研发口头宣布可上线 |

测试画像并不阻止开发过程中使用 fake；它规定最终哪些事实必须通过真实依赖/隔离节点验证。

## 2. 子任务验收包结构

```json
{
  "task_id": "RUN-02.04",
  "implementation_status": "not_started",
  "contract_revision": "engineering-v1",
  "scope": {"files": [], "migration_ids": [], "api_or_event_changes": []},
  "design_refs": [],
  "invariant_ids": [],
  "baseline_case_ids": [],
  "task_specific_tests": [],
  "dependency_evidence_refs": [],
  "implementation_pr": null,
  "tested_commit": null,
  "environment_fingerprint": null,
  "expected_results": [],
  "actual_results": null,
  "rollback_plan_ref": null,
  "reviewer_decision": null,
  "release_scope_approval": null
}
```

- 这里空字段是模板，不是可完成验收的记录；正式领取前必须补 scope/专属正负例，实施后才能填 actual。
- `baseline_case_ids` 来自本层映射，只提供相关底线，不声称完整覆盖该子任务的所有代码。
- 上层 DAG 的依赖完成、当前设计版本一致、测试环境就绪和所需证据齐全才允许签字。
- 任何“因为未连外部系统所以 skipped”必须标 not_verified 或关闭能力，不能填 passed。

## 3. 第一条闭环的 12 个参考 PR 切片

这些不是替代全部任务的 12 个大 PR。可再拆小，但一条切片必须能在安全默认下验证。

| 切片 | 具体写入范围 | 关键验证 | 合并时仍关闭的内容 |
|---|---|---|---|
| PR-E01 模式与配置安全 | 当前 config/main 组装入口，生产配置前置校验，legacy-local 隔离 | ECASE-39/40；初始化前禁 Shell/匿名 fallback | 所有 v2 执行能力 |
| PR-E02 DB 角色与初始 schema | DB engine/migrations、身份/资源基础表、复合 FK | 临时 PG 空库/旧 fixture、非高权角色 | 未授权 API |
| PR-E03 BFF 身份 | Principal、SSO/callback/session/CSRF、停用 | AUTH suite、ECASE-17 | 后台执行 |
| PR-E04 资源/策略/RLS | Repository/授权/事务上下文/列表/详情 | ECASE-15/16/18、跨用户下载 | 原始执行端口 |
| PR-E05 Run/版本/预算领域 | Run/Job/Manifest/Approval/checkpoint/ledger schema 和状态类型 | 延迟 FK、状态/唯一约束、canonical golden vectors | 真实模型/副作用派发 |
| PR-E06 原子提交 | TX-01 和预算预留/idempotency、Session 顺序 | ECASE-01/02/03 | 未接 manager 的执行 |
| PR-E07 Worker/Event/fake engine | TX-02、generation、Outbox/SSE、checkpoint 接口 | ECASE-04/05/19；fake 不改真实环境 | 任意命令 |
| PR-E08 manager/compute target | 固定镜像、真实资源/网络/配额/私有协议 | ECASE-20/21/23/24/25 | 未验证 browser/parser/connector |
| PR-E09 Action/Approval/Dispatch | TX-03/04/05/06、假下游幂等/核对 | ECASE-06～12、审计失败 | 真实外部业务写 |
| PR-E10 workspace/Artifact | 私有副本、collector、TX-08/CAS、来源策略 | ECASE-13/26/27/28 | 未批准分享/文件类型 |
| PR-E11 真实 LocalHarnessAdapter | 改 agent/orchestrator，受控 ModelService，ToolGateway、预算/审计 | ECASE-14/35/37/40、single/team 回归 | 未验证外部连接器 |
| PR-E12 v2 用户闭环 | Run/审批/上传/结果 UI、epoch/cache/SSE | ECASE-18/19/38、原 UITEST | 未通过 G5 的用户/数据范围 |

后续 Skill/MCP/KB 与管理功能继续按 P3–P5 卡片拆分。不要把所有新目录一次性生成空壳后宣称完成 718 项。

## 4. 代码审查必须看到的负例

| 改动类别 | 必须解释/演示 |
|---|---|
| 新 API | 未登录、跨 org、同 org 无权、过期权限、重复/并发请求 |
| 新表/查询 | org/RLS/FK、连接污染、索引与迁移回填、无上下文 |
| 新外部调用 | endpoint/凭据范围、timeout/未知效果、重试/费用、审计先后 |
| 新执行器 | 实际所在 cell、网络/Secret/配额、输出/进程树/销毁 |
| 新 Artifact/知识输出 | 内容类型、来源、ACL、删除/撤权与分享 |
| 新缓存 | key 的身份/版本范围、迟到响应、失效丢通知 |
| 新状态/事件 | 允许迁移、终态、重放、旧 schema、不同角色可见性 |
| 新回滚/管理功能 | 是否丢账/复活权限/重复业务效果，support grant 与审计 |

## 5. 迁移与兼容执行步骤

### 5.1 本地/CI 的迁移验收

1. 生成真实迁移并检视 SQL：非空/唯一/延迟 FK/RLS/角色/索引，确认不凭默认用户创建高权限表。
2. 用空库升级到目标版本，跑 core fixture。
3. 用上一个兼容版本 fixture 升级，核对行数/hash/归属/状态/金额。
4. 并发访问背景下验证新增约束不会静默丢数据；大表回填按批次并明确锁影响。
5. 旧 API/Worker 兼容读取必要字段，未知状态/checkpoint 必须安全拒绝而非从头重跑。
6. 回滚优先旧兼容应用或前向修复；破坏性 down migration 不能自动删除已产生的新业务事实。

### 5.2 生产窗口的额外约束

- 明确授权后才可修改真实环境；本规划不是生产操作授权。
- 一次只由受控迁移 job 写 schema，应用启动只检查兼容，不由多个 Worker 抢着 migrate。
- 备份点一致、恢复经过演练、当前撤权/删除事实可重放。
- 旧系统停写后最终增量与 verify；无主会话/文件保留隔离，不自动公开。
- 迁移后不能恢复旧 DB 快照抹掉新预算/审批/删除事实；必要时维护窗口进行受控数据合并。

## 6. 配置安全启动矩阵

| 缺失/不安全项 | production 行为 | 允许的开发行为 |
|---|---|---|
| 无企业身份配置/默认共享 Token | 拒绝业务路由或启动失败 | 显式 legacy-local，仅回环与合成数据 |
| DB 应用角色是 owner/BYPASSRLS | 拒绝上线，要求修正角色 | 临时测试必须标不具备多租户证据 |
| manager/profile/硬配额不可用 | 排队/拒绝对应能力 | fake adapter，不本机执行不可信代码 |
| 模型 apiKey 命令/未知 endpoint | 解析前拒绝 | 旧本地配置仅保留明确开发模式 |
| Secret 服务不可用 | 禁相关调用，不回落公共凭据 | fake Secret provider 无真实权限 |
| 无当前权限/审计事实存储 | 停新敏感/副作用动作 | 合成 fixture，不开放真实数据 |
| 新引擎/协议实验能力未审 | 默认关闭 | 独立实验环境、单独验收 |

配置中的布尔/枚举/范围非法应报错，不把无法解析的值当 permissive 默认。环境变量可由部署管理员控制，这仍依赖组织基础设施权限治理，不能让用户 Skill 修改控制服务配置。

## 7. 故障收敛而非简单“重启服务”

### 7.1 任务卡住

按 Run→Job lease→Invocation/Dispatch→Approval→target binding→Artifact/ledger 查询；每层只读取获权字段。若在 dispatching/unknown，先核对下游；如果只是等审批，告知期限，不重启所有沙箱。

### 7.2 Manager/节点失联

停止新分配、保留容量占用、撤销旧 generation，依据硬 deadline 与 Reaper 核对。节点重新加入必须清点旧资源，不因“机器起来了”就把所有计数归零。

### 7.3 审计/费用异常

区分权威 PG/意图不可写与外部归档暂时故障。前者阻止高风险派发；后者保持 Outbox 有界积压/告警。未知 usage 不能直接清零，核对后追加调整。

### 7.4 安全事件

先按最小必要范围禁用户/连接/能力/profile/节点；撤 Token、隔离网络、保护证据；恢复时重新跑对应 ECASE 和原门禁。不能用“删除 workspace”证明安全恢复。

## 8. 测量口径

- API latency：请求进入到已持久响应，模型推理另计，不把排队时间藏起来。
- Run queue：TX-01 commit 到第一次有效领取，不因重试重置起点。
- Run execution：首次 preparing 到结果/明确终态，审批等待是否计入总期限按契约固定。
- Sandbox provision：请求准入到外部 manager 确认 ready，镜像拉取冷/温分别计。
- Cancellation：cancel accepted→禁止新派发→进程停止→资源销毁分别计，不只测 HTTP 返回。
- Unknown effects/usage：独立计数与最长未解决时间，不合并为普通 error 掩盖。
- 资源成本：按所有 target cells 加总，不能只计 Run 数量；parser/background connector 同样计。

指标 label 不带 user/run/文件名/原始 URL 等高基数敏感字段，相关 ID 留在受控 trace/log 中。

## 9. 阶段审查的问题清单

每阶段退出问：

1. 新增了哪些资源或执行路径？相应拒绝例和真实依赖测试在哪里？
2. 哪些状态仍可能 outcome_unknown？谁能核对、哪里被阻断、资源是否回收？
3. 哪些数据被发送给哪些模型/MCP？来源和凭据有没有跨域？
4. 哪些条件只经过 mock，哪些是真实节点/数据库/浏览器验证？
5. 发生回滚是否丢账、丢审计、复活已撤权数据或重复外部动作？
6. 运行中换权限/版本/连接/镜像会怎样？测试是否覆盖竞争？
7. 尚未通过的能力是否在 API/网络层真正关闭，而不只按钮隐藏？
8. 计划数字、工期和 SLA 是否已有实测支持，还是仍然假设？

## 10. 本轮深化的完成标准

本轮完成意味着设计、任务映射与文档结构一致，关键错误边界得到澄清。**不意味着这些事务、cell 隔离、测试、迁移或事故演练已经实现。**

真正实施应从第一条安全闭环开始，按 task ID 逐项产生 PR 与证据；如果任务还缺必要企业决策，应记录具体 blocker，而不是继续制造大量空目录或假测试通过记录。
