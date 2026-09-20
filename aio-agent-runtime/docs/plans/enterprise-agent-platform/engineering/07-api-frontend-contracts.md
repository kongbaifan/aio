# 07. API、事件、错误和前端状态工程契约

> 示例仅用于设计与契约测试。端点尚未实现；真实 OpenAPI 必须从实现生成并校验，不能以本文件代替服务器行为。

## 1. HTTP 通用约定

- 浏览器同源 BFF Cookie：Secure/HttpOnly/明确 SameSite；写请求另需 CSRF/Origin 验证。
- 内部 service API 使用工作负载身份；用户不可直接调用 manager/executor。
- ID 使用严格 UUID/受控 opaque ID，拒绝超长/非法路径，不因 ID 合法就授权。
- JSON 拒绝未知授权字段、重复 key、NaN/Infinity、过深结构；数据解析在资源查询前完成但错误不泄漏秘密。
- 初始建议：普通 JSON 请求 <= 1 MiB；message UTF-8 <= 64 KiB；input_artifact_ids <= 32；page_size 1–100。真实限额配置版本化并测边界。
- 分页 cursor 包含排序键/资源 scope，不接受任意 SQL order/filter；返回资源先授权再分页，不能先分页全局数据后在前端过滤。
- mutation 用 revision/If-Match 等一致约定；本方案 body.expected_revision 为主，不同时接受相互矛盾的版本条件。
- 错误携带 code/request_id/retryable 与获准 details，禁止原始 traceback、上游 Authorization、内部路径/SQL 回显。

## 2. 创建 Session 和 Run

### 2.1 Session

```http
POST /api/v2/sessions
Content-Type: application/json
X-CSRF-Token: <browser-session-csrf-value>
```

```json
{
  "project_id": "10000000-0000-4000-8000-000000000001",
  "agent_version_id": "20000000-0000-4000-8000-000000000001",
  "title": "销售表分析"
}
```

服务端建立 owner/org/id，不接受客户端指定。创建成功返回 201、revision、当前模板版本。V1 Session 固定 AgentVersion；需要换模板创建新 Session，避免悄悄改变旧对话授权和指令。允许的模型选择若可调整，作为下次 Run 的明确获权配置版本，不修改旧 Run。

### 2.2 Run

```http
POST /api/v2/sessions/{session_id}/runs
Idempotency-Key: <client-generated-high-entropy-operation-id>
Content-Type: application/json
X-CSRF-Token: <browser-session-csrf-value>
```

```json
{
  "message": "分析销售表并生成报告",
  "agent_version_id": "20000000-0000-4000-8000-000000000001",
  "expected_session_revision": 8,
  "input_artifact_ids": ["30000000-0000-4000-8000-000000000001"],
  "mode": "single"
}
```

- agent_version 与 Session 固定版本不一致返回 `SESSION_AGENT_MISMATCH`，不临时扩大能力。
- input refs 必须同 org 且用户获权、状态可读；不接受 path/baseUrl/credential/sandbox 参数。
- body.agent/system instructions 不作为平台权限；extra fields 要拒绝而非偷偷使用。
- 幂等键建议 16–128 字符的高熵值，范围为 actor/org/operation；同 key 异摘要 409。
- 重放同 key 先验证当前身份和资源权限，再返回原 Run；不能泄露已撤权内容。

响应：

```json
{
  "run_id": "40000000-0000-4000-8000-000000000001",
  "state": "queued",
  "session_revision": 9,
  "status_url": "/api/v2/runs/40000000-0000-4000-8000-000000000001",
  "events_url": "/api/v2/runs/40000000-0000-4000-8000-000000000001/events"
}
```

202 代表 TX-01 已成功提交，不表示模型/沙箱已经启动。UI 不因收到 202 就显示“任务完成”。

## 3. 查询、取消、重试和核对

`GET /runs/{id}` 返回当前 state/revision、获权结果引用、usage summary、可用操作和 cleanup summary。`available_actions` 是 UX 提示，执行按钮请求时仍重新授权。

```json
{
  "run_id": "40000000-0000-4000-8000-000000000001",
  "state": "recovery_required",
  "revision": 17,
  "reason_code": "EXTERNAL_OUTCOME_UNKNOWN",
  "result": null,
  "usage": {"status": "estimated", "currency": "USD", "amount": "0.013000"},
  "cleanup": {"state": "clean"},
  "available_actions": ["view", "request_reconciliation"]
}
```

