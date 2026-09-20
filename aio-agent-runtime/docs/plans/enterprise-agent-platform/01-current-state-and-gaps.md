# 01. 当前项目核查与改造差距

> 核查基线 `1164d95`。本文件区分已存在代码与拟新增能力。代码行号用于定位，后续改造可能移动；以符号名和实际源码为准。

## 1. 分析范围与优先级

优先分析 `apps/local-harness`、`apps/sandbox-lite`、`compose.yaml`、当前 CI。`services/node-repl`、`services/python-runtime` 用于评估可复用执行器，不把提取的完整运行时等同于已可部署的企业平台。

- **P0**：开放多用户/代码执行前必须解决；不能以“内网用户可信”跳过。
- **P1**：完整生产首版前解决，或明确限制功能后进入受控试点。
- **P2**：规模化和体验优化，可后续处理。

仓库没有 `.codegraph/` 或 `.trellis/`，本次没有创建索引、Trellis 任务或修改其配置。根目录有大量归档/提取物；实施写入以 `aio-agent-runtime` 为主，避免同时维护多个同名副本。

## 2. 基于源码的差距表

| ID / 级别 | 已存在事实与定位 | 多用户场景的问题 | 计划改造 |
|---|---|---|---|
| GAP-01 P0 | `app/main.py:82 RuntimeContainer` 仅构造一个 `SandboxClient`；`compose.yaml:2` 一个 sandbox 服务 | 多 Session 共用执行环境 | RunContext → SandboxBinding → 按 Run 获取执行客户端 |
| GAP-02 P0 | `compose.yaml:16` 所有人使用同一 `sandbox-workspace:/workspace` | 文件、可写依赖、用户目录污染；同名文件互相覆盖 | 项目持久目录 + Run 工作副本 + 独占写租约 |
| GAP-03 P0 | `app/main.py:118 _authorized` 只有全局 Token；未配置时允许访问 | 没有用户身份、部门成员关系、资源授权 | OIDC/BFF 登录、Principal、默认拒绝策略 |
| GAP-04 P0 | `app/main.py:375` 列出全部会话；详情/删除仅按 session_id 查找 | IDOR/BOLA：持有全局 Token 即可操作其他会话 | 所有列表和对象 API 强制组织/拥有者/项目授权 |
| GAP-05 P0 | `app/storage.py:16 SCHEMA` 没有 org_id/owner_id/project_id | 数据库无法表达租户与归属 | PostgreSQL 分表、约束、权限过滤与 RLS 防御 |
| GAP-06 P0 | `app/main.py:403` 文件 API 使用全局 sandbox，参数只有 path | 文件不绑定项目、任务和用户 | project/workspace/artifact 资源化；禁止全局文件浏览 |
| GAP-07 P0 | `sandbox-lite/server.py:364 execute_code` 是 Python 子进程，cwd 为 workspace | cwd 不隔离宿主文件、进程、网络 | OS 级隔离 + 只挂单一工作副本 + 限额/网络策略 |
| GAP-08 P0 | `server.py:450 shell_ws` 直接启动系统 Shell，没有与 Python 相同的 env 白名单 | 新执行路径绕过已有秘密过滤；同样没有用户隔离 | 首版业务入口关闭交互终端；未来进入专属沙箱并单独授权 |
| GAP-09 P0 | `app/clients/browser.py:38 run` 在 Harness 进程所在环境启动 CLI | Python 隔离不覆盖浏览器；继承共享服务环境 | BrowserExecutor 迁入 Run 沙箱，独立 Profile |
| GAP-10 P0 | `app/clients/node_repl.py` 只有服务 URL；`tools/registry.py:228` 接收模型提供 session_id | 不能把任意 session_id 当成用户权限 | 服务端绑定 run↔repl session；无直接外部访问 |
| GAP-11 P0 | `services/node-repl/worker.js:67/114` 使用 process Proxy、vm.Context、require | Node vm/Worker 是语言执行机制，不是多租户 OS 安全边界 | 只能作为沙箱内部解释器复用 |
| GAP-12 P0 | `app/llm/providers.py:98 _resolve_secret_value` 支持 `!` Shell 命令 | 一旦配置开放给用户，会把配置入口变为控制服务命令执行入口 | 生产仅允许受控 SecretRef；禁止用户配置 Shell、任意 baseUrl |
| GAP-13 P0 | `main.py:33 ConfirmationRegistry` 用内存 Future；confirm 只按 confirmation_id | 审批不绑定批准者/具体执行版本；跨进程与重启不可靠 | 持久 Approval，action_digest、过期、CAS、授权和审计 |
| GAP-14 P0 | `main.py:255 chat_stream` 直接在响应生成器中执行编排 | 连接生命周期与任务耦合，缺少独立持久 Run 和可靠取消 | POST Run + Worker + GET SSE 订阅与重放 |
| GAP-15 P0 | `app/sessions.py:62 SessionStore` 内存为唯一读路径；单进程锁 | 多 Worker 数据不一致；多个请求可交错修改同一会话 | 持久 Repository、事务、会话顺序/项目租约 |
| GAP-16 P1 | SessionStore 超过 50 会话会淘汰最旧项并删除持久记录 | 缓存容量策略变成业务数据删除 | 缓存淘汰不能删除权威数据；独立留存任务与审计 |
| GAP-17 P1 | `app/agent.py` 在本次局部 messages 里记录工具消息，持久 Session 主要保存用户和最终回答 | 重启无法精确重建工具过程；恢复容易重复外部写入 | 独立 Run/Step/ToolInvocation/Event/Checkpoint |
| GAP-18 P0 | `ToolRegistry.execute(name, arguments)` 缺少可信执行上下文；Python handler 未传会话绑定 | 业务工具拿不到完整身份与沙箱资源约束 | `execute(context, request)`；模型参数与授权上下文分离 |
| GAP-19 P1 | `SkillRegistry` 全局扫描目录，`context()` 输出全量目录 | 没有个人/部门范围、审核、版本、禁用、发布 | Registry + immutable SkillVersion + Grant + 显式依赖 |
| GAP-20 P1 | `mcp_server.py` 是将 Sandbox 工具向外暴露的 stdio MCP Server | 不是多用户 MCP Client/连接器管理；另有写能力策略路径 | 建设 MCP ClientAdapter；所有入口统一 ToolGateway |
| GAP-21 P1 | 当前 Harness 未看到知识库上传/解析/索引/ACL 检索链路 | 不能直接实现图中的部门知识库 | 新增摄取 Worker、文档版本、ACL、检索与引用 |
| GAP-22 P1 | `app/audit.py:9/23` JSONL，OSError 时继续；事件可能含工具原始参数 | 无统一用户/Run 关联；隐私与审计完整性风险 | 结构化脱敏审计 + 事务 Outbox；高风险动作审计失败即拒绝 |
| GAP-23 P0 | `server.py:375` capture_output 后才截断返回 | 返回上限不等于内存上限；大量输出先进入进程内存 | 增量读取、有界缓存、输出总量限制、限速与终止 |
| GAP-24 P0 | 超时主要针对直接进程；Shell finally 只 terminate/kill 外层进程 | 子孙进程和后台任务可能残留 | 进程组/cgroup/容器级停止 + reaper 验证 |
| GAP-25 P1 | 当前 usage 记录 Token 和 calls，不区分未上报与真实零 | 无组织预算、预留、并发超支与对账 | BudgetReservation + UsageLedger + unknown usage 标记 |
| GAP-26 P1 | `app/static/app.js:1/27` 全局 Token 放 localStorage、直接发聊天流 | 没有企业登录、授权页面、Run 恢复、审批中心 | 新平台 UI；HttpOnly 登录会话、CSRF、SSE 回放 |
| GAP-27 P0 | Compose 的 internal 网络同时连到 Harness 和 Sandbox | internal 仅限制某类外部连接，不代表沙箱不能攻击同网控制服务 | 分信任区域；只开放限定代理端点，禁止管理面访问 |
| GAP-28 P1 | Compose 有 cap_drop/非 root/资源限制，但无完整磁盘配额/只读根/生命周期管理 | 静态单容器保护不能覆盖动态多租户需求 | 固定安全 SandboxSpec + Admission + Host Reaper |
| GAP-29 P1 | `.github/workflows/ci.yml` 主要是 pytest、ruff、jsdom | 没有真实 OS 隔离、恢复、身份矩阵、负载验收 | 专用 Linux 隔离 CI 和安全/故障集成测试 |
| GAP-30 P1 | `docs/SOURCE_MAP.md` 明确部分生产构建/编排器不在提取源码内；旧验收未执行 Docker | 不能按完整生产系统现成可用来估算 | 路线以当前 apps 重构为主；归档组件按来源和安全审查逐个引入 |

