# 父任务索引与子任务领取入口

> 所有任务待实施。此索引由阶段手册与原 06 总表整理；下表负责人和最低父依赖沿用原定义。具体跨卡子任务约束见 [依赖与门禁](dependencies-and-gates.md)。

共 **110 个父任务、718 个子任务**；没有删减原任务或把规划完成当成实现完成。

## 阶段分布

| 阶段 | 手册 | 父任务 | 子任务 |
|---|---|---:|---:|
| P0 | [P0：需求、契约、基线与开发环境](p0-foundation.md) | 6 | 44 |
| P1 | [P1：身份、数据、权限与平台基础](p1-identity-data.md) | 18 | 113 |
| P2 | [P2：持久任务、工具网关与沙箱闭环](p2-runtime-sandbox.md) | 37 | 241 |
| P3 | [P3：共享能力与业务工作台](p3-capabilities-workbench.md) | 23 | 140 |
| P4 | [P4：试点准备、验证、迁移与限范围开放](p4-pilot-verification.md) | 16 | 100 |
| P5 | [P5：生产硬化、应急演练与正式交接](p5-production.md) | 4 | 38 |
| P6 | [P6：企业数据源与可选引擎增强](p6-extensions.md) | 6 | 42 |

## 逐项索引

原父依赖为粗粒度顺序；预算/Manifest 两处使用已明确的契约里程碑拆分。机器索引包含默认卡内顺序、其余父依赖及 82 条额外约束形成的实际子任务前置集合。

