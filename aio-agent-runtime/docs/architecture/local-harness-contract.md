# Local Harness Contract

## 1. Scope / Trigger

本契约覆盖 `apps/local-harness`、`apps/sandbox-lite`、工作台 UI 和 Docker Compose 之间的本地执行闭环。

## 2. Signatures

### Harness API

```text
GET  /api/health
GET  /api/config
GET  /api/models
POST /api/chat
GET  /api/sessions
DELETE /api/sessions/{session_id}
GET  /api/files?path=.
GET  /api/files/content?path=...
GET  /api/files/download?path=...
GET  /api/skills
POST /api/skills/match
```

### Sandbox API

```text
GET  /v1/healthz
GET  /v1/files?path=.
GET  /v1/files/read?path=...
POST /v1/files/write      {"path": string, "content": string}
POST /v1/execute          {"code": string, "language": "python", "session_id": string?}
POST /v1/lint             {"code": string, "language": "python"}
```

## 3. Contracts

### Chat request

```json
{
  "message": "生成销售数据 CSV",
  "session_id": "optional-session-id",
  "mode": "single",
  "provider": "deepseek",
  "model": "deepseek-chat"
}
```

`mode` 只能是 `single` 或 `team`。`provider` / `model` 可选；省略时使用会话已绑定模型，再回退到 `config/models.json` 的 default。Harness 会把模型请求转换为工具调用，再把工具结果放回模型上下文。

### Models

- 模型目录：项目内 `config/models.json`（可选本机覆盖 `config/models.local.json`）。
- 与 pi 相同：`apiKey` 写在 **provider** 上，可为 `sk-` 字面量，或环境变量名，或 `!command`。
- `GET /api/models` 返回可切换列表及 `available`（是否已解析出非空密钥）。
- 工作台下拉切换为会话级；同一会话后续请求沿用绑定模型，直到再次切换。

### Environment

| Key | Default | Meaning |
|---|---|---|
| `HARNESS_MODEL` | empty | 默认 `provider/model`，覆盖 json default |
| `HARNESS_MODELS_JSON` | empty | 覆盖 models.json 路径 |
| （密钥） | — | 优先写在 `config/models.json` 的 `providers.*.apiKey`（pi 字面量写法） |
| `SANDBOX_URL` | `http://127.0.0.1:8081` | Sandbox 地址 |
| `HARNESS_TOKEN` | empty | 设置后保护 Harness API |
| `SANDBOX_TOKEN` | empty | 设置后保护 Sandbox API |

## 4. Validation & Error Matrix

| Case | Expected result |
|---|---|
| 空消息 | Harness 返回 422 |
| 未知工具 | Agent 记录 error event，不执行任意命令 |
| Sandbox 不可用 | Chat 返回可读错误，健康检查显示 unavailable |
| 路径越界 | Sandbox 返回 403 |
| 文件超过限制 | Sandbox 返回 413 |
| 模型工具循环超过上限 | 返回 trace id 和 error event |
| 未配置模型密钥 | `/api/models` 标记 unavailable；chat 返回 400 明确错误 |

## 5. Good / Base / Bad Cases

- Good：`列出文件` 只调用 `list_files`，返回 workspace 相对路径。
- Base：`生成销售数据 CSV` 依次调用 `write_file` 和 `execute_python`。
- Bad：模型要求读取 `../secret`，Sandbox 必须拒绝并把错误反馈给模型。

## 6. Tests Required

- `apps/sandbox-lite/tests/test_security.py`：路径边界、健康接口、写读闭环。
- `apps/local-harness/tests/test_agent.py`：脚本化模型工具循环、OpenAI schema 序列化。
- 集成检查：Sandbox 停止时 Harness 健康接口仍能返回 `sandbox.status=unavailable`。

## 7. Wrong vs Correct

### Wrong

```python
joined = os.path.normpath(os.path.join(root, path))
if not joined.startswith(root):
    raise PermissionError()
```

### Correct

```python
candidate = (root_path / path).resolve()
candidate.relative_to(root_path)
```

字符串前缀会把 `/workspace-other` 错误地当成 `/workspace` 子目录；必须比较规范化路径的真实相对关系。