- cancel 幂等，返回当前 `cancel_requested/cancelled/recovery_required`，不承诺外部业务已撤销。
- `POST /runs/{id}/retry` 只为允许安全重试创建新 Run，并记录 source_run_id；未知效果不接受普通 retry。
- reconcile 是限权核对接口，提交 evidence_ref/结论/版本，不提供任意 status PATCH。
- 任务终态与 cleanup 分开；清理失败需告警和容量保留，但已可靠保存的结果仍可按权限读取。

## 4. 审批请求和决定

获取审批内容须具备查看该动作摘要的权限，不能借审批查看整段私有 Session。

```json
{
  "approval_id": "50000000-0000-4000-8000-000000000001",
  "run_id": "40000000-0000-4000-8000-000000000001",
  "revision": 3,
  "action_digest": "example-action-digest",
  "state": "pending",
  "expires_at": "2030-01-01T00:00:00Z",
  "summary": {"system": "工单系统", "action": "创建工单", "max_affected_items": 1},
  "required_authentication_level": "step-up-if-policy-requires"
}
```

决定请求：

```json
{
  "expected_revision": 3,
  "action_digest": "example-action-digest",
  "decision": "approve",
  "reason": "业务范围已核对"
}
```

服务器根据当前登录身份确认批准者，不接受 `approved_by`。digest 不符合、版本冲突、已失效/过期分别给稳定错误，不能把重复请求变成新的批准。

业务摘要和 raw arguments 的可见字段各有范围；需要更强认证时服务端发受控 step-up 流程，不能让前端自报 auth_level=high。

## 5. 上传、预览、分享和下载

### 5.1 上传槽流程

1. `POST /projects/{id}/uploads`，传 filename/purpose/expected_size/media_type（都只是待验证声明）。
2. 返回 slot_id、size_limit、expiry 和限定上传方式，不返回全桶凭据。
3. 上传完成 `POST /uploads/{id}/complete`，服务端核验实际 size/hash、归属和状态。
4. 返回 artifact 或 document ingest ID，初始 quarantine/scanning，不可公开。
5. 只有服务端 ready 后 UI 才展示正常预览/下载。

同 slot 重复 complete 同内容返回原事实，内容变化拒绝；过期/其他用户 slot 不可完成。

### 5.2 下载与撤回

敏感资源使用授权代理，每次请求验证当前 ACL/来源；普通低敏产物可用短期签名 URL，但 UI 必须说明撤销后已发 URL 可能在短有效期内仍可用。下载域不承载平台 Cookie，Content-Disposition/Content-Type/nosniff/CSP 按文件类型设置。

HTML/SVG/Office 不能在平台同域获得脚本权限；markdown 经过 sanitizer，外链不带 Token/敏感 referrer。分享 API 不接受任意公开 URL，而是明确用户/组、动作和到期，并复核 derived_access_policy。

## 6. SSE 事件 envelope

```text
id: 40000000-0000-4000-8000-000000000001:42
event: tool.completed
data: {"schema_version":1,"run_id":"40000000-0000-4000-8000-000000000001","seq":42,"timestamp":"2030-01-01T00:00:00Z","payload":{"invocation_id":"uuid","state":"succeeded","result_ref":"authorized-result-ref"}}
```

- Event ID 是游标，不是授权票据；不能用另一个 Run 的 ID 读数据。
- `schema_version` 必须兼容；遇到未知重要事件类型以安全方式停/重取 snapshot，不能假装成功。
- `answer.delta` 只含新增文本块和 segment ID；完成事件指向已提交 answer/result，而不是每次携带全部全文。
- 最终成功用 `run.completed` 且 payload.state=succeeded；失败/取消/超时/待核对明确不同事件与状态。
- 不把模型隐藏推理当平台必须收集内容，保存可公开的回答、工具输入/结果摘要与事件即可。
- 心跳是 comment，不占业务 seq；重复投递允许，客户端按 run+seq 去重。

### 6.1 历史与实时切换不丢事件

推荐 PG 是事实，Redis/通知只用于唤醒：

1. 验证当前订阅权限和 after_seq/Last-Event-ID 一致。
2. 读取当前 high_water seq，按顺序发送获权历史 `(after, high_water]`。
3. 继续从最后实际发送的 seq 查询更大事件；订阅通知加速，但始终定期查询 PG。
4. 通知注册/历史读取之间即使发生事件，也会被下一次 `seq > last_sent` 查到。
5. 序号未到达不能在客户端自行跳过；游标过期返回 snapshot 流程，不从最初 prompt 重跑。

权限撤销导致某内容不可再见时，返回获权的 redacted/unavailable 事件或拒绝该视图，保留必要游标连续性而不泄漏源标题/正文。不能重放历史敏感正文只因当时有权限。

