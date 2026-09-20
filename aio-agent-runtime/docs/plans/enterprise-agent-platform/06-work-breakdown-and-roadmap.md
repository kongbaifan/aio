# 06. 文件级实施任务、依赖与排期

> 全部任务状态：待实施。本轮没有完成下表中的业务开发任务。共有 110 项，按可交付 PR/验证单元拆分；标注路径为建议写入位置，新增路径当前不一定存在。

## 0. 使用新增的阶段执行手册

本文件保留 110 个父任务和角色/粗依赖；更细的实际执行依据是 [P0–P6 手册](stages/README.md) 与 [任务索引](stages/task-index.md)，共 718 个带编号子任务。每卡补充了改动位置、接口/数据契约、操作步骤、测试证据和 PR/回滚边界。

特别注意：[依赖与门禁](stages/dependencies-and-gates.md) 将 RUN-10 对 RUN-02、CAP-02 对 CAP-01 的前置拆为明确契约里程碑，避免把整张卡互相等待；也补充 REL-04 灰度前必须完成备份恢复和回滚演练等开放前置。其他原父依赖仍保留，细化不是删除原要求。

总表中的阶段时间是参考窗口，阶段手册将数据/审计/模型策略等安全底座明确前移到 P2；P5 是完成生产硬化和放行，不是到那时才补这些基础。所有状态保持待实施。

## 1. 人员与工作流

| 角色 | 主责 | 不应遗漏的协作 |
|---|---|---|
| BE-A 后端 A | 身份/权限、数据、会话、管理 API | 与安全共同定义资源动作，与 FE 定义错误和页面权限 |
| BE-B 后端 B | Run、AgentAdapter、工具网关、MCP/KB | 与 PE 定义执行协议，与 QA 定义恢复/幂等 |
| PE 平台工程 | Sandbox Manager、镜像、网络、资源、发布、备份 | 对执行边界负责，不把安全交给提示词 |
| FE 前端 | 新平台 Web、Run 交互、审批、管理台 | 用真实契约与双用户 E2E，不自行决定权限 |
| QA 测试 | 功能/契约/隔离/故障/性能回归 | 从 G0 介入，建设可重复的负例夹具 |
| SEC/ARCH | 威胁模型、关键设计/准入、安全验收 | 审查新执行器、新数据出口、新凭据模式 |
| PM/业务验收人 | 首批任务、范围、数据、验收与推广 | 确定正确答案和真实工作流程 |

不建议同一人独自承担所有生产安全判断。开发可并行，授权/执行契约必须先统一，避免各组各建一套 user_id 和 Run 状态。

## 2. 建议目录演进

```text
aio-agent-runtime/
  apps/local-harness/
    app/
      main.py                       # 组装路由/依赖；不执行长任务
      config.py                     # legacy 与平台配置边界
      api/v2/                       # auth、projects、sessions、runs、能力、admin
      auth/                         # OIDC、Principal、浏览器会话、成员同步
      policy/                       # 资源授权、风险、撤权、数据策略
      db/                           # engine、models、repositories、事务上下文
      runtime/                      # RunContext、状态机、job、event、approval、engine
      execution/                    # 到可信 manager 的客户端与 binding
      workspaces/                   # 工作区版本、租约、Artifact、上传槽
      capabilities/                 # 注册中心、ManifestSnapshot、发布与撤销
      tools/gateway.py              # 统一二次授权/审批/审计/执行路由
      tools/registry.py             # 保留无身份的 schema/定义
      skills/                       # 获权不可变包读取器与导入
      mcp/                          # 客户端、连接、OAuth、schema、调用策略
      knowledge/                    # 文档、摄取、ACL、检索、引用
      secrets/                      # SecretRef resolver，不回显原始密钥
      billing/                      # 预算、预留、账本、对账
      observability/                # 审计、trace、metrics、脱敏
      llm/                          # 复用模型兼容层，改凭据/策略绑定
    migrations/                     # Alembic 迁移及回填
    run_worker.py                   # 独立可信编排 Worker
    tests/                          # 保留旧测试，新增 v2/unit/integration
  services/sandbox-manager/
    src/sandbox_manager/
      api.py                        # 内部窄化服务契约
      service.py                    # 生命周期/验证/对账
      backends/                     # Docker，后续其他运行时
      profiles.py                   # 固定执行/网络模板
      workspace.py                  # 安全挂载与资源标识
      reconciler.py                 # lease/孤儿/清理
    tests/
  services/run-executor/
    src/run_executor/
      protocol.py                   # Run 内 JSONL/私有控制通道
      processes.py                  # 进程组、有界输出、deadline
      python_exec.py                 # Python adapter
      node_exec.py                   # 同 Run Node REPL adapter
      browser.py                    # 浏览器执行与 Profile
      files.py                      # 受限文件操作
      entrypoints.py                # 固定 Skill entrypoint
    tests/
  services/node-repl/                # 只作为执行单元内部依赖评估
  web/platform/                     # React + TypeScript + Vite 建议基线
    src/api/ auth/ components/ features/
    tests/
  infra/platform/                   # 控制/执行节点部署与策略
  infra/images/                     # 固定基础/分析/浏览器/parser 镜像
  compose.platform.yaml             # 新平台开发/集成环境；不是沿用旧共享部署
  scripts/platform/                 # 安全初始化、迁移、备份、验证
  docs/api/platform-v2.openapi.json  # 从实际代码生成的契约快照
  docs/plans/enterprise-agent-platform/
.github/workflows/                  # CI 仍放仓库真正根目录
```