上述是设计差距，不等于本轮已经主动验证了每一种可利用路径。不要将静态发现写成已完成的渗透测试结果。

## 3. 可以直接复用、需要重构、暂不纳入的部分

### 3.1 保留后逐步重构

| 部分 | 复用价值 | 重构边界 |
|---|---|---|
| FastAPI 路由、Pydantic DTO | 已有后端与测试基础 | 拆 router/service/repository；生产 `/api/v2` 独立契约 |
| ModelClient 与兼容 Provider | 支持不同供应商和流式工具调用 | 凭据 scope、模型白名单、预算、重试与 usage 修订 |
| AgentRunner / Orchestrator | 当前 single/team 任务循环可以验证业务 | 从 HTTP 生命周期剥离；注入 RunContext/ToolGateway；Team 属于同一 Run |
| ToolRegistry | 工具 schema 与 handler 集中 | 保留 schema 管理思想，移除绑定全局客户端的闭包 |
| SkillRegistry | 文档扫描、frontmatter、受限读取 | 迁移为版本包读取器；权限由 Registry/Policy 决定 |
| Sandbox HTTP client | 远程执行接口形态可参考 | URL/token 从可信 binding 获取；不得由模型或用户请求覆盖 |
| 工作台消息、工具轨迹 UI | 已有行为可做新 UI 验收参考 | 不把全局 state/token/session 假设带到多用户版 |
| 现有 pytest/jsdom | 保留历史兼容与错误处理的回归价值 | 新增租户隔离和真实运行时测试；不能把 mock 测试当安全证明 |