### 6.2 慢消费者和资源上限

每订阅限制缓冲 bytes/event 数、每用户订阅数、连接 idle/max age。超过上限断开并提示回放；不能让一个慢浏览器阻塞 Worker 或把全部日志复制到 API 内存。

## 7. 统一错误码与用户操作

| HTTP / code | 原因 | UI 行为 | 可重试条件 |
|---|---|---|---|
| 401 AUTH_REQUIRED | 会话无效/过期 | 登录后重取当前视图 | 不自动新建 Run |
| 403 POLICY_DENIED | 已知范围内动作不允许 | 解释可申请权限 | 权限变化后重新请求 |
| 404 RESOURCE_NOT_FOUND | 不存在或不可见敏感资源 | 不泄露标题/owner | 不枚举其他 ID |
| 409 IDEMPOTENCY_CONFLICT | 同 key 异请求 | 停止自动重传 | 用户明确新动作使用新 key |
| 409 SESSION_BUSY/PROJECT_BLOCKED | 未解决 Run/写租约/未知业务影响 | 展示获权占用/处理方式 | 解占用或核对完成 |
| 409 REVISION_CONFLICT | 对象被修改 | 重取获权状态 | 用户确认后提交新 revision |
| 409 ACTION_CHANGED | 审批内容改变 | 旧审批失效 | 新动作重新审批 |
| 410 APPROVAL_EXPIRED | 审批超期 | 展示已过期 | 根据 Run/策略申请新审批 |
| 410 EVENT_CURSOR_EXPIRED | 历史已归档 | 获取授权 snapshot | 不重跑任务 |
| 413 PAYLOAD_TOO_LARGE | 请求/文件/输出超限 | 说明限额 | 缩小输入后新请求 |
| 422 INVALID_REQUEST | schema/格式错误 | 字段级提示 | 修正输入 |
| 429 QUOTA_EXCEEDED | 预算/并发/频率限制 | 显示 scope 与允许重试提示 | 额度/队列变化 |
| 503 EXECUTION_UNAVAILABLE | manager/profile 不能安全执行 | 排队/失败说明 | 不回退宿主运行 |
| 503 POLICY_STATE_UNAVAILABLE | 无法取得当前权限/必要审计 | 暂停敏感动作 | 安全服务恢复 |

`OUTCOME_UNKNOWN` 主要是 Run/Invocation 状态，不简单当可重试 503。raw provider body 不进入普通 error.details。

## 8. 前端状态归属和迟到响应

- 全局只保留当前认证视图与非敏感 UI 偏好；资源缓存以 actor/org/scope 分区。
- 每次登录/退出/切 org 增加 client_context_epoch，并 abort 旧请求/订阅；收到响应时比对发起时 epoch，旧用户迟到响应丢弃。
- 切 Project/Session 也用 view epoch 防旧结果覆盖新页面；不能只在请求发出前检查当前用户。
- localStorage 不存 Secret、长期登录 Token、敏感 prompt/正文；可保存非敏感偏好，恢复游标仍绑定当前获权 Run。
- Request abort 仅停止浏览器读取，不自动 cancel Run；UI 区分“断线”和“任务取消”。

### 8.1 页面状态表

| 服务端状态 | 主操作 | 禁止的 UX 推断 |
|---|---|---|
| queued | 查看排队、取消 | 提交成功=完成 |
| running | 查看轨迹、停止 | 文本流结束=所有产物已保存 |
| waiting_approval | 获权人决定/查看期限 | 弹窗关闭=批准 |
| persisting | 等待保存、查看进度 | 提前给候选下载链接 |
| cancel_requested | 停止处理中 | 点击后立刻显示业务已撤销 |
| recovery_required | 申请核对、查看获权影响 | 提供普通一键重试外部写 |
| succeeded | 读回答/ready 产物 | 清理失败也当资源已回收 |
| failed/cancelled/timed_out | 说明原因、符合策略才新建任务 | 复用旧审批或自动重发 |

## 9. 契约测试交付物

- 有效/无效请求样例：字段边界、额外授权字段、重复 JSON key、非法数字、超长 ID、旧 revision。
- 事件 golden stream：文本块、工具、审批、产物、usage unknown、失败、取消和缺口恢复。
- 两浏览器主体夹具与请求 epoch 竞争测试。
- 原 UITEST、AUTH/RUNTEST，加 ECASE-18/19/38/39/40 等差量。
- 真实实现后生成 OpenAPI/TS 类型，CI 检查 spec drift；不能只手写前端接口并忽略服务端差异。