前端基线可在 G0 根据团队经验替换为等价栈，但不要在项目中同时维护两套新的业务前端。现有 `app/static` 继续作为单机学习/回归参考，新平台逐步迁移其功能与视觉，不重写已验证的流式规则。

`services/run-executor` 推荐使用固定入口、由 manager 通过受控 runtime exec/私有通道调用；不把完整开发 Sandbox API 端口开放给所有人。

## 3. 任务定义与完成标准

每个任务完成必须包含：

- 改动文件与新/旧行为说明。
- 正向、权限拒绝、错误/超时测试；涉及数据必须有迁移与回滚说明。
- OpenAPI/事件/schema/文档同步；影响调用方需同时更新。
- 无 Secret、无临时安全 bypass、无“失败则在宿主运行”分支。
- CI 与手工验收证据链接；尚未完成测试必须写明，不用勾选代替证据。

以下表格的“文件/交付物”是具体 write scope，“验收”是该任务 DoD。依赖指最低前置条件，不代表只能串行执行。

## 4. FND：基线与架构冻结（6 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| FND-01 | QA/BE | 无 | 基线报告；复现 pytest/jsdom/ruff，记录版本与 skips，不调用真实外部写服务 | 有可重复命令与真实结果 |
| FND-02 | SEC/ARCH/PM | 无 | 数据分类、威胁模型、信任边界、运行时候选、初始业务样本与 ADR | G0 签字，开放/禁止能力明确 |
| FND-03 | BE/FE | FND-02 | 冻结 RunContext、状态、事件、错误、API v2 草案；需求追踪 | 前后端使用同一版本契约 |
| FND-04 | PE/QA | FND-02 | 独立 Linux 测试执行节点；无生产网络/凭据；固定测试镜像仓库 | 可以运行隔离测试且不接触生产 |
| FND-05 | BE/PE | FND-03 | 平台模块骨架、环境模式、CI job、测试配置、依赖锁定策略 | dev/test/prod 区分，旧模式不误开放 |
| FND-06 | SEC/PE | FND-01 | 来源/许可证/SBOM 盘点；审核归档组件、证书材料和模型使用条款 | V1 依赖有明确准入清单 |

## 5. DAT：持久化与迁移基础（6 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| DAT-01 | BE-A/PE | FND-05 | `app/db/engine.py`、开发 PG、Alembic；独立应用/迁移账号 | 应用非 owner/BYPASSRLS，迁移可重放 |
| DAT-02 | BE-A | DAT-01,FND-03 | 身份、项目、resources/grants 基础表与复合 FK | 跨 org FK 拒绝；新资源默认 private |
| DAT-03 | BE-B | DAT-02 | runs/steps/checkpoints/invocations/approvals/events/jobs/outbox 表；状态/唯一约束 | 并发创建、事务回滚、事件序号测试 |
| DAT-04 | BE-A/PE | DAT-02 | `workspaces/storage.py`；对象存储客户端、upload slot、候选/发布对象域 | 跨 scope 访问拒绝，超大上传中断 |
| DAT-05 | BE-A/QA | DAT-02 | `scripts/platform/import_legacy.py` 草案和映射格式，先 dry-run | 不猜所有者，无主数据隔离，不修改原库 |
| DAT-06 | BE-A | DAT-01,DAT-02 | request/job 事务上下文、参数化 set_config、连接池生命周期 | 取消/异常/连接复用不串组织 |

