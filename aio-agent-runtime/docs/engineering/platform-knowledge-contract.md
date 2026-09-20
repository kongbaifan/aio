# 知识库、隔离摄取、检索与引用契约

> 代码：`app/knowledge/`、`services/document-parser/`、`web/platform/src/features/Knowledge.tsx`。知识能力由 `0007_knowledge` 引入，当前应用迁移为 `0013_shared_budgets`；要求操作员安装 pgvector。此文只描述已实现路径，不替代完整 KB/生产 Gate。

## 1. 资源与身份边界

- KnowledgeBase 是 `knowledge` 资源；read/search/update 分开授权，不提供管理员通读私人资料的旁路。
- Document 是独立 `document` 资源。默认 `restricted`；只有显式改为 `inherited` 才沿用知识库搜索权限。给别人 KB 权限不会自动公开受限文档。
- 当前文档权限、组织状态、部门 membership、资源 status/classification 每次重新读取。知道 version/chunk/citation UUID 或 blob hash 不等于能读取正文。
- 上传者必须有 KB.update 和文档管理权；原始对象按 org+hash 存储，不能自行选择宿主路径。
- Agent 固定 KB 工具定义；Run 另外冻结当时可读取的文档版本 ID 上限。新文件或新权限不会静默扩展已经开始的任务。

## 2. 可执行接口

```text
POST /api/v2/knowledge
  KnowledgeCreate{name,description,parser_profile,embedding_model_id?}
POST /api/v2/knowledge/{id}/documents
  DocumentCreate{title,filename,max_bytes,visibility,document_id?,expected_revision?}
PUT /api/v2/knowledge/uploads/{version_id}/content
  application/octet-stream -> immutable source + queued ingestion
PATCH /api/v2/knowledge/documents/{id}/visibility
  {expected_revision,visibility:restricted|inherited}
DELETE /api/v2/knowledge/documents/{id}
  {expected_revision} -> access revoked before physical cleanup
POST /api/v2/knowledge/{id}/search
  {query,request_id,limit} -> explicit lexical preview (no model request)
GET /api/v2/knowledge/citations/{citation_id}
  -> current-authorized fixed version/text/location/download URL
GET /api/v2/knowledge/versions/{version_id}/download -> attachment only
POST /api/v2/admin/embedding-models -> approved fixed model/dimension/prices/secret NAME
POST /api/v2/admin/embedding-calls/{id}/reconcile -> append-only usage evidence
```

浏览器所有写请求均有 BFF 身份、Origin/CSRF 和大小校验。请求类型由真实 OpenAPI 生成，原文/格式/路径等仍由服务器验证。

## 3. 上传、版本和配额

1. 创建版本/上传票据，锁组织配额；同时预留原文件和最坏索引空间，不先写盘再检查额度。
2. 字节请求将不可变 hash/size 与 writing 状态落盘，再写组织范围 BlobStore。重试同一版本不能换字节。
3. 上传确认与 Job 创建同事务。另一个上传尝试已经提交并开始解析时，相同字节的重试不会创建第二个 Job。
4. 当前版本在候选索引完成前保持可用；新版本成功时原子切换 active pointer，旧引用不改指向不同的新内容。
5. 总量包含原文、候选索引和 parser spec 的临时保留数据；文档配额与 Artifact/Upload/Workspace 共享组织存储上限。

当前原文最大8 MiB；单 KB 最多256个文档、每文档最多30个版本；块数/长度与解析器有界。更大规模、归档与保留策略需独立评估，不能扩大到无限再声称安全。

## 4. 隔离摄取状态与授权

```text
Version: uploading -> queued -> parsing -> indexing -> ready / failed / deleted
Job: queued -> leased -> ready / failed / cleanup_pending / recovery_required
Phase: parse -> embed -> publish
```

- Worker 领取 PG lease/generation；先提交固定 spec/dispatch，再向 Manager 发请求。target_slot=`knowledge/ingestion`，不伪造业务 Run。
- Manager 回调现有私有 `/internal/v1/sandbox/authorize`，验证整个 spec、源版本、当前请求人/权限、当前 parser profile、generation、lease、deadline 和固定命令。
- 解析器只见该文件及固定 manifest，没有公司业务网、模型 key、用户 HOME 或控制服务文件系统。
- `parsed-document.json` 仍作为不可信输出校验；只有确认外部 writer 停止才写候选 chunks。完整索引发布前仍重新授权，不公开半份索引。
- Manager acknowledge 只在退休 cell 和平台已确认清理后允许，删除原始 spec/导出/命令 payload，保留必要绑定/去重事实。
- Worker 丢失时先清理旧 cell；已确认 parser checkpoint 可以继续后续阶段；已派发结果不明的 embedding 不自动重复请求。
- 手工安全重试刷新 queued_at，而不是篡改创建时间或使用过期的首次排队 TTL。迟到的 heartbeat 错误不能把已提交 ready 索引倒退成 failed。

格式及具体边界见 [解析器说明](../../services/document-parser/README.md)。不执行宏/公式/外链，不是专业杀毒；扫描图片 PDF 无 OCR。

## 5. 检索与内容权限

