# MCP stdio 显式附件输入契约

## 1. Scope / Trigger

适用于 `app/connections/stdio{,_inputs,_settings}.py`、Run 创建、Gateway stdio 委派、Manager `stdio_inputs.py` 和工作台附件授权。基础隔离/节点 claim/停止事实仍服从 [stdio 契约](platform-mcp-stdio-contract.md)。附件输入本身没有新增迁移，也没有把输入正文加到表中；当前应用迁移为 `0013_shared_budgets`。

**两层 opt-in 缺一不可**：操作员批准固定模板 `input_policy=run_attachments`，使用者在本次 Run 中提交 `allow_stdio_attachments=true`。默认模板/默认 Run 均不传附件。只允许该 Run 的 `input_artifact_ids`，不隐式读取 Project head、计算中的 workspace、历史文件、HOME 或服务器目录。

当前最多 **32 个文件、原始字节合计 4 MiB**；批准的输入 profile 必须预留至少 8 MiB workspace，给副本之外的临时工作保留空间。超限明确拒绝，不静默截取原文件。

## 2. Signatures / Versioned contracts

```text
StdioProfile.input_policy: Literal["none", "run_attachments"] = "none"
RunCreate.allow_stdio_attachments: strict bool = false

StdioSpec (v1): unchanged no-input spec and aio-stdio-spec-v1 digest
StdioInputSpec (v2): base scope + input_manifest[], aio-stdio-spec-v2 digest
input_manifest[] = {
  artifact_id: canonical UUID,
  source_path: original relative name (metadata only),
  path: "attachments/" + artifact_id,
  sha256: lowercase SHA-256,
  bytes: nonnegative integer
}

POST /internal/v1/connectors/stdio
  prepare: {context: {operation, payload}} -> {allowed, spec, needs_inputs}
  inputs: {context: {operation: "call", payload}, spec} -> {allowed, input_files[]}
  cleanup: existing cleanup scope -> {allowed, specs[]}

POST /v1/stdio/open
  {spec, context, credential, input_files?: [{path, sha256, content_b64}]}
  -> ready receipt (no input bodies)
```

`inputs` 不是公开文件下载 API，也不是客户端任意 path/ID 查询：必须是当前业务调用、原 binding、同 Run/代次、精确已落盘 Spec，且 lease 仍为 preparing。发现没有业务附件，即使模板允许输入也得到空清单。

普通 stdio 控制响应保持 64 KiB 上限；只有私有 `inputs` 响应放宽到 6 MiB，覆盖 4 MiB 的 base64 与有界元数据。Manager 请求仍有既有总字节边界，并限制 input_files 数量与累计编码字节；逐文件还需通过 raw size/hash 校验。

## 3. Authorization / Data flow / Persistence

1. Run 创建先验证附件当前 read 权限、同项目与去重，保存附件 ID 和严格布尔授权；这个授权是幂等请求的一部分，不能在重试时更换。
2. `prepare` 在当前 Run/dispatch 锁与授权下，只读取显式附件的元数据，固定 v2 Spec。没有用户同意时是空清单，不借用已有 workspace。
3. `inputs` 比较原 Spec 和当前允许的完整清单。事务外从既有 BlobStore 读取原始 bytes 并核对 SHA/长度，然后再次检查当前权限/Run/lease/清单，才把 bytes 返回 Gateway。
4. Gateway 仅在首次 preparing 初始化需要时短暂转交 bytes；没有控制端允许时不能自行指定要读哪些附件。后续 ready 进程不再拉取/注入初始文件。
5. Manager 在创建 cell 前检查**所有**清单、目标路径、数量、大小、base64 和 SHA。镜像 Entrypoint 必须为空，避免批准的 watchdog 之前有隐式进程启动。
6. Manager 生成自己的普通文件 tar，把经过单独验证的 raw bytes 写入新 cell 的私有工作卷；这不是在宿主解压用户 ZIP/TAR 或解析文档。代码尚未启动，因此没有用户 symlink 与复制并发的窗口。
7. 原文固定放在 `/workspace/attachments/<artifact UUID>`；清单在 `/workspace/attachments/manifest.json`。`source_path` 只说明原名称，绝不作为宿主或容器目标路径执行。
8. 复制后、启动与 RPC 前仍走当前 authority；撤权/取消/丢 lease 后停止新动作并回收 cell。已交付给进程/模型的内容无法“倒退未读”，不承诺远程擦除。

PG stdio lease 与 Manager journal 只保留有界清单/摘要。`StdioOpen.authority()` 排除 credential 和 input_files，不把正文附到控制回调/操作日志。Gateway 没有新增明文附件缓存；工具已返回的已知业务结果仍按原契约加密。原附件的来源、当前权限、后续 Run/Artifact 撤回规则不变。

**副本不冒充只读文件系统**：MCP 可改变其私有副本；同代次后续调用看到的是该进程自己的状态。再次 open 携带 input_files 时拒绝重新注入，不覆盖已工作的文件。它不能修改 BlobStore 原件，也没有把 stdio workspace 发布到 Project head 的入口。审批/代次变更结束旧进程，只有新代次明确获权的原始附件可以重新复制，不恢复 MCP scratch 或内存。

## 4. Deployment / Browser contract

在固定 Manager profile 中显式加入：

```json
{"input_policy": "run_attachments"}
```