## 6. IAM：身份、权限与凭据（10 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| IAM-01 | BE-A/SEC | FND-02,DAT-02 | `auth/principal.py`、角色与资源动作模型，用户/部门/项目关系 | 多部门和私有 Session 规则明确 |
| IAM-02 | BE-A | IAM-01 | OIDC/BFF、HttpOnly Cookie、CSRF、登录退出、回调校验 | 假 issuer/aud/state、过期/重放全部拒绝 |
| IAM-03 | BE-A | IAM-02 | 成员 provisioning、外部组映射、离职同步与成员 revision | 删除/停用不是仅隐藏前端 |
| IAM-04 | BE-A/SEC | IAM-01 | `policy/service.py`：资源/动作/范围/风险决策，默认 deny | 角色不能越过 org ceiling |
| IAM-05 | BE-A | IAM-04,DAT-06 | v2 sessions/projects/files/versions 路由 scope 与稳定 403/404 | 全部对象列表与详情负例通过 |
| IAM-06 | BE-A/QA | IAM-04,DAT-06 | RLS 策略、FORCE、专用调度角色、SQL/批量接口校验 | 连接池污染/空上下文/跨组织测试 |
| IAM-07 | BE-A/PE | IAM-04,FND-06 | `secrets/`、SecretBinding、仅内部读取、禁用户 Shell 配置 | API 不回显；测试连接不泄露凭据 |
| IAM-08 | BE-A/BE-B | IAM-03,IAM-04 | 撤权版本/禁用通知、每次调用再检查、SSE 关闭 | 新调用立即被拒；失效池关闭 |
| IAM-09 | BE-A/SEC | IAM-04 | 支持授权、审批人与发起者分离、break-glass 授权模型 | 运维默认看不到正文；授权到期失效 |
| IAM-10 | QA/BE-A | IAM-05,IAM-06,IAM-08 | 双用户/部门/组织/角色矩阵、CSRF/SSO 会话测试 | G1 证据完整，无 P0 越权 |

## 7. RUN：任务、编排与可靠性（12 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| RUN-01 | BE-B | FND-03,DAT-03,IAM-04 | `runtime/context.py`、状态机与 transition validator | 模型/客户端不能覆盖可信身份字段 |
| RUN-02 | BE-B | RUN-01,IAM-05 | Run 创建/幂等键/session revision/活跃任务约束 | 同键同体同 Run；同键异体 409 |
| RUN-03 | BE-B | RUN-02 | PG job 领取、心跳、租约、generation 与公平队列 | 两 Worker 不同时有效执行同一 Run |
| RUN-04 | BE-B | RUN-03 | 事务事件/Outbox、序号、截断、内容引用、消费者去重 | 事件持久化与状态原子一致 |
| RUN-05 | BE-B/FE | RUN-04,IAM-08 | SSE 订阅/回放、慢消费者、Last-Event-ID、撤权检查 | API 重启/断线不丢终态、不串 Run |
| RUN-06 | BE-B | RUN-01 | `runtime/engines/base.py`、LocalHarnessAdapter、能力声明 | 引擎与 HTTP/DB 解耦，fake adapter 可跑 |
| RUN-07 | BE-B | RUN-06,CAP-01 | 改 `agent.py`：注入上下文/网关、持久消息/游标/checkpoint/结果、无全局 tool client | 原工具循环测试 + scope 回归通过 |
| RUN-08 | BE-B | RUN-01,IAM-09 | 持久 Approval、action_digest、CAS、到期、通知/恢复 | 重启仍可决定；变更参数强制新审批 |
| RUN-09 | BE-B/PE | RUN-03,RUN-08,SBX-11 | 取消、deadline、unknown/reconcile、旧 Worker 拒绝 | 不明外部写不自动重跑；取消终止进程树 |
| RUN-10 | BE-B | RUN-02,DAT-03 | Run 预算预留、调用计量接口、失败释放与 unknown usage 契约 | 并发请求不能绕过预留；未知量不当 0 |
| RUN-11 | BE-B | RUN-07,SBX-09 | 改 `orchestrator.py`：team 作为 Run steps，统一身份/模型/配额/工作区 | 子步骤不能扩大能力，最终回答与状态正确 |
| RUN-12 | QA/BE-B | RUN-05,RUN-09,RUN-11 | 重启、重复、断流、长等待、外部结果不明的集成测试 | G3 完整证据 |