| 父任务 | 阶段 | 负责人 | 原最低父依赖 | 子任务数 | 状态 |
|---|---|---|---|---:|---|
| [FND-01 · 复现可运行基线与真实测试范围](p0-foundation.md#fnd-01) | P0 | QA/BE | 无 | 7 | 待实施 |
| [FND-02 · 冻结业务范围、数据级别与威胁模型](p0-foundation.md#fnd-02) | P0 | SEC/ARCH/PM | 无 | 8 | 待实施 |
| [FND-03 · 固定平台契约与跨组测试夹具](p0-foundation.md#fnd-03) | P0 | BE/FE | FND-02 | 8 | 待实施 |
| [FND-04 · 建立可销毁 Linux 执行测试环境](p0-foundation.md#fnd-04) | P0 | PE/QA | FND-02 | 7 | 待实施 |
| [FND-05 · 搭建开发骨架与安全模式开关](p0-foundation.md#fnd-05) | P0 | BE/PE | FND-03 | 7 | 待实施 |
| [FND-06 · 组件来源、许可证、构建链与供应商准入](p0-foundation.md#fnd-06) | P0 | SEC/PE | FND-01 | 7 | 待实施 |
| [DAT-01 · PostgreSQL、事务和迁移入口](p1-identity-data.md#dat-01) | P1 | BE-A/PE | FND-05 | 6 | 待实施 |
| [DAT-02 · 组织、项目、资源与授权实体](p1-identity-data.md#dat-02) | P1 | BE-A | DAT-01, FND-03 | 6 | 待实施 |
| [DAT-03 · Run、审批、事件与 checkpoint 持久结构](p1-identity-data.md#dat-03) | P1 | BE-B | DAT-02 | 6 | 待实施 |
| [DAT-04 · 受控对象存储与上传槽](p1-identity-data.md#dat-04) | P1 | BE-A/PE | DAT-02 | 7 | 待实施 |
| [DAT-05 · 旧数据盘点与迁移映射设计](p1-identity-data.md#dat-05) | P1 | BE-A/QA | DAT-02 | 6 | 待实施 |
| [DAT-06 · Request/Job 数据库上下文和连接池卫生](p1-identity-data.md#dat-06) | P1 | BE-A | DAT-01, DAT-02 | 6 | 待实施 |
| [IAM-01 · Principal、角色和授权词汇](p1-identity-data.md#iam-01) | P1 | BE-A/SEC | FND-02, DAT-02 | 6 | 待实施 |
| [IAM-02 · 企业登录、BFF 会话和 CSRF](p1-identity-data.md#iam-02) | P1 | BE-A | IAM-01 | 7 | 待实施 |
| [IAM-03 · 成员同步、停用和多部门变更](p1-identity-data.md#iam-03) | P1 | BE-A | IAM-02 | 6 | 待实施 |
| [IAM-04 · 默认拒绝的 PolicyService](p1-identity-data.md#iam-04) | P1 | BE-A/SEC | IAM-01 | 7 | 待实施 |
| [IAM-05 · v2 会话、项目和文件资源授权](p1-identity-data.md#iam-05) | P1 | BE-A | IAM-04, DAT-06 | 7 | 待实施 |
| [IAM-06 · RLS、防跨组织关联与专用角色](p1-identity-data.md#iam-06) | P1 | BE-A/QA | IAM-04, DAT-06 | 6 | 待实施 |
| [IAM-07 · SecretRef、内部解析与配置命令封堵](p1-identity-data.md#iam-07) | P1 | BE-A/PE | IAM-04, FND-06 | 7 | 待实施 |
| [IAM-08 · 撤权版本与实时再授权](p1-identity-data.md#iam-08) | P1 | BE-A/BE-B | IAM-03, IAM-04 | 6 | 待实施 |
| [IAM-09 · 审批人与支持访问的独立授权](p1-identity-data.md#iam-09) | P1 | BE-A/SEC | IAM-04 | 6 | 待实施 |
| [IAM-10 · 身份与资源隔离集成门禁](p1-identity-data.md#iam-10) | P1 | QA/BE-A | IAM-05, IAM-06, IAM-08 | 6 | 待实施 |
| [RUN-01 · 不可伪造的 RunContext 与状态迁移](p2-runtime-sandbox.md#run-01) | P2 | BE-B | FND-03, DAT-03, IAM-04 | 6 | 待实施 |
| [RUN-02 · 幂等创建 Run 与会话顺序](p2-runtime-sandbox.md#run-02) | P2 | BE-B | RUN-01, IAM-05 | 6 | 待实施 |
| [RUN-03 · Job 领取、租约、generation 与公平队列](p2-runtime-sandbox.md#run-03) | P2 | BE-B | RUN-02 | 7 | 待实施 |
| [RUN-04 · 事务事件、Outbox 与有界内容](p2-runtime-sandbox.md#run-04) | P2 | BE-B | RUN-03 | 6 | 待实施 |
| [RUN-05 · SSE 订阅、回放和撤权](p2-runtime-sandbox.md#run-05) | P2 | BE-B/FE | RUN-04, IAM-08 | 7 | 待实施 |
| [RUN-06 · EngineAdapter 与 LocalHarnessAdapter 边界](p2-runtime-sandbox.md#run-06) | P2 | BE-B | RUN-01 | 6 | 待实施 |
| [RUN-07 · AgentRunner 持久游标与工具调用重构](p2-runtime-sandbox.md#run-07) | P2 | BE-B | RUN-06, CAP-01 | 7 | 待实施 |
| [RUN-08 · 持久审批与 ActionSpec 冻结](p2-runtime-sandbox.md#run-08) | P2 | BE-B | RUN-01, IAM-09 | 7 | 待实施 |
| [RUN-09 · 取消、硬 deadline、未知结果与人工核对](p2-runtime-sandbox.md#run-09) | P2 | BE-B/PE | RUN-03, RUN-08, SBX-11 | 7 | 待实施 |
| [RUN-10 · 最小预算准入与用量事实](p2-runtime-sandbox.md#run-10) | P2 | BE-B | RUN-02, DAT-03 | 6 | 待实施 |
| [RUN-11 · Team 编排统一 Run 与权限](p2-runtime-sandbox.md#run-11) | P2 | BE-B | RUN-07, SBX-09 | 6 | 待实施 |
| [RUN-12 · Run 故障恢复集成门禁](p2-runtime-sandbox.md#run-12) | P2 | QA/BE-B | RUN-05, RUN-09, RUN-11 | 6 | 待实施 |
| [SBX-01 · 节点安全与运行时能力基线](p2-runtime-sandbox.md#sbx-01) | P2 | PE/SEC | FND-02, FND-04 | 6 | 待实施 |
| [SBX-02 · Sandbox Manager 窄接口与幂等绑定](p2-runtime-sandbox.md#sbx-02) | P2 | PE/BE-B | RUN-01, SBX-01 | 7 | 待实施 |
| [SBX-03 · 固定基础镜像和依赖层](p2-runtime-sandbox.md#sbx-03) | P2 | PE | SBX-01, FND-06 | 6 | 待实施 |
| [SBX-04 · 私有执行协议与进程生命周期](p2-runtime-sandbox.md#sbx-04) | P2 | PE/BE-B | SBX-02, SBX-03 | 7 | 待实施 |
| [SBX-05 · Python/Node 适配与私有依赖](p2-runtime-sandbox.md#sbx-05) | P2 | PE/BE-B | SBX-04 | 6 | 待实施 |
| [SBX-06 · 浏览器执行与 Profile 隔离](p2-runtime-sandbox.md#sbx-06) | P2 | PE | SBX-04 | 7 | 待实施 |
| [SBX-07 · CPU/内存/PID/磁盘/并发准入](p2-runtime-sandbox.md#sbx-07) | P2 | PE/BE-B | SBX-02, RUN-03 | 7 | 待实施 |
| [SBX-08 · 默认拒绝网络与可信出口](p2-runtime-sandbox.md#sbx-08) | P2 | PE/SEC | SBX-02 | 7 | 待实施 |
| [SBX-09 · 工作区版本、单写者与 CAS 发布](p2-runtime-sandbox.md#sbx-09) | P2 | BE-A/PE | DAT-04, SBX-02 | 7 | 待实施 |
| [SBX-10 · 安全产物收集、扫描与原子发布](p2-runtime-sandbox.md#sbx-10) | P2 | BE-A/PE | SBX-09, SBX-04 | 7 | 待实施 |
| [SBX-11 · 取消、TTL、Reaper 和节点隔离](p2-runtime-sandbox.md#sbx-11) | P2 | PE/BE-B | SBX-02, SBX-07 | 7 | 待实施 |
| [SBX-12 · Run capability 与最小凭据注入](p2-runtime-sandbox.md#sbx-12) | P2 | PE/BE-A | IAM-07, SBX-08 | 6 | 待实施 |
| [SBX-13 · 真实执行隔离与资源滥用验收](p2-runtime-sandbox.md#sbx-13) | P2 | QA/SEC/PE | SBX-05, SBX-06, SBX-07, SBX-08, SBX-10, SBX-11 | 7 | 待实施 |
| [SBX-14 · 更强隔离运行时准入](p2-runtime-sandbox.md#sbx-14) | P2 | PE/SEC | SBX-13 | 6 | 待实施 |
| [CAP-01 · 统一 ToolGateway 与执行路由](p2-runtime-sandbox.md#cap-01) | P2 | BE-B | IAM-04, RUN-01 | 7 | 待实施 |
| [CAP-02 · 能力版本、ManifestSnapshot 和命名映射](p2-runtime-sandbox.md#cap-02) | P2 | BE-B | CAP-01, DAT-02 | 7 | 待实施 |
| [CAP-03 · Skill 包上传与准入扫描](p3-capabilities-workbench.md#cap-03) | P3 | BE-A/PE | CAP-02, DAT-04 | 6 | 待实施 |
| [CAP-04 · 获权不可变 SkillPackageReader](p3-capabilities-workbench.md#cap-04) | P3 | BE-B | CAP-02 | 6 | 待实施 |
| [CAP-05 · Skill 隔离测试、审核、发布、禁用和回滚](p3-capabilities-workbench.md#cap-05) | P3 | BE-B/QA | CAP-03, SBX-13, RUN-08 | 7 | 待实施 |
| [CAP-06 · Agent 模板、发布版本与现有 Skill 种子导入](p3-capabilities-workbench.md#cap-06) | P3 | BE-A/FE | CAP-02, CAP-04 | 6 | 待实施 |
| [CAP-07 · 封闭所有 legacy 和调试旁路](p2-runtime-sandbox.md#cap-07) | P2 | BE-B/QA | CAP-01, RUN-07 | 6 | 待实施 |
| [MCP-01 · 标准远程协议适配器](p3-capabilities-workbench.md#mcp-01) | P3 | BE-B | CAP-01, CAP-02 | 6 | 待实施 |
| [MCP-02 · 连接实例和身份隔离连接池](p3-capabilities-workbench.md#mcp-02) | P3 | BE-B | MCP-01, IAM-07 | 6 | 待实施 |
| [MCP-03 · OAuth/凭据绑定、刷新和撤销](p3-capabilities-workbench.md#mcp-03) | P3 | BE-A | MCP-02, IAM-02 | 6 | 待实施 |
| [MCP-04 · 端点、schema 变更和 SSRF 约束](p3-capabilities-workbench.md#mcp-04) | P3 | BE-B/SEC | MCP-01, SBX-08 | 6 | 待实施 |
| [MCP-05 · stdio MCP 专属执行单元](p3-capabilities-workbench.md#mcp-05) | P3 | PE/BE-B | MCP-02, SBX-05, SBX-12 | 6 | 待实施 |
| [MCP-06 · 可核对的外部写调用](p3-capabilities-workbench.md#mcp-06) | P3 | BE-B/SEC | MCP-02, RUN-08, RUN-09 | 7 | 待实施 |
| [MCP-07 · 结果、限额、超时和熔断](p3-capabilities-workbench.md#mcp-07) | P3 | BE-B | MCP-01, RUN-04 | 6 | 待实施 |
| [MCP-08 · MCP 全链路互操作与安全验收](p3-capabilities-workbench.md#mcp-08) | P3 | QA | MCP-03, MCP-04, MCP-05, MCP-06, MCP-07 | 6 | 待实施 |
| [KB-01 · 知识库、文档版本与 ACL](p3-capabilities-workbench.md#kb-01) | P3 | BE-A | DAT-02, CAP-02 | 6 | 待实施 |
| [KB-02 · 摄取状态、Job 与发布一致性](p3-capabilities-workbench.md#kb-02) | P3 | BE-B | KB-01, RUN-03, DAT-04 | 6 | 待实施 |
| [KB-03 · 隔离 parser 与不可信文档](p3-capabilities-workbench.md#kb-03) | P3 | PE/BE-B | KB-02, SBX-04, SBX-08 | 6 | 待实施 |
| [KB-04 · 分块、嵌入、版本索引与计费](p3-capabilities-workbench.md#kb-04) | P3 | BE-B | KB-03, IAM-07 | 6 | 待实施 |
| [KB-05 · 授权混合检索、中文质量与缓存](p3-capabilities-workbench.md#kb-05) | P3 | BE-B | KB-04, IAM-06 | 6 | 待实施 |
| [KB-06 · 可验证引用与原文阅读](p3-capabilities-workbench.md#kb-06) | P3 | BE-A/FE | KB-05 | 6 | 待实施 |
| [KB-07 · 更新、删除、撤权与派生上下文失效](p3-capabilities-workbench.md#kb-07) | P3 | BE-A/BE-B | KB-05, IAM-08 | 6 | 待实施 |
| [KB-08 · 知识质量与 ACL 联合验收](p3-capabilities-workbench.md#kb-08) | P3 | QA/业务 | KB-06, KB-07 | 6 | 待实施 |
| [KB-09 · 企业知识源的增量与权限同步](p6-extensions.md#kb-09) | P6 | BE-B | KB-08 | 9 | 待实施 |
| [UI-01 · 平台前端骨架与类型化 API](p1-identity-data.md#ui-01) | P1 | FE | FND-03, FND-05 | 6 | 待实施 |
| [UI-02 · 登录、退出与无权限交互](p1-identity-data.md#ui-02) | P1 | FE | UI-01, IAM-02 | 6 | 待实施 |
| [UI-03 · Agent、项目与会话目录](p3-capabilities-workbench.md#ui-03) | P3 | FE | UI-02, IAM-05, CAP-06 | 6 | 待实施 |
| [UI-04 · 持久 Run 视图与恢复](p2-runtime-sandbox.md#ui-04) | P2 | FE | UI-01, RUN-05 | 7 | 待实施 |
| [UI-05 · 上传、产物、预览、引用和分享](p3-capabilities-workbench.md#ui-05) | P3 | FE | UI-03, SBX-10 | 6 | 待实施 |
| [UI-06 · 审批中心与业务影响说明](p2-runtime-sandbox.md#ui-06) | P2 | FE | UI-04, RUN-08 | 6 | 待实施 |
| [UI-07 · Skill、连接和知识的管理页面](p3-capabilities-workbench.md#ui-07) | P3 | FE | UI-03, CAP-05, MCP-03, KB-02 | 6 | 待实施 |
| [UI-08 · 任务、预算、审计与支持管理台](p4-pilot-verification.md#ui-08) | P4 | FE | UI-03, GOV-02, GOV-03, GOV-05 | 6 | 待实施 |
| [UI-09 · 可用性、可访问性和异常状态](p4-pilot-verification.md#ui-09) | P4 | FE/QA | UI-04, UI-05, UI-06 | 6 | 待实施 |
| [UI-10 · 双用户浏览器 E2E 与安全交互](p4-pilot-verification.md#ui-10) | P4 | QA/FE | UI-07, UI-08, UI-09 | 6 | 待实施 |
| [GOV-01 · 数据分级、来源和外发策略](p2-runtime-sandbox.md#gov-01) | P2 | SEC/BE-A | FND-02, IAM-04 | 6 | 待实施 |
| [GOV-02 · 持久审计、脱敏与高风险失败策略](p2-runtime-sandbox.md#gov-02) | P2 | BE-A/SEC | DAT-03, IAM-04 | 6 | 待实施 |
| [GOV-03 · 预算账本、结算、价格版本与对账](p4-pilot-verification.md#gov-03) | P4 | BE-B | RUN-10 | 7 | 待实施 |
| [GOV-04 · 应急开关与全链路禁用](p2-runtime-sandbox.md#gov-04) | P2 | BE-A/PE | IAM-08, RUN-09 | 6 | 待实施 |
| [GOV-05 · 限时支持授权、诊断包与安全回放](p4-pilot-verification.md#gov-05) | P4 | BE-A/FE | IAM-09, GOV-02 | 6 | 待实施 |
| [GOV-06 · 分享、留存、删除与备份删除事实](p4-pilot-verification.md#gov-06) | P4 | BE-A | DAT-04, KB-07, IAM-04 | 7 | 待实施 |
| [GOV-07 · 受控模型配置与凭据作用域](p2-runtime-sandbox.md#gov-07) | P2 | BE-A/BE-B | IAM-07, GOV-01 | 7 | 待实施 |
| [GOV-08 · Trace、指标、日志与低基数观测](p4-pilot-verification.md#gov-08) | P4 | PE/BE-B | RUN-04, SBX-11, GOV-02 | 6 | 待实施 |
| [GOV-09 · 模型、Prompt、Skill 与业务质量回归](p4-pilot-verification.md#gov-09) | P4 | QA/BE-B/业务 | CAP-06, KB-08, GOV-07 | 6 | 待实施 |
| [OPS-01 · 镜像构建、SBOM、签名与准入](p2-runtime-sandbox.md#ops-01) | P2 | PE | FND-06, SBX-03 | 6 | 待实施 |
| [OPS-02 · 平台环境、反代与生产校验](p2-runtime-sandbox.md#ops-02) | P2 | PE/BE | IAM-02, SBX-02, RUN-03 | 7 | 待实施 |
| [OPS-03 · 联合备份与隔离恢复](p4-pilot-verification.md#ops-03) | P4 | PE/BE-A | DAT-04, GOV-06 | 7 | 待实施 |
| [OPS-04 · Dashboard、告警和首批 Runbook](p4-pilot-verification.md#ops-04) | P4 | PE/QA | GOV-08 | 6 | 待实施 |
| [OPS-05 · 容量、长稳、慢消费者和故障注入](p4-pilot-verification.md#ops-05) | P4 | QA/PE | RUN-12, SBX-13, MCP-08 | 7 | 待实施 |
| [OPS-06 · 与承诺一致的高可用、故障域和排空](p5-production.md#ops-06) | P5 | PE/ARCH | OPS-02, OPS-05 | 10 | 待实施 |
| [OPS-07 · 依赖、镜像、证书与凭据的持续升级](p5-production.md#ops-07) | P5 | PE/SEC | OPS-01 | 8 | 待实施 |
| [OPS-08 · 真实职责分工的事故演练](p5-production.md#ops-08) | P5 | PE/SEC/QA | GOV-04, OPS-03, OPS-04 | 10 | 待实施 |
| [REL-01 · 旧库和共享文件迁移预演](p4-pilot-verification.md#rel-01) | P4 | BE-A/QA | DAT-05, GOV-06, OPS-03 | 6 | 待实施 |
| [REL-02 · G1–G5 安全负例与遗留风险复核](p4-pilot-verification.md#rel-02) | P4 | SEC/QA | IAM-10, SBX-13, RUN-12, MCP-08, KB-08 | 6 | 待实施 |
| [REL-03 · 业务 UAT 与使用培训](p4-pilot-verification.md#rel-03) | P4 | PM/业务/QA | UI-10, REL-02 | 6 | 待实施 |
| [REL-04 · 白名单灰度、配额与扩量判断](p4-pilot-verification.md#rel-04) | P4 | PE/PM | REL-03, OPS-04 | 6 | 待实施 |
| [REL-05 · 应用、schema、能力与镜像回滚演练](p4-pilot-verification.md#rel-05) | P4 | PE/BE/QA | OPS-02, REL-01 | 6 | 待实施 |
| [REL-06 · G6 放行、正式数据切换与运营交接](p5-production.md#rel-06) | P5 | PM/SEC/PE | REL-04, REL-05, OPS-08 | 10 | 待实施 |
| [ENG-01 · 固定 Codex 版本、协议和合规验证清单](p6-extensions.md#eng-01) | P6 | ARCH/BE-B | RUN-06, GOV-01 | 7 | 待实施 |
| [ENG-02 · 隔离 App Server 与私有桥接](p6-extensions.md#eng-02) | P6 | BE-B/PE | ENG-01, SBX-13 | 7 | 待实施 |
| [ENG-03 · RPC 白名单、工具、审批与费用策略映射](p6-extensions.md#eng-03) | P6 | BE-B/SEC | ENG-02, RUN-08, CAP-01 | 7 | 待实施 |
| [ENG-04 · 引擎契约、取消、恢复与安全差量](p6-extensions.md#eng-04) | P6 | QA/BE-B | ENG-03 | 6 | 待实施 |
| [ENG-05 · 引擎选择、费用性能、灰度和回退决定](p6-extensions.md#eng-05) | P6 | ARCH/PM/PE | ENG-04 | 6 | 待实施 |

## 工单导入与维护

- [work-items.json](work-items.json) 是可机读的初始工作分解：包含阶段、负责人、原父依赖、子任务、真实前置集合与定位。
- Markdown 任务卡为内容依据；JSON 是派生索引，不应单独修改成第二份相互矛盾的计划。更新文档后需重新生成/核对索引。
- 导入 Jira/飞书等系统时，父任务可建 Story、子任务建 Subtask，依赖用 blockers；任务状态仍从待实施开始。
- 代码接口就绪、真实集成完成、允许试点/生产开放应分列，不把一次 PR merge 自动等同生产验收。
- source_line 是当前文档定位提示，可能随文档更新移动；稳定引用以 task ID 和 HTML anchor 为准。
- 依赖图表示保守顺序，不是并发人数或精确工期承诺。需要更细并行时先明确契约和验收，再修改依赖。
