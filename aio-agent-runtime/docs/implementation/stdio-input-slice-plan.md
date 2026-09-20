# stdio 当前 Run 附件导入：实施计划与边界

> 状态：本切片已实现并完成下述本机验证；完整企业平台目标仍 active。基线为 v11 stdio，当前仍是 58 张表、81 条 API 路径。本增量只解决 MCP-05.02 的明确 Run 附件输入，不扩展联网或生产 Gate。

## 1. 必须保持的不变量

- 两层显式允许：操作员固定模板 `input_policy=run_attachments`，使用者在本次 Run 提交 `allow_stdio_attachments=true`（默认 false）。连接或模板原有权限不能自动扩展成文件访问。
- 只复制 `Run.input.input_artifact_ids` 明确列出的当前获权、同项目、已发布的不可变附件；不读取隐式 Project head、计算中 workspace、HOME、宿主目录或任意 URL。
- 最多 32 个附件、原始字节合计 4 MiB；profile 必须为其保留至少 8 MiB 私有 workspace。超限明确失败，不静默裁剪。
- 原文件路径仅作为元数据；容器目标固定为 `attachments/<artifact UUID>`，清单固定为 `/workspace/attachments/manifest.json`，不由用户命令指定宿主路径。
- 原始字节经 BlobStore 完整性检查、再经 Gateway 受控转交、Manager 全量摘要/大小/清单校验；不在控制进程解压、解析或执行文档。
- PG stdio 租约与 Manager journal 只保留有界元数据/摘要，不复制附件正文。凭据仍只经 exec stdin，业务结果仍在 Gateway 加密。
- 只在首次进程启动前复制输入；同代次后续调用不得把初始附件重新覆盖到有状态 workspace。撤权、已取消/过期、旧代次、错误节点、失联进程继续失败关闭。
- 副本不等于只读业务文件系统：MCP 可改变其私有副本，但不能修改原附件，也不能将其 scratch workspace 提交成 project head。本增量不导出 stdio 文件。

## 2. 接口与兼容策略

1. `RunCreate.allow_stdio_attachments: bool = false`，连同附件 ID 固定在原有幂等请求和 Run input 中；丢失响应重试不可更改这个授权。
2. 无输入 profile 保持旧 template digest 和 `StdioSpec.schema_version=1`；新增 `StdioInputSpec.schema_version=2` 包含有界 `input_manifest`，独立摘要域 `aio-stdio-spec-v2`。不改 v1 迁移/摘要语义。
3. `/internal/v1/connectors/stdio` 增加 `inputs` 操作（无新增公开文件下载入口）；只对同一当前调用的固定 Spec/身份/Run/代次返回 bytes，前后重新授权。
4. `prepare` 只返回 Spec/是否首次需要输入；`inputs` 响应才短暂携带 base64 文件。普通控制响应仍有小上限，输入响应独立限制在 6 MiB。
5. `/v1/stdio/open` 额外接收 `input_files`；它们不进入 authority/journal 请求，只与固定清单核验。全部验证之后才能分配/启动 MCP。
6. 现有 v11 JSONB Spec 保存 v2，无新增表；API/Worker/Gateway/Manager 必须协调升级。浏览器显示独立授权复选框与明确限制。

## 3. 实施顺序与验收

- [x] Manager：profile opt-in、v1/v2 解码、元数据/字节验证、启动前有界复制、不重复覆盖；保持 compute/parser 复制行为和配额。
- [x] API/平台：冻结本次授权，按 Run 精确授权/固定清单，事务外读不可变 bytes，再验权；引用撤回沿用原 Run/Artifact provenance。
- [x] Gateway：首开短暂转交附件、有界输入响应、实例复用无二次注入、不落明文文件缓存。
- [x] Web：默认不允许，清楚展示读取范围，提交/重试固定授权，换会话复位；生成请求类型同步。
- [x] 真实 Docker：成功读取、同进程状态保留、原文不入 journal、跨用户/Run不可见、错误 hash/路径/总额/未批准 profile 在执行前拒绝、清理实际副本。
- [x] 真实 PG/Worker：未同意零文件、只允许选中附件、非所选/跨用户/被撤回附件拒绝、正文损坏不执行、4 MiB 边界通过/多 1 byte 拒绝，失败后清理状态准确。
- [x] HTTP 合成业务旅程：显式勾选后的附件读取；不将测试模型/参考 MCP 当作公司接入或浏览器视觉证据。
- [x] 完整本机回归、镜像/契约再生成、文档与证据同步；原父任务/生产 Gate 不整体勾选。

验证：平台 370、Manager 64、Gateway 82、parser 16、Web 62 项均通过且无跳过；HTTP 175 项检查通过，其中包含两用户附件传入和未同意的拒绝路径。旧 Harness/Sandbox/前端回归分别 142/24/45；具体证据和明确差额见 [实施状态](README.md) 与 [输入契约](../engineering/platform-mcp-stdio-input-contract.md)。这些数字是整套本机回归，不是本切片新增用例数，更不是全部 Docker 或生产 Gate。

## 4. 本轮不包含

受控网络出口、安装第三方依赖、任意语言镜像、MCP 二进制结果导入、真实业务写、从运行中的 compute workspace 共享文件、进程内存恢复、跨节点对象后端、专业 malware/DLP 和真实浏览器/公司 UAT。