## 8. SBX：执行层与资源隔离（14 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| SBX-01 | PE/SEC | FND-02,FND-04 | Linux/cgroup v2/运行时基线、节点隔离、管理身份与目录权限 | 目标环境支持所需资源/网络控制 |
| SBX-02 | PE/BE-B | RUN-01,SBX-01 | `sandbox-manager` 内部 API、Run binding、幂等、mTLS/短期身份 | 拒绝任意 mount/image/privileged 参数 |
| SBX-03 | PE | SBX-01,FND-06 | `infra/images` 固定分析/parser 镜像；非 root/只读根/锁依赖 | digest 固定，无 .env/密钥/开发缓存 |
| SBX-04 | PE/BE-B | SBX-02,SBX-03 | `run-executor` 窄协议、进程组、流式 stdout/stderr、文件边界 | 输出洪水/超时/退出码/UTF-8 可验证 |
| SBX-05 | PE/BE-B | SBX-04 | Python 与 Node 执行适配；REPL session 由 Run 绑定 | 两 Run 的变量、HOME、依赖互不影响 |
| SBX-06 | PE | SBX-04 | BrowserExecutor 与镜像/Profile/网络兼容，移除控制侧 CLI 路径 | 控制服务无浏览器子进程；Cookie 不跨用户 |
| SBX-07 | PE/BE-B | SBX-02,RUN-03 | CPU/内存/PID/磁盘/inode/时长/并发准入；规格与队列公平性 | 声明上限实际生效；超量排队，不超卖失控 |
| SBX-08 | PE/SEC | SBX-02 | 默认拒绝 egress/DNS、代理、管理网与元数据阻断 | 直连/重定向/IPv6/DNS 绕过负例通过 |
| SBX-09 | BE-A/PE | DAT-04,SBX-02 | WorkspaceVersion、写 lease、Run 工作副本、head CAS、只读挂载 | 同项目单写者；旧 lease 不能发布覆盖 |
| SBX-10 | BE-A/PE | SBX-09,SBX-04 | 停止执行后产物收集、扫描、不可变对象、原子发布 | 链接逃逸/大文件/未扫描对象不发布 |
| SBX-11 | PE/BE-B | SBX-02,SBX-07 | TTL、取消、销毁、孤儿 reaper、节点失联与隔离 | 容器/卷/进程清理可对账，失败可见 |
| SBX-12 | PE/BE-A | IAM-07,SBX-08 | 无长期 Secret 的执行模板、Run capability/连接器限权注入 | 不能访问管理凭据；过期/撤销 token 拒绝 |
| SBX-13 | QA/SEC/PE | SBX-05,SBX-06,SBX-07,SBX-08,SBX-10,SBX-11 | 真实 Linux 多沙箱隔离与资源滥用测试 | G2，无宿主执行 fallback，无共享污染 |
| SBX-14 | PE/SEC | SBX-13 | gVisor/Kata/微 VM 候选兼容与性能验证、安全域 profile | 任意代码开放前有 go/no-go；不强行关闭防护 |

## 9. CAP：能力、Skill 与 Agent 模板（7 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| CAP-01 | BE-B | IAM-04,RUN-01 | `tools/gateway.py`：统一上下文、授权、schema、风险与执行路由；审批 hook 后接 RUN-08 | 无全局 SandboxClient 闭包绑定 |
| CAP-02 | BE-B | CAP-01,DAT-02 | 能力/版本/ManifestSnapshot、授权目录和 alias 映射 | 隐藏不等于授权；未知/撤回工具拒绝 |
| CAP-03 | BE-A/PE | CAP-02,DAT-04 | Skill 包上传、解压/来源/Secret/依赖校验、隔离扫描 | 恶意归档不落到控制代码目录 |
| CAP-04 | BE-B | CAP-02 | 改 SkillRegistry 为获权固定版本 reader；摘要/引用/脚本路径解析 | 只能读当前获权版本，无全量目录泄露 |
| CAP-05 | BE-B/QA | CAP-03,SBX-13,RUN-08 | 测试 Run、审核发布、禁用/回滚、依赖兼容 | 旧任务固定版本，执行修改后重批 |
| CAP-06 | BE-A/FE | CAP-02,CAP-04 | Agent 模板/发布版本/允许模型和能力；导入少量现有 Skill | 业务人员只选模板，无底层系统权限 |
| CAP-07 | BE-B/QA | CAP-01,RUN-07 | 旧 HTTP/MCP 入口迁移/生产关闭；工具旁路枚举测试 | single/team/MCP/管理测试统一策略 |