- 文档解析在独立 cell；索引与检索在可信服务做有界文本/向量操作，没有宿主文档解析 fallback。
- 中文关键词使用确定的字/二元词和英文词，GIN 索引；展示/引用文本不做 NFKC 重写。
- 可选混合检索使用 pgvector cosine + lexical 的 RRF 融合。当前先做组织、KB、文档权限、ready/active version 及 Run 快照交集，再计算/读取候选。
- 使用有界、获权集合上的精确向量查询；不假设全局 ANN 后过滤一定能提供足够获权结果。大规模 HNSW/性能 Gate 尚未交付。
- 不跨权限缓存答案。重复查询意图只复用自己的持久结果，并重新检查每个引用的当前权限。
- 浏览器检索预览明确为 lexical，不调用嵌入服务；Agent 的 hybrid 查询只在 Worker 执行。混合查询没有合法向量时明确失败，不静默降级来掩盖模型错误。
- 返回片段是资料，不是 system policy。没有结果明确 answerable=false，不生成“假引用”。

## 6. 嵌入外发与费用

- 嵌入模型需要操作员允许的 origin/Secret 变量名、固定模型/维度/价格/每次上限。API只配置名字，实际密钥仅由 Worker 解析，不进入 parser/compute。
- 注册 hybrid KB 意味着明确允许授权片段外发给该模型；UI另提示用途/费用。真实公司数据政策仍须公司批准。
- 每批请求先持久化意图、输入 digest 与预算预留，再跨网络。响应必须满足字节/索引/维度/有限非零向量、usage 和价格上限；拒绝 redirect 与压缩响应，不回显供应商原始错误。
- 摄取与 Run 查询共享个人预算。Run 内 embedding 占用同一 Run reservation，不会绕过模型调用上限；其他摄取请求独立预留再结算。
- v13 同时维护固定组织 / 部门计费投影与已配置共享上限，未发送退款、unknown hold 和不同责任人核对必须同事务更新；Run 内 embedding 不重复分配独立 hold。浏览器查询依旧明确 lexical，内部独立 embedding 意图也必须受限，见 [共享预算契约](platform-shared-budget-contract.md)。
- usage 缺失不是零费用，保留上限并允许已确认的向量使用。响应丢失则结果/费用 unknown，不盲目再次计费。
- usage 核对需不同管理员提供依据，追加 ledger；重复同一证据不会再次扣款。费用确认不意味着遗失的向量已经找回，不能因此自动发布索引。

## 7. 引用、历史和删除

- Citation 是服务端记录的 query/chunk/version 映射，不从模型文字构造原文 URL。UI展示的证据列表来自 Run.result.citations。
- `knowledge_source_refs` 传播到 Run、历史 checkpoint、Workspace 和 Artifact。撤权/版本替换/删除影响后续模型、事件回放和产物读取。
- 删除先禁资源访问、清 active pointer、标记版本，再等待 parser 清理及 acknowledge。旧 Job 不得重新发布已删除内容。
- GC 清 chunks/向量/citation，并清理相关查询结果/派生 query vector；计费与审计事实不伪装删除。
- 只有持组织存储锁、确认其他知识版本/Artifact/上传/待发布 workspace 都不引用 hash 时才删原始 blob。删除中断可重试，不跨壳或根据用户路径递归删除。
- 已披露给模型、已下载到客户端、第三方备份/供应商留存无法通过平台删除收回；不做这种保证。

## 8. 错误与测试矩阵

| 场景 | 结果与保护 |
|---|---|
| 缺认证/CSRF/资源权限 | 401/403/404，正文不进入模型 |
| 上传变更字节/错误版本 revision | 409，不覆盖已绑定对象 |
| 宏、实体、归档越界/膨胀、无文本 | 明确解析错误，隔离 cell 清理，索引不可见 |
| parser 失联/lease过期/删除竞争 | cleanup_pending/failed，不重用未确认写者 |
| 嵌入模型维度/usage异常、响应断开 | 不发布错误向量；未知费用保留，不自动重试 |
| 私有文档藏在共享 KB 内 | 查询前过滤，不先给模型再删片段 |
| 替换版本/撤权后的旧引用 | 不可用，而非悄悄指向新文档 |
| 分享派生文件 | 不洗掉来源权限约束 |

单元/PG：`test_embedding_contracts.py`、`test_knowledge_integration.py`。实际 Linux Docker：`test_knowledge_pipeline.py` 覆盖六种格式和活动内容拒绝。Web：`knowledge.test.tsx`。有限时长 HTTP preview 覆盖实际解析、混合检索、文档权限、引用和删除。模型/身份/业务内容为合成测试数据，不能代替真实公司接入与 UAT。

**错误**：API里解压DOCX、读到全库后再过滤、把model文本URL当引用、没usage就算免费。  
**正确**：独立parser -> 当前ACL的候选索引 -> Worker有预算外发 -> 当前权限精确检索 -> 服务端引用 -> 撤权/删除传播。

## 9. 升级与剩余范围

升级需要已安装 pgvector 的 PostgreSQL 17；本机验证镜像固定为 `pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`。生产先备份/排空旧 API/Worker，再迁移 v7、刷新 runtime grants、配置 parser image/profile 后启动；旧读取器不认识新来源字段，不能混跑。

待完成：OCR/更多格式/文档视觉预览、外部数据源增量摄取与 ACL 同步、用户批量迁移、专业扫描/DLP、token级上下文预算、更多嵌入供应商和完整对账、ANN/大规模质量与性能门禁、跨节点存储/备份恢复/HA、真实浏览器及公司 UAT、安全生产 Gate。
