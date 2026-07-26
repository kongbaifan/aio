# AIO Agent Runtime

这是一个面向 AI Agent 的沙箱运行时项目。它把文件、代码、终端、浏览器、MCP 和业务 Skill 组织成可组合的执行能力。

## 项目定位

```text
Agent / LLM
    -> Skill 选择和任务拆解
    -> MCP / HTTP 工具调用
    -> Python 沙箱、Node REPL、浏览器、终端
    -> 文件、代码执行结果或业务系统结果
```

这里的 Agent 编排逻辑通常由上层应用提供；本项目主要负责工具执行、运行时隔离、协议接入和容器内进程管理。

## 目录结构

```text
apps/                 可独立学习或运行的应用
  sandbox-lite/       FastAPI + WebSocket 教学版沙箱
  local-harness/      本地 Agent 循环、工具注册和工作台 UI
services/             核心服务源码
  python-runtime/     FastAPI 沙箱 API 和代码解释器
  node-repl/          有状态 JavaScript REPL
  hijack-proxy/       Go 请求代理
packages/             可复用框架和 SDK
skills/               业务 Skill、系统 Skill、Agent Skill
infra/                容器入口、初始化脚本、Nginx/Supervisor 配置
web/                  浏览器和终端界面
docs/                 架构、API、协议、工程规范和学习路线
tools/                脚本模板
artifacts/            Linux 运行时二进制，不是源码
```

## 最快开始

建议先在项目根目录创建一个合并虚拟环境，两个本地服务共用它：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
```

依赖安装完成后，可以用一个 PowerShell 窗口启动本地 Harness（关闭窗口或按 Ctrl+C 会同时停止子服务）：

```powershell
.\scripts\start-local.ps1
```

需要同时启用有状态 JavaScript REPL 时：

```powershell
.\scripts\start-local.ps1 -WithNode
```

脚本只监听 `127.0.0.1`。模型来自 `config/models.json`，密钥写在项目根 `.env`（如 `DEEPSEEK_API_KEY`）。首次使用仍需按下面步骤安装 Python 依赖。

先启动 Sandbox 和本地 Harness：

```powershell
cd apps\sandbox-lite
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python start.py
```

另开一个终端启动 Harness：

```powershell
cd apps\local-harness
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

然后访问 `http://127.0.0.1:8080`。Harness 可以直接输入“列出文件”或“生成销售数据 CSV”。

### 模型配置（项目内 `config/models.json`）

模型目录只在本仓库管理，**不读取** `~/.pi`。写法对齐 pi：在 **provider** 上配置 `baseUrl` / `api` / `apiKey` / `compat` / `models`。

`apiKey` **请写环境变量名**，密钥本身放进 `.env`（已被 `.gitignore` 忽略）：

```json
{
  "default": { "provider": "fastai", "model": "gpt-5.5" },
  "providers": {
    "zmoon": {
      "baseUrl": "https://newapi.zmoon.top/v1",
      "api": "openai-completions",
      "apiKey": "ZMOON_API_KEY",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false,
        "maxTokensField": "max_tokens"
      },
      "models": [{ "id": "grok-4.5", "name": "grok-4.5", "maxTokens": 128000 }]
    }
  }
}
```

```bash
cp .env.example .env   # 然后填入 ZMOON_API_KEY 等
```

`apiKey` 也支持字面量（`sk-...`）和 shell 命令（`!op read op://...`）两种写法，但 **`config/models.json` 是要提交的文件** —— 字面量密钥请只写在 `config/models.local.json`（已忽略，会深合并覆盖同名 provider）。

CI 的密钥扫描覆盖整个子项目，不只是 `models.json`：真实密钥同样会被粘进测试、文档和示例配置（已经发生过一次，一个可用的 key 进了 `tests/test_providers.py` 的字面量用例）。规则匹配 `sk-` / `key-` / `AIza` / `gh*_` / `xox*` 等形态并带长度阈值，测试里请用 `sk-test-…` 这类假值。

工作台输入框上方可下拉切换模型（会话级）。

也可以使用 Docker Compose：

```powershell
copy .env.example .env
docker compose up --build
```

`config/` 和 `skills/` 以只读卷挂载进 harness 容器，模型密钥通过 `.env` 注入环境变量，都不会烤进镜像。容器里目录层级和裸机不同，compose 用 `HARNESS_PROJECT_ROOT=/app` 显式指定项目根。

Sandbox 单独访问 `http://127.0.0.1:8081`，Harness 工作台访问 `http://127.0.0.1:8080`。

## 两种执行模式

- **single**：单个 Agent 循环，最多 `MAX_AGENT_ROUNDS`（默认 8）轮工具调用。
- **team**：先让模型把任务拆成最多 `MAX_TEAM_STEPS`（默认 4）步，逐步执行后汇总。各步骤**共享同一个会话**，所以后面的步骤能看到前面生成了什么文件。