## 10. MCP：外部能力连接（8 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| MCP-01 | BE-B | CAP-01,CAP-02 | 标准远程 MCP adapter、initialize/discovery/call/error，固定版本依赖 | 至少一个只读测试服务互操作通过 |
| MCP-02 | BE-B | MCP-01,IAM-07 | ConnectionInstance、credential scope、session/pool 分区 | 两身份调用不会混用 headers/Cookie/session |
| MCP-03 | BE-A | MCP-02,IAM-02 | OAuth/凭据绑定、回调、轮换、撤销、状态展示 | Secret 不回显，连接失效能终止后续调用 |
| MCP-04 | BE-B/SEC | MCP-01,SBX-08 | endpoint/redirect/资源链接校验、schema 变化/新工具审核 | 测试连接不成为 SSRF 后门 |
| MCP-05 | PE/BE-B | MCP-02,SBX-05,SBX-12 | stdio MCP 在专属执行单元安装/启动/停止；固定命令模板 | 无控制进程 spawn；状态/凭据不跨用户 |
| MCP-06 | BE-B/SEC | MCP-02,RUN-08,RUN-09 | 写工具意图、外部幂等、结果查询、审批映射、unknown | 假超时服务不会导致重复业务写 |
| MCP-07 | BE-B | MCP-01,RUN-04 | progress/result 映射、限额、超时、circuit breaker、错误脱敏 | 过大/畸形/失败响应不拖垮 Run/泄露秘密 |
| MCP-08 | QA | MCP-03,MCP-04,MCP-05,MCP-06,MCP-07 | 只读/写/stdio/撤权/重启/协议兼容测试 | 对应能力启用前逐项通过 |

## 11. KB：知识摄取与检索（9 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| KB-01 | BE-A | DAT-02,CAP-02 | KB/Document/Version/ACL/schema 与 API | 文档可比 KB 更窄，无 ACL 默认不公开 |
| KB-02 | BE-B | KB-01,RUN-03,DAT-04 | Ingestion job 状态、upload→parse→index 流程与重试 | 半完成文档不被检索 |
| KB-03 | PE/BE-B | KB-02,SBX-04,SBX-08 | PDF/DOCX/TXT/CSV/XLSX parser 沙箱，宏/外链/解压限制 | 损坏/恶意文件不在共享服务执行 |
| KB-04 | BE-B | KB-03,IAM-07 | chunker、embedding client、版本/维度/index 管理、幂等写入 | 重试不重复 chunk；更换模型不混维度 |
| KB-05 | BE-B | KB-04,IAM-06 | 授权混合检索、中文检索方案、rerank 与缓存 scope | 文本进入模型前已获权；ANN 过滤召回测试 |
| KB-06 | BE-A/FE | KB-05 | 引用阅读、页码/位置、原文下载、证据不足交互 | 引用再次鉴权，不能猜 chunk_id 读文档 |
| KB-07 | BE-A/BE-B | KB-05,IAM-08 | 文档更新/删除、epoch 防旧 Job 复活、上下文来源失效 | 撤权/删除后不从缓存/旧摘要继续外发 |
| KB-08 | QA/业务 | KB-06,KB-07 | 60+ 问答质量/授权样本、召回/正确率/引用评估 | 安全负例零泄露，业务门槛签字 |
| KB-09 | BE-B | KB-08 | 可选企业数据源增量同步：游标/删除/ACL/change token | P2 默认；确需首版时另估范围与接入等待 |

## 12. UI：业务工作台与管理台（10 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| UI-01 | FE | FND-03,FND-05 | `web/platform` TypeScript、路由、API client、生成类型、测试框架 | 无硬编码 Token，错误类型统一 |
| UI-02 | FE | UI-01,IAM-02 | 登录/退出/停用/无权限页面、CSRF、会话过期处理 | 登录回调与保护路由 E2E |
| UI-03 | FE | UI-02,IAM-05,CAP-06 | Agent 目录、项目/会话列表、成员和模型选择 | 只显示授权范围，不跨项目复用 state |
| UI-04 | FE | UI-01,RUN-05 | Run 创建、事件去重/断线回放、状态机、停止/重试/unknown 展示 | 浏览器刷新不中断任务，错误不显示为成功 |
| UI-05 | FE | UI-03,SBX-10 | 上传进度、扫描、预览、引用、Artifact 下载和分享 | 未发布文件不展示；预览安全头/域正确 |
| UI-06 | FE | UI-04,RUN-08 | 审批中心、业务影响摘要、到期/重启/重复决定状态 | 参数变更后不能误批准旧操作 |
| UI-07 | FE | UI-03,CAP-05,MCP-03,KB-02 | Skill/连接/知识管理基本页面与进度；个人/部门范围切换 | 不在前端保存 Secret，不回显原始凭据 |
| UI-08 | FE | UI-03,GOV-02,GOV-03,GOV-05 | 管理任务/用量/审计/限时支持 UI | 运维默认元数据；授权后才看允许内容 |
| UI-09 | FE/QA | UI-04,UI-05,UI-06 | 中文提示、键盘/焦点、移动端、加载/空态/错误态 | 不只靠颜色；过期状态可理解 |
| UI-10 | QA/FE | UI-07,UI-08,UI-09 | 双用户浏览器 E2E、XSS、权限撤销、重连、审批流程 | 关键业务旅程可重复自动运行 |