这只是既有完整固定 profile 的增量字段，不是独立可运行模板。使用 `scripts/platform/export_stdio_endpoint.py` 重新导出 BFF/Gateway 的 template/endpoint 引用；模板 opt-in 改变摘要，需要重新登记/审核相应版本，不能静默扩展旧连接的文件权限。新参考 profile 会显式启用这一能力，但 Run 默认仍关闭。

默认 `input_policy=none` 的旧模板维持原 template digest，v1 Spec 继续按原字段/摘要读取；v2 使用独立摘要域，JSONB 租约可保存，无新增迁移。排空旧 Worker 并协调升级 API/Gateway/Manager，不声称旧读取器认识新 Spec 或任意滚动升级都已验证。

工作台仅在带附件的 MCP 任务显示独立复选框：**允许隔离 MCP 读取本次所选附件**。默认不选；改动所选文件、切换会话、成功提交后复位。丢失提交回复时锁定原附件 ID、授权值和幂等键；不能通过“重试同一提交”扩大授权。合计超过 4 MiB 时不能勾选，但仍可在原有附件/compute 额度内使用其他能力。

此能力不承诺阻止已获得 Token 和附件的第三方代码滥用其获授能力；无网络、固定镜像审核和清理是当前约束，不是通用 DLP。

## 5. Validation & Error Matrix

| 情况 | 结果 / 不变量 |
|---|---|
| 模板未 opt-in，或 Run 未明确同意 | 零附件；不能因为 Agent 有 MCP 工具就自动分享文件 |
| Run 授权为字符串/数字/null | 422，不作 truthy 转换 |
| >32 文件或 >4 MiB raw bytes | `STDIO_INPUT_QUOTA_EXCEEDED` / 契约拒绝；不创建输入执行 intent/cell，不静默裁剪 |
| 缺私有存储 | `STDIO_INPUT_STORAGE_UNAVAILABLE`；无宿主目录 fallback |
| 未选中、另一 Run/用户/项目、元数据变更 | scope/spec/当前资源拒绝；不会返回新增文件正文 |
| 撤权或 bytes 损坏 | 原 BlobStore/authority 拒绝；未开始业务 MCP 进程 |
| Manager missing/extra/duplicate files | `STDIO_INPUT_MANIFEST_MISMATCH`，分配前拒绝 |
| 不正确 hash/长度/编码 | `INPUT_INVALID` / `STDIO_INPUT_INTEGRITY_ERROR`，分配前拒绝 |
| active session 被要求重导入 | `STDIO_INPUT_REINJECTION_DENIED`；原进程副本不被覆盖 |
| 镜像携带隐式 Entrypoint | `STDIO_IMAGE_ENTRYPOINT_DENIED`，不使用它替换 watchdog |
| inputs 响应 >6 MiB，其他控制响应 >64 KiB | 有界失败，不继续派发 |
| Run 完成/旧 generation/Manager 丢失 | 不能通过 stdio inputs 私口重新下载或重建原进程；正常 Artifact 下载仍按原当前权限规则 |

## 6. Good / Base / Bad + Assertion points

- Good：Alice 明确选择 A 并同意；同项目的 B 没有出现在清单里。真实 MCP 读到 A 的 hash/内容，原件不变；Bob 的 cell 没有 A。
- Base：只批准模板但没勾选，或只勾选但模板未批准，都没有输入。发现时同样零业务文件。
- Bad：从整个 project head 自动加载；挂宿主目录；把 user filename 用作解压目的地；把 input_files 存进 spec/journal；每次 tools/call 都重新覆盖初始文件。

测试入口：

- Manager `test_stdio_contracts.py`：v1 digest 保持、v2 解码、非规范/重复/越界 metadata、编码/hash、短暂 payload 不进 authority。
- Manager `test_stdio.py`：真实官方 SDK/Docker 的文件读取、同进程修改后复用、跨 Run 不可见、无明文 journal、分配前拒绝和实际销毁。
- 平台 `test_stdio_input_pipeline.py`：真实 PG/Gateway/Manager，双 opt-in、只选中附件、伪造清单/后续下载拒绝、当前权限再校验、损坏 bytes、4 MiB 边界与超限不截断，以及清理状态。
- Gateway `test_stdio_boundary.py`：首开一次转交、后续不重新传原文、严格 metadata 与独立响应上限；不冒充真实网络测试。
- Web `workbench.test.tsx`：默认关闭、修改附件复位、可访问 label/说明、丢回复时同一授权/幂等重试。
- `test_workbench.py`：两个合成 SSO 用户通过真实 HTTP 上传/授权/执行/原件下载，以及不勾选时零文件；它不是浏览器视觉或公司真实接入证明。

## 7. Wrong vs Correct / Remaining

```text
Wrong: tool has filesystem access -> mount every user's company workspace
Correct: approved image policy AND immutable per-Run consent -> exact selected, authorized, checked copies

Wrong: stdio open retry -> rewrite attachments to recover the old process state
Correct: ready session keeps its private state; lost session is not silently restarted/replayed

Wrong: put base64 documents into StdioSpec so a later Manager can restore everything
Correct: versioned metadata-only Spec + bounded transient first-open transfer; no process/scratch restoration claim
```

仍未交付：从活动 compute workspace 协作、stdio 二进制产物导出、受控联网/依赖安装、其他语言/供应商镜像的差量 Gate、跨节点存储/HA、专业扫描/DLP、真实浏览器和公司 UAT。本增量不将 MCP-05、原 110 父任务或完整企业平台整体标完成。