两种模式都是流式的，也都支持人工确认。

## Skill 如何参与推理

`skills/` 下每个目录一个 SKILL.md，正文是实质性的操作指南（全仓库约 6000 行），并常常引用同级或邻近 skill 的 `references/` 文档。这些内容按**渐进式披露**使用，不会整体塞进上下文：

1. 每轮对话的 system prompt 注入全部 30 个 skill 的 `name + description` 清单（约 3k token，加基础指令后 system prompt 共约 4k token）。
2. 模型自己判断任务落在哪个 skill 的领域，用 `read_skill` 读它的 SKILL.md。
3. SKILL.md 里若要求先读某个 references 文档，模型继续 `read_skill` 取。

关键词匹配（`DOMAIN_KEYWORDS`）仍在，但只作为「可能相关」的提示写进清单，不再决定模型能看到什么 —— 它只覆盖 7 个域，「请假审批」「考勤」「发消息」这类查询会完全落空。

两类路径互不相通，不要混用：

| 工具 | 作用范围 | 权限 |
|---|---|---|
| `read_file` / `write_file` / `list_files` | sandbox workspace | 读写 |
| `read_skill` / `list_skill_files` | 项目 `skills/` 目录 | 只读，路径边界由 `SkillRegistry` 约束 |

工具结果进入模型上下文前会按 `HARNESS_TOOL_CONTEXT_LIMIT`（默认 8000 字符）截断，并附一句
「输出已截断，需要后续内容请分段读取」。sandbox 侧 `read_file` 允许 10MB、`execute_python`
输出允许 1MB、`browser_snapshot` 无上限，不截的话读一个大文件就会把几 MB 塞进 `messages`，
而且会留在里面参与**之后的每一轮**，token 成本按轮次翻倍。不加那句说明的话更糟——模型会把
截断处当成文件真正的结尾。

## 会话持久化

会话、消息历史和 token 统计落在 `var/sessions.db`（SQLite），重启后原样恢复。用 `HARNESS_SESSION_DB` 换路径，显式设为空字符串则退回纯内存。

消息以 JSON 存在单列里而不是拆表：条数有上限（每会话最多 200 条）、总是整段读取，一次 UPSERT 更简单，也不会出现元数据与消息写到一半不一致。内存里保留一份副本作为读路径，所以**多 worker 部署会各读各的缓存** —— 当前是单进程 uvicorn，够用。

Docker 下 `var/` 挂在命名卷 `harness-var` 上，容器重建后历史仍在。

## 审计日志

每次 agent 启动、工具调用、批准/拒绝、结束都会追加一行 JSON 到 `var/audit.jsonl`，含 token 用量。写失败不会中断 Agent 主流程。

超过 `HARNESS_AUDIT_MAX_BYTES`（默认 5 MB）就轮转成 `audit.jsonl.1`，旧的依次后移，超出 `HARNESS_AUDIT_BACKUPS`（默认 3）的最老一份删掉。上限设 0 表示不轮转。

## Token 用量

每次回答下方会显示本次消耗和会话累计；`/api/sessions` 和 SSE 的 `done` 帧也带 `usage`。流式请求通过 `stream_options.include_usage` 拿上游上报的数字，个别网关不认这个字段时在 provider 的 `compat` 里设 `supportsStreamUsage: false`，此时只统计调用次数。

实测（`fastai/gpt-5.5`，30 个 skill）：

| 场景 | prompt | 总计 | LLM 调用 |
|---|---|---|---|
| 简单问答，不碰 skill | 12,375 | 12,412 | 1 |
| 触发一次 skill 阅读 | 25,353 | 25,752 | 2 |
| team 两步任务 | 72,647 | 73,237 | 7 |

固定开销的构成（约 10,100 字符 / 12,400 token）：

- skill 清单 **7,541 字符（75%）**
- 工具 schema 2,156 字符
- 基础指令 406 字符

也就是说 skill 全量注入是主要成本。要压的话，把 `context()` 里每条 description 截到 120 字符可省约 2,900 字符（≈3,500 token，降 28%），代价是模型判断该读哪个 skill 的依据变少。先看数字再决定，别凭感觉砍。

## 安全护栏

`HARNESS_REQUIRE_TOOL_CONFIRMATION` 默认为 `true`：`write_file`、`execute_python`、`browser_open` 这类破坏性工具执行前会在工作台弹确认框，批准才执行，拒绝或超时（5 分钟）按拒绝处理。

注意这个护栏只在流式接口 `/api/chat/stream` 上生效。非流式的 `/api/chat` 没有回传通道，需要确认的工具会被直接拒绝。