## 13. GOV：治理、预算、审计与排障（9 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| GOV-01 | SEC/BE-A | FND-02,IAM-04 | 数据分类、来源与派生产物标签传播、模型/embedding/reranker/连接器出口策略 | 不能因自动 fallback 将敏感数据发往不允许供应商 |
| GOV-02 | BE-A/SEC | DAT-03,IAM-04 | 替换审计为结构化事实、事务 Outbox、脱敏、审计访问权限 | 高风险审计失败即拒绝，常规遥测可降级 |
| GOV-03 | BE-B | RUN-10 | 预算 ledger、预留/结算/释放、unknown、价格版本与部门汇总 | 并发超支/重复 usage/失败收费测试 |
| GOV-04 | BE-A/PE | IAM-08,RUN-09 | 全局/组织/用户/工具/模型/执行类 kill switch | 已排队与后续调用受限，不能只改前端 |
| GOV-05 | BE-A/FE | IAM-09,GOV-02 | 限时支持 grant、脱敏诊断包、dry-run 回放、访问审计 | 调试不重复外部写，内容访问可追溯 |
| GOV-06 | BE-A | DAT-04,KB-07,IAM-04 | 资源分享/到期/撤回、留存删除、备份删除记录 | 默认 private，恢复不复活已删除资源 |
| GOV-07 | BE-A/BE-B | IAM-07,GOV-01 | 模型配置版本、端点允许集、生产禁 Shell、按身份缓存 | 任意用户 provider URL/命令被拒绝 |
| GOV-08 | PE/BE-B | RUN-04,SBX-11,GOV-02 | OpenTelemetry/metrics 关联、低基数指标、外部调用耗时 | 不带业务正文/Token，高风险异常有告警 |
| GOV-09 | QA/BE-B/业务 | CAP-06,KB-08,GOV-07 | 模型/Skill/提示变更回归集、质量与费用基线 | 发布新模型/模板有比较证据，不只“能回答” |

## 14. OPS：部署、容量与日常运维（8 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| OPS-01 | PE | FND-06,SBX-03 | CI 镜像构建、依赖锁、SBOM、扫描、签名/digest、回滚标签 | 只部署已批准镜像，不拉 latest 执行 |
| OPS-02 | PE/BE | IAM-02,SBX-02,RUN-03 | `compose.platform.yaml`/环境配置、反代/TLS、服务账号、生产校验 | 生产不能启用匿名/旧路由/共享 Sandbox fallback |
| OPS-03 | PE/BE-A | DAT-04,GOV-06 | PG PITR/对象版本/配置/密钥依赖备份，隔离恢复脚本 | RPO/RTO 用真实恢复演练证明 |
| OPS-04 | PE/QA | GOV-08 | 健康/就绪/告警、节点水位、队列/孤儿仪表盘、值班 Runbook | 告警能定位 run/node，未泄露正文 |
| OPS-05 | QA/PE | RUN-12,SBX-13,MCP-08 | 目标混合负载、长稳、慢消费者、故障注入、泄露检测 | 满足已冻结 SLO，无跨 scope 污染 |
| OPS-06 | PE/ARCH | OPS-02,OPS-05 | 生产 HA：多 API/Worker、PG 高可用、多执行节点与排空 | 单节点失效不丢权威状态；单机场景不宣称 HA |
| OPS-07 | PE/SEC | OPS-01 | 漏洞升级、镜像定期重建、依赖兼容、证书/Secret 轮换日历 | 有升级负责人、验证和回滚机制 |
| OPS-08 | PE/SEC/QA | GOV-04,OPS-03,OPS-04 | 环境污染/Secret 泄露/未知写/越权/磁盘满/模型费用事故演练 | 有处置证据、恢复与通知流程 |

