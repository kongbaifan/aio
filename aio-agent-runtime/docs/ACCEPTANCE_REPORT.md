# AIO Agent Runtime 验收报告

验收日期：2026-07-23

## 结论

项目已经整理为可以在本机学习和运行的 Local Harness。用户可以在工作台输入中文任务，由 Agent 选择工具，调用 Sandbox 读写文件、执行 Python、检查代码和查看运行指标；团队模式会先规划，再执行，再汇总。

## 已完成能力

- `apps/local-harness`：FastAPI 后端、单 Agent 工具循环、团队模式、会话、Skills 匹配、审计 JSONL、MCP 入口。
- `apps/sandbox-lite`：workspace 路径边界、Token 鉴权、文件大小限制、代码大小限制、执行超时、UTF-8 输出、WebSocket Shell 和运行指标。
- 工作台 UI：会话列表、单 Agent/团队模式、文件浏览、文件预览下载、执行轨迹、Skills 面板、Token 设置、移动端导航。
- 工作台视觉：采用 Linear 风格的深色会话侧栏、浅色内容区、紫色任务强调色、绿色运行状态和紧凑低圆角控件。
- Node REPL：有状态 JavaScript session，可由 Harness 配置为 `execute_javascript` 工具。
- Docker：Sandbox/Harness 分离网络、非 root 用户、资源限制和 `no-new-privileges` 配置。
- 项目整理：保留 canonical 源码，去除重复归档，来源和取舍写入 `docs/SOURCE_MAP.md`。

新增和修改的运行时代码包含中文注释；第三方归档源码保留其原始注释语言。

## 验证结果

| 检查 | 结果 |
|---|---:|
| Local Harness pytest | 3 passed |
| Sandbox Lite pytest | 7 passed |
| Node REPL validator tests | 3 passed |
| Python AST 源码扫描 | 236 files, 0 errors |
| Node/浏览器 JavaScript 语法检查 | 通过 |
| PowerShell 启动脚本语法 | 通过 |
| Compose YAML 解析 | 通过，包含 `sandbox` 和 `harness` |
| Harness 健康检查 | `ok` |
| Sandbox 健康检查 | `ok` |
| Node REPL 健康检查 | `ok` |

端到端任务也已验证：

- 单 Agent“列出文件”真实调用 `list_files`。
- 团队模式真实调用 `write_file` 和 `execute_python`，生成 100 条销售数据，计算总金额 `63125.00`。
- Node session 连续执行结果保持 `1 -> 2`。
- 带 Harness Token 的文件列表和下载接口分别返回 200；下载内容为 1630 字节。
- DeepSeek `deepseek-chat` 连通性请求通过，并完成真实 Agent 工具调用：模型选择 `list_files`，Sandbox 返回工作区文件后生成中文回答。
- 桌面 1440px 和紧凑移动断点 500px 截图已检查，控件没有重叠或裁切。

## 启动方式

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
.\scripts\start-local.ps1
```

工作台地址：`http://127.0.0.1:8080`

需要 Node REPL 时：

```powershell
.\scripts\start-local.ps1 -WithNode
```

> **过期说明（本报告是某次验收的快照，保留原文）**：这里描述的 `LLM_BASE_URL` /
> `LLM_API_KEY` / `LLM_MODEL` 映射已经不是当前实现。模型目录改为项目内
> `config/models.json`，每个 provider 自己配 `apiKey`（写环境变量名，值放 `.env`）；
> 全局 `LLM_API_KEY` 的跨 provider 兜底已被移除——它会把 A 家的密钥发给 B 家的 baseUrl。
> 当前配置方式见 README「模型配置」一节。

启动脚本会自动读取 `E:\code\agent\.env`：`BASE_URL` 映射为 `LLM_BASE_URL`，`DEEPSEEK_API_KEY` 映射为 `LLM_API_KEY`，`MODEL_NAME` 映射为 `LLM_MODEL`。没有外部配置时才使用演示模型。

## 验收限制

- 当前机器没有 Docker CLI，因此没有执行 `docker compose build/up`；Compose 文件只完成静态 YAML 解析和人工审查。
- 当前运行中的 8080/8081/8092 进程是在模型接入前启动的，仍显示 `demo`；新增配置会在下次通过启动脚本或手动重启 Harness 时加载。
- `apps/sandbox-lite` 会在本机直接启动 Python 和 Shell，只适合本地学习，不是生产级安全沙箱，不能暴露到公网。
- 生产部署仍需补充更严格的身份认证、网络出口策略、资源隔离、进程回收、持久化审计和人工确认流程。