**MCP 入口**（`mcp_server.py`）是第三条路径，同样没有确认的回传通道。默认只暴露只读的
`list_files` / `read_file`；显式设 `HARNESS_MCP_ALLOW_WRITE=true` 才注册 `write_file` /
`execute_python`，且每次调用都会记审计。放不放开由部署者决定，代码不默认敞开。

**密钥不跨 provider 复用**：每个 provider 必须在 `config/models.json` 里自己配 `apiKey`。
曾经有过「provider 专属 key 为空就回落到全局 `LLM_API_KEY`」的兜底，已经去掉——那意味着
A 家的密钥会被当 Bearer 发给 B 家的 baseUrl，而 `/api/models` 还会把该 provider 标成可用，
界面上完全看不出来。

**上游响应体不会原样落盘**：网关返回的错误体会先截短到 200 字符、再抹掉疑似密钥
（`sk-` / `Bearer` / `AIza` 等形态）才进异常消息——这些文本会走两条路，SSE error 帧发到
浏览器、审计日志写进 `var/audit.jsonl`，而 one-api 系网关的错误体常常回显请求头。

教学版会直接启动本机 Python 和 Shell —— `safe_path` 只约束文件接口，**被执行的代码本身不受限制**，能读写整台机器。只适合本地学习，不要暴露到公网；需要真正隔离请走 Docker Compose 那条路径（internal 网络、`cap_drop: ALL`、内存/CPU/进程数上限）。

## 开发

```powershell
# 后端测试（local-harness 99 + sandbox-lite 21）
cd apps\local-harness; python -m pytest tests -q
cd apps\sandbox-lite;  python -m pytest tests -q

# 前端冒烟测试（jsdom 加载真实 index.html + app.js，跑完整 SSE 链路）
cd apps\local-harness; npm ci; npm test

# lint（规则集刻意很小，只拦运行时会炸的问题）
python -m ruff check apps tools scripts
```

后端测试依赖 `requirements-dev.txt`（含 `pytest-asyncio`，缺了会看到一堆
`PytestUnknownMarkWarning` 然后整片 failed）。MCP 入口的测试还需要
`requirements-mcp.txt`，否则 `test_mcp_server.py` 会被 `importorskip` 整个跳过。

前端没有构建步骤，`app.js` 是顶层脚本。加这层测试是因为踩过两次同类问题：`stream.append`（实际方法叫 `push`）和 `finalizeActivityGroup` 少传参数，分别让打字机和活动区整段失效，而 `readSse` 当时把 `onFrame` 一起包在「跳过非 JSON 心跳」的 catch 里，控制台一条错误都没有。现在 catch 只罩 `JSON.parse`，帧处理的异常会正常抛出。

### 前端第三方资产

marked / DOMPurify / highlight.js / lucide 放在 `app/static/vendor/`，随仓库提交，页面**不发任何外部请求**。只装 Python 依赖的人不需要 Node 也能正常用。

升级版本：改 `apps/local-harness/package.json` 的 `dependencies`，然后

```bash
npm install && npm run sync-vendor
```

把 `vendor/` 的变更一起提交。`vendor/MANIFEST.json` 记录每个文件的来源包和版本，前端测试会校验它与 `package.json` 一致、且 `index.html` 里没有外链。

顺带一提，改成本地加载后代码高亮才真正开始工作 —— 之前 unpkg 的 highlight.js 在部分网络环境下取不到，`window.hljs` 是 undefined，而 `renderMarkdownInto` 对此是静默降级的。

CI 定义在仓库根的 `.github/workflows/ci.yml`（仓库根是 `doubaoskills`，本项目是其子目录），跑上面这些检查，外加扫描 `config/models.json` 里的明文密钥。`services/` 还有约 59 处 lint 待治理，暂未纳入门禁。

## 推荐学习顺序

1. `docs/learning-roadmap.md`
2. `apps/sandbox-lite/server.py`
3. `apps/local-harness/app/agent.py`
4. `apps/local-harness/app/tools/registry.py`
5. `services/python-runtime/application/python_server.py`
6. `services/node-repl/server.js -> session-manager.js -> worker.js`
7. `infra/entrypoint.sh` 和 `infra/gem/`
8. `docs/protocols/mcp.md` 与 `packages/fastmcp/`
9. `skills/business/` 和 `skills/system/`
10. `services/hijack-proxy/`

## 来源与边界

本目录由 `E:\code\doubaoskills` 下的多个归档整理而来。来源、取舍和未纳入的重复副本记录在 `docs/SOURCE_MAP.md`。

`artifacts/linux-amd64/` 中的 `mcp_vm_server` 和 `vm_runtime_hook` 只有 ELF 二进制，完整生产构建链不在本目录中。生产部署还需要补充认证、网络隔离、资源限制、审计和进程回收策略。