## 15. REL：迁移、试点与发布（6 项）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| REL-01 | BE-A/QA | DAT-05,GOV-06,OPS-03 | SQLite/共享目录迁移预演、所有者映射、数量/hash/ACL 验证 | 无主数据不公开，原始备份可恢复 |
| REL-02 | SEC/QA | IAM-10,SBX-13,RUN-12,MCP-08,KB-08 | G1–G5 安全负例/滥用验证与遗留风险评审 | P0 无未关闭风险；例外必须限范围签字 |
| REL-03 | PM/业务/QA | UI-10,REL-02 | 真实业务类型 UAT、培训、验收记录 | 业务正确性与体验验收通过 |
| REL-04 | PE/PM | REL-03,OPS-04 | 部门白名单灰度、配额/能力开关、每日监控 | 扩量条件明确，不默认一键全公司开放 |
| REL-05 | PE/BE/QA | OPS-02,REL-01 | 应用版本/数据 expand-contract/能力/镜像回滚演练 | 不丢账本/权限，不自动撤销未知外部写 |
| REL-06 | PM/SEC/PE | REL-04,REL-05,OPS-08 | G6 放行、责任人、值班、SLA 边界、培训与技术债清单 | 有签字和证据索引，不靠口头“差不多” |

## 16. ENG：可选 Codex 引擎（5 项，不在 V1 关键路径）

| ID | 负责人 | 依赖 | 文件/交付物与工作细项 | 验收 |
|---|---|---|---|---|
| ENG-01 | ARCH/BE-B | RUN-06,GOV-01 | 固定版本官方文档/实验接口/条款与需求对照 | 是否适合生产的 go/no-go 初审 |
| ENG-02 | BE-B/PE | ENG-01,SBX-13 | `runtime/engines/codex.py` 和隔离 App Server 镜像/私有桥接 | thread/HOME/配置/凭据不跨用户 |
| ENG-03 | BE-B/SEC | ENG-02,RUN-08,CAP-01 | RPC 白名单、内置命令边界、审批/ToolGateway/模型代理映射 | 无 raw RPC 暴露，不能绕过权限或预算 |
| ENG-04 | QA/BE-B | ENG-03 | schema/事件/取消/恢复/错误/安全契约测试 | 与平台 Run 语义一致，缺失能力明确拒绝 |
| ENG-05 | ARCH/PM/PE | ENG-04 | 兼容、费用、性能、支持成熟度、回退路径评审 | 未通过继续关闭，不影响 LocalHarness |

## 17. 关键依赖图

```text
G0 / FND
  ├── DAT + IAM → G1
  │      ├── RUN Context / Job / Event / Approval → G3
  │      └── Resource/Secret/Data Policy
  ├── SBX Manager / Executor / Network / Workspace → G2
  └── UI 契约与基础框架

G1 + G2 + G3
  ├── CAP/Skill
  ├── MCP 身份与可核对写入
  ├── KB 摄取/ACL/引用
  └── 业务 UI + GOV → G4

G4 + 安全/负载/恢复测试 → G5 → 限部门试点 → G6 完整生产

EngineAdapter 稳定 + G2/G3/G4 → ENG 可选验证，不阻塞 V1
```

注意：RUN-07 与 CAP-01 可交错开发接口，但 CAP-01 的基本授权不依赖 RUN-07，避免循环；审批 hook 在 RUN-08 完成后接入。管理/前端可用 fake 服务提前开发，不得用 fake 结果替代最后集成验收。

## 18. 分阶段交付与时间窗口

参考团队与假设见总计划。下表是有交叠的日历窗口，不是各行累加。

| 阶段 | 参考时间窗口 | 核心输出 | 阶段退出条件 |
|---|---|---|---|
| P0 需求与技术基线 | 第 1–2 周 | G0、契约、干净 CI、Linux 测试节点、样本 | FND 完成；禁止范围冻结 |
| P1 多用户基础 | 第 2–5 周 | SSO/PG/资源授权/项目会话 API/前端登录 | G1；无全局 Token 生产路径 |
| P2 持久 Run 与执行隔离 | 第 4–9 周 | Worker/事件/审批/manager/单写工作区/所有执行器边界 | G2/G3；不能只完成 Python 隔离 |
| P3 核心能力闭环 | 第 8–13 周 | 少量 Skill/远程只读 MCP/上传 KB/引用/业务工作台 | G4；ACL 与版本撤销有效 |
| P4 受限安全试点 | 第 12–16 周 | 安全/恢复/容量验证、白名单员工、少量合规数据 | G5；有明确可用能力和禁用功能 |
| P5 完整生产治理 | 第 15–24 周 | 个人连接、受控写入、完整管理/运维/迁移/HA 需求 | G6；值班/回滚/演练和业务签字 |
| P6 可选增强 | G2/G3/G4 后独立安排 | Codex、更多数据源、长期记忆、更大规模池化 | 各自独立准入，不承诺随 V1 免费完成 |

### 18.1 粗粒度投入核算