### 3.2 作为沙箱内部的执行组件评估

- `services/node-repl`：有状态 JS 执行；每个 Run 单独实例或绑定，不共享 Worker 的宿主执行权限。
- `services/python-runtime`：Jupyter/文件/运行时能力较多；先核查依赖、启动链、签名 middleware 和外部挂载路径，再决定替代最小执行器。不要在第一阶段为了“功能全”整包搬入。
- `apps/sandbox-lite`：适合演示和最小单元执行；生产路径应引入窄化运行时协议与安全配置，不继续把全部开发调试端点暴露出去。

### 3.3 首版不依赖

- 根目录多个 archive、来源提取快照和 Linux 二进制。
- `services/hijack-proxy` 及其证书相关材料，除非明确有必要且完成来源、证书、TLS 信任与合法性审查。
- 不存在于仓库里的原始生产调度器/构建链。
- 旧文档中引用但当前路径并不存在的开发命令；实施前逐项确认，不照抄执行。

这些不是要删除的文件。本计划不清理归档、不移动运行数据、不轮换用户现有密钥；如发现真实凭据历史问题，按独立安全流程处理。

## 4. 最容易漏改的调用路径清单

实施时必须一一审查，不只替换 Python 工具：

1. `/api/chat` 非流式路径。
2. `/api/chat/stream` 流式路径。
3. `team` 内各子步骤和汇总。
4. `mcp_server.py` 暴露的读写工具。
5. 浏览器 CLI 与其子进程。
6. Node REPL 和用户可指定 session 参数。
7. Sandbox 原始 HTTP/WS 接口。
8. 模型配置解析的 Shell 和自定义 endpoint。
9. 文件上传/预览/下载/打包与文档解析器。
10. Skill 的 scripts、初始化脚本、依赖构建钩子。
11. 管理员“测试连接”“测试 Skill”“调试任务”入口。
12. 后续 Codex 的直接命令和实验 process API。

**验收目标：所有路径都能明确回答“当前调用者是谁、获准访问什么、命令在哪执行、如何取消、如何审计”。**

## 5. 当前数据的迁移限制

现有 SQLite 没有所有者，不能根据会话标题、文件名或猜测分配给员工；共享 workspace 也无法自动判断文件归属。

迁移需要：

- 备份 SQLite、workspace、Skill 配置；先离线盘点、不直接公开。
- 管理员提供显式 `legacy_session_id → org/user/project` 映射。
- 无映射项进入“待归档/待认领”的受限空间，不默认给全公司。
- 原始文件导入为项目初始版本，记录 hash、来源与权限。
- 旧 Token 只用于隔离开发模式，不能转换成一张覆盖全部资源的生产凭据。
- 旧审计按原始事实保留并标记身份未知；不能伪造补齐为某个员工操作。

## 6. 实施前基线工作

1. 在干净开发环境记录 Python/Node/Docker/内核版本、当前依赖版本。
2. 运行现有 Harness、Sandbox、前端回归测试，记录实际 passed/skipped，不复用旧报告数字。
3. 以假模型和 fake 工具跑通 single/team、工具拒绝、失败/截断、SSE。
4. 在专用 Linux 执行节点构建当前镜像，检查非 root、挂载、网络和限额是否真正生效。
5. 建立两个用户、两个部门、一个共享项目的测试夹具，即使新接口尚未实现，先定义失败用例。
6. 记录现有行为哪些只保留在开发模式，哪些迁移到平台契约。
7. 产出依赖/镜像 SBOM、来源与许可证清单，审核提取组件是否可合法投入企业使用。

现有测试命令仅作为基线入口：

```text
apps/local-harness: python -m pytest tests -q
apps/sandbox-lite:  python -m pytest tests -q
apps/local-harness: npm test
项目目录:          ruff check apps tools scripts
```

依赖安装、模型调用、容器构建与运行应在实施阶段按环境准备流程执行。本轮没有执行这些命令。