| 工作包 | 建议投入范围（人周，含该包开发/测试/联调） |
|---|---:|
| 基线、威胁模型、契约 | 4–6 |
| 身份、数据、授权、迁移基础 | 10–14 |
| Run、事件、审批、可靠性 | 10–16 |
| 沙箱、网络、工作区、执行器 | 12–18 |
| Skill/MCP/KB 首批能力 | 14–22 |
| 前端工作台与管理台 | 8–12 |
| 治理、部署、故障/负载/上线收敛 | 12–20 |

合计约 70–110 人周量级，包含相关测试与联调，不再把相同 QA 投入重复计算。5 名全职加兼职架构/产品对应约 16–24 周的首版规划窗口；外部 SSO/业务 API/采购等待、全面任意代码开放或高敏隔离会延长周期。两人团队应重新裁剪业务范围或延长期限，不减掉安全底座。

## 19. 前 15 个工作日的具体推进建议

| 时间 | BE-A | BE-B | PE | FE | QA/SEC/PM |
|---|---|---|---|---|---|
| D1–2 | 资源/身份/数据模型草案 | Run/工具/事件契约 | Linux/运行时条件盘点 | 现 UI 行为与页面清单 | 选样本、威胁模型、重现基线 |
| D3–4 | PG/Alembic/基础表 | RunContext/状态/fake adapter | 干净执行节点/镜像基线 | 新 UI 框架/API 类型 | 两用户/部门/组织夹具、ADR 评审 |
| D5 | SSO/BFF 初链路 | 幂等创建接口草案 | manager 窄接口定义 | 登录/错误页面 | G0 检查；缺条件则限制试验范围 |
| D6–7 | Repository scope/RLS | job claim/lease/fencing | 固定镜像与 executor 雏形 | 项目/会话页面 mock | 空上下文/连接池/并发领取测试 |
| D8–9 | 对象授权/Session API | 持久事件/Outbox | 工作副本挂载/资源限额 | Run timeline/SSE mock | 第一条两用户端到端测试 |
| D10 | SSO 与 API 集成 | Worker 从 API 解耦 | 无宿主执行 fallback | 登录到任务创建联调 | 里程碑审查，不宣称可上线 |
| D11–12 | SecretRef/模型配置约束 | 持久审批/网关接口 | 网络默认拒绝/进程树停止 | 审批状态与断线回放 | 旁路清单、Secret/审批负例 |
| D13–14 | 撤权、上传槽契约 | single runner 适配 | reaper/TTL/孤儿对账 | 文件状态/权限错误 | 崩溃/重复/掉线/取消场景 |
| D15 | 数据/API 评审 | Run 契约评审 | G2 差距清单 | 集成演示 | 记录未完成项和下一轮范围 |

这只是前期工作安排，不承诺 15 天完成所有底座。必须以门禁证据而非日期决定开放程度。

## 20. 推荐 PR 顺序

1. PR-01：基线、契约、数据与安全决策、测试夹具（不开放新入口）。
2. PR-02：平台模式/PG/迁移/资源基础，保留 legacy 开发模式。
3. PR-03：SSO/Principal/资源授权/RLS 与负例。
4. PR-04：Run/Job/Event/Outbox/幂等 API。
5. PR-05：manager/executor 最小闭环，固定镜像、无宿主 fallback。
6. PR-06：WorkspaceVersion/写租约/Artifact 安全发布。
7. PR-07：网络/资源/取消/reaper/执行器覆盖。
8. PR-08：ToolGateway/持久审批/LocalHarnessAdapter/single+team。
9. PR-09：新 Web 的登录、任务、SSE、审批与文件。
10. PR-10：Skill/Agent 版本与审核目录。
11. PR-11：少量远程 MCP/连接身份/协议治理。
12. PR-12：KB 摄取/检索/ACL/引用/删除。
13. PR-13：预算、审计、支持、应急开关和管理台。
14. PR-14：真实隔离/恢复/负载/迁移/上线演练。

PR 可再按任务拆小；同一条未稳定的全链路不同时由多个 PR 修改相同核心函数。先把一条“登录→任务→专属执行→产物→销毁”的路径完成，再铺能力数量。

## 21. 每个阶段必须限制的入口

| 尚未通过 | 必须保持关闭 |
|---|---|
| G1 | 全公司访问、私有业务数据导入 |
| G2 | 任意 Python/Node/Shell/浏览器/stdio MCP/文档解析执行 |
| G3 | 外部写工具、自动任务接管、长任务生产使用 |
| G4 | 自助发布 Skill、个人任意 MCP、部门 KB 分享 |
| G5 | 扩大真实数据和员工范围 |
| G6 | 对外宣称高可用/生产服务承诺 |

这并非在开发环境不能验证这些能力，而是验证时只用受控测试身份、合成数据和专用执行节点。
