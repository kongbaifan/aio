# 05. Skill、MCP、知识库、模型与引擎接入计划

> 工程层补充：实现时同时阅读 [工程契约索引](engineering/README.md)。其中明确了多权限 cell、RLS 威胁边界、事务锁序、审批与未知效果、当前撤权和可信资源核对；不把本页架构概览当作已实现保证。

> 能力共享与执行隔离并不矛盾。本文件定义“共享什么、以谁的身份调用、在哪里执行、如何发布和撤销”。

## 1. 统一能力模型，而不是把所有东西都叫工具

| 类型 | 本质 | 向模型提供的形式 | 安全执行边界 |
|---|---|---|---|
| AgentTemplate | 模型/指令/可用能力的组合配置 | 固定版本系统上下文 | 不能扩大组织策略 |
| Skill | 指令、资源、脚本、依赖与使用约束的版本包 | 按需读取说明；可选 typed entrypoint | 脚本在 Run 沙箱；说明本身不授予权限 |
| MCP | 标准工具/资源协议连接 | 经过裁剪和命名映射的工具 schema | 远程服务自身授权；stdio 进隔离单元 |
| KnowledgeBase | 有权限的数据集合及检索服务 | knowledge_search/read_citation 等受控工具 | 检索、引用、下载、派生上下文统一 ACL |
| BuiltinTool | 平台文件/计算/浏览器等基础能力 | 固定 schema 和 handler | ToolGateway + 对应 Run 执行器 |

Tool Manifest 不是把全公司所有 Skill 和 KB 全量塞进上下文，而是为当前 Run 生成必要、获权、有版本的能力集合。

建议 Manifest 保存：工具 alias→真实能力版本映射、schema_digest、风险级别、资源上限、连接 scope、输出限制、数据分类、依赖关系与失效策略。模型只见业务 schema，不见 SecretRef、内网管理地址或原始数据库连接。

### 1.1 解析顺序

1. 当前用户/项目可访问资源集合。
2. 组织/部门数据与风险约束。
3. 选定 AgentVersion 的能力上限。
4. 能力发布/健康/禁用状态。
5. 依赖是否完整、模型工具 schema 是否兼容。
6. 固定 ManifestSnapshot，并记录版本摘要。
7. 每次实际执行仍由 ToolGateway 做当前权限检查。

能力数量过多时使用授权目录分页/搜索和按需加载，不以“关键词没匹配到”作为授权判定。工具 alias 需要符合实际模型/协议命名约束、避免冲突与保留名；不能让两个部门同名工具映射到错误连接。

## 2. Skill 生命周期

### 2.1 包结构建议

```text
skill-package/
  SKILL.md
  manifest.yaml
  references/
  scripts/
  assets/
  tests/
  dependency-locks/
```

`manifest.yaml` 建议字段：

```yaml
schema_version: 1
name: sales-analysis
version: 1.0.0
kind: instruction-with-entrypoints
runtime_profile: standard
runtime_image_ref: approved-image-digest
entrypoints:
  - id: analyze
    language: python
    path: scripts/analyze.py
    input_schema_ref: schemas/analyze-input.json
required_capabilities:
  - workspace_read
  - workspace_write
network_profile: none
requested_data_classification: internal
output_policy:
  allowed_types: [xlsx, csv, pdf]
  max_files: 20
```

示例中的声明只是申请，不是授权。EntryPoint、依赖、镜像、文件 digest 在发布时核实，执行时由平台构造，不能由模型传入其他脚本路径。

### 2.2 状态机

`draft → uploaded → scanning → testable → review_pending → published → deprecated/disabled`

- 上传后不在管理服务 import、安装或执行包。
- scan 包括 Secret、路径、大小、解压、依赖、许可证、恶意行为信号；扫描通过不代表绝对安全。
- 测试使用独立 Run、合成/授权样本和最小出网配置。
- 维护者只能申请所需工具、网络和凭据，不能自己授予新权限。
- 发布版本不可修改；变更脚本、引用、锁文件均产生新版本。
- 同一 Skill 可同时保留多个版本；AgentVersion/Run 固定引用。
- 禁用表示禁止新的使用，并按事故等级决定是否取消活跃 Run；deprecated 仅提示迁移，不自动改旧任务。

### 2.3 个人与共享

- 个人 Prompt-only Skill 可以作为私有草稿，但仍不能改变上层权限和数据策略。
- 首版可执行 Skill 必须经过准入；未审核代码仅允许特定实验角色在无业务凭据、无业务出网的沙箱测试。
- 发布到部门/组织是显式操作，需审核/Grant，不因上传到某个目录就变成全局可见。
- 公共模板只读；员工修改时 fork 新私有版本，不能覆盖大家使用的目录。
- scripts 能读取到不代表可执行；`read_skill` 与 `execute_entrypoint` 权限分开。

### 2.4 对现有代码的改造

- `SkillRegistry._load/context/read` 保留文件解析经验，但由 `SkillPackageReader` 读取获权固定版本。
- 新增 `CapabilityRegistry`、`SkillVersionService`、`SkillAdmissionService` 和只读 artifact storage。
- `context()` 不再输出全局全部 Skill；从 ManifestSnapshot 生成目录。
- 模型需要脚本内容时通过获权读取；执行入口通过 ToolGateway→RunExecutor。
- 现有目录 `skills/` 可作为受信任种子来源，导入时生成版本和来源记录，不直接作为多用户可写共享目录。

### 2.5 Skill 验收

正常版本可发布且旧任务不受新版本影响；跨部门看不到未授权版本；禁用后新调用拒绝；恶意压缩包/Secret/路径逃逸被拒；修改已批准脚本必须重新审批；调用不存在的依赖给出可理解错误。

## 3. MCP 连接与工具治理

### 3.1 传输范围修正

原架构图将 HTTP/SSE、WebSocket、gRPC、自定义协议放在一起。这可以是“通用适配层”的长期目标，但不是 MCP 首版都要支持的标准传输清单。

首版建议：

1. **Streamable HTTP**：远程 MCP 主路径，选定客户端/协议版本并做互操作测试。
2. **stdio**：在专属沙箱/连接器执行单元启动本地 MCP 进程。
3. 旧式 HTTP+SSE：仅确有存量服务时通过兼容适配器支持，并明确与 Streamable HTTP 的 SSE 响应不是同一概念。
4. WebSocket/gRPC/自定义业务 HTTP：不假装是现成标准 MCP，后续按单独适配器加入。

当前 `mcp_server.py` 主要是把本项目 Sandbox 工具暴露出去，需要另建 MCP 客户端与连接生命周期管理，不能通过加几个服务器配置项就获得多租户接入。

### 3.2 连接模型

分离三种对象：

- **ConnectorDefinitionVersion**：连接器种类、允许端点模板、支持的协议、工具与风险策略。
- **ConnectionInstance**：属于哪个用户/部门、实际 endpoint、启用范围、状态。
- **CredentialBinding**：SecretRef/OAuth 身份、scope、版本、到期与撤销。

共享的是 Definition 和经审批的部门 Connection，不默认共享个人 Credential。一个数据库 MCP 是否允许全部门使用，同样取决于数据库账号/行级权限，不由平台给它贴“财务助手”标签决定。

### 3.3 连接过程

1. 用户选择允许的 ConnectorDefinition；自由 URL 仅对有维护权限的人开放，仍经过 SSRF 校验。
2. 创建处于 pending 的 ConnectionInstance，保存允许域名/端口/数据级别。
3. 发起 OAuth 或写入 Secret 服务；回调绑定 user、connection、state、nonce 和到期时间。
4. 在受控网络执行 initialize、能力协商、tools/resources 发现与健康检查。
5. 对 schema 做大小、嵌套、名称和风险约束；固定发现摘要。
6. 用户/管理员授权工具与资源范围，连接进入 ready。
7. tools 变化触发重新验证；新工具不能因为远端新增就自动加入所有人的 Manifest。

### 3.4 调用过程

`Tool alias → Manifest version → 当前授权 → 当前连接身份 → 参数校验 → 风险/审批 → 幂等调用 → 结果校验/截断 → 审计/上下文`

- 读工具也要授权；第三方 annotations 不能取代风险判定。
- 连接池/远端 session 按 org+connection+credential scope+revision 隔离，Cookie/default headers 不能跨身份复用。
- 字符串、二进制、图像、resource link 等结果分别限额；不把任意 URL 自动下载到控制节点。
- MCP 的错误与 progress 映射到平台 Invocation/Event，不把它的原始异常当作可信执行策略。
- 服务器返回的“请安装工具/读取密钥/访问另一个网站”等内容是数据，不能自动执行。
- 服务超时后先按工具是否幂等/外部可查询判定，不默认自动重试所有调用。

### 3.5 stdio MCP 特别约束

- 安装包与启动命令来自已发布 ConnectorDefinition；用户不能给控制服务传 `npx arbitrary` 或 `python arbitrary.py`。
- 进程运行在绑定 Run 的隔离单元，或未来具备同等身份/网络隔离的专用连接器单元。
- 私有 HOME、依赖、工作目录与 Secret scope；其他用户不可连接其 stdio/session。持有凭据的 stdio connector 默认与任意计算代码分 cell；同 Run 内也不能让 compute 读取凭据并直连业务系统。
- 凭据必须交给该进程时，承认该进程可读取它；使用最小 scope、短期 Token 与外部服务权限控制。
- 暂不池化有用户身份的 stdio 实例。支持长期状态的连接器需独立 TTL、撤权、清理与重建设计。

### 3.6 首批连接器选择

建议只选 2–3 个：一个只读内部知识/工单查询、一个测试数据库只读查询、一个具备明确幂等与查询接口的低风险写服务。不要以 GitHub/Jira/数据库/飞书全接完作为第一阶段目标。

测试至少包括成功、401/Token 过期、工具 schema 变更、429、超时、流断开、错误格式、结果过大、SSRF 重定向、权限撤销和写结果不明。

## 4. 知识库全链路

### 4.1 首版范围

先支持上传式 PDF/DOCX/TXT/Markdown/CSV 和必要的 XLSX，不先承诺全网爬取、音视频转写和所有企业知识源。现成企业数据源可在上传链路稳定后添加增量同步连接器。

摄取流程：

`上传槽 → 原始文件隔离存储 → 类型/大小检查 → 文档 ACL 固定 → parser Job → 规范化内容 → 分块 → embedding Job → 索引写入 → 版本原子切换 → 可检索`

每个阶段记录状态、耗时、parser/chunker/embedding 版本、重试次数与错误码。失败不会出现半份公开索引；解析输出也当不可信数据。

### 4.2 文档权限

- KB 范围授权是外层；文档 ACL 可更窄，不能自动继承宽权限。
- 来源系统无法提供可靠 ACL 时，默认只给导入者或保持 quarantine，不公开给整个部门。
- 原文、chunks、embedding 元数据、引用、摘要、下载遵守同一来源权限。
- 文档更新使用新版本和切换指针；旧内容不立即从活跃 Run 伪装消失，但新访问必须重新授权。
- 用户组/部门变化增加权限版本，失效检索缓存和后续上下文；不得只在导入时检查一次。

### 4.3 首版存储与检索选择

- 优先 PostgreSQL + pgvector，减少新增独立向量数据库；按实际数据量验证是否足够。
- 记录 embedding_model/version、dimension、distance metric、chunker/parser 版本；换模型/维度构建新索引，不混用旧向量。
- 中文关键词检索必须明确分词/索引方案，不能假定默认英文全文配置即可达到中文质量。可采用经过测试的中文分词加词项索引/pg_trgm 辅助；公司已有搜索平台时可复用。
- 初始 chunk 建议 400–800 token、重叠 60–100 token，并保留页码/标题/表格结构；根据实际 PDF/表格调优，不机械按字符截断所有类型。
- 入模 top_k 初始 5–8，候选数/重排预算可配置；查询改写、reranker 同样受数据出网策略。

### 4.4 检索授权顺序

1. 验证 Principal 和 knowledge/search 权限。
2. 得到当前可访问 KB/文档/版本范围。
3. 在数据库查询边界应用 org 与 ACL 条件，返回的候选文本必须已获权。
4. 混合召回、重排只处理获权内容；ANN 的过滤/召回不足要测试，必要时采用授权子集精确检索或增加有界候选预算。
5. 组装最小证据发给允许的模型，不发送全库内容。
6. 引用 API 再次校验，不因知道 chunk_id 就可读原文。
7. 缓存键包含 org、主体/权限 scope、ACL revision、索引版本、模型/查询配置；首版不启用跨权限域答案缓存。

应用后置过滤可以是额外防御，但不能让未授权内容先进入模型、reranker、日志或浏览器。

### 4.5 删除、更新与撤权

- 文档删除先使访问失效并增 deletion/ACL epoch，再异步删除索引、对象和派生缓存。
- 正在执行的摄取 Job 发布前检查 epoch，避免旧 Job 把已删除文档重新发布。
- 外部源的删除/权限变化必须作为同步事件处理，不只同步新增文档。
- 会话来源记录标出知识片段，下一次模型调用重建有效上下文；缺失来源或不可分离的旧摘要需要重新生成或阻止复用。
- 不承诺收回已经展示给用户或已经发送给外部模型的文本；通过最小披露与合规供应商降低风险。
- 备份恢复需重放删除与撤权记录，否则旧索引可能复活。

### 4.6 质量验收

准备至少 60 条真实业务类型的合成/脱敏题，覆盖单文档、多文档、表格、最新版本、无答案、越权诱导和冲突信息。

初始建议目标：授权负例泄露为 0；明确可回答问题的正确来源召回率 >= 90%；可回答问题业务正确率 >= 85%；引用支持回答的比例 >= 95%。这些是拟定质量门槛，需业务验收人确认并允许对困难文档调整解析方案；不把检索指标当成答案必然正确的保证。

## 5. Agent 配置与模型服务

### 5.1 AgentVersion

固定：指令版本、允许模型配置、可用 CapabilityVersion 范围、默认 runtime profile、最大轮次/工具数/费用、审批策略引用、数据分类要求。

可由员工覆盖的配置仅限明确白名单，例如语言、报告格式、允许模型集合中的选择；不能覆盖 endpoint、Secret、system 安全策略、挂载、runtime command 或组织预算。

### 5.2 当前 Provider 模块的复用方式

- 保留 `ModelClient` 的 respond/stream/complete 能力和兼容选项经验。
- 新增 ModelConfigVersion 与 SecretBindingResolver；生产禁用 `!shell` 密钥解析与任意用户 endpoint。校验必须在旧 Registry 解析配置之前完成，不能先执行旧解析器再检查输入是否安全。
- 缓存包含 org/连接身份/凭据版本，避免只按 provider+model 复用有身份状态的客户端。
- 模型目录对用户只返回其可用条目；不暴露原始配置路径、密钥是否属于其他部门等信息。
- 兼容 API 不等于模型行为等价，分别测试 tool schema、stream usage、finish_reason、取消和错误 redaction。
- 数据策略同时覆盖 embedding、reranker、摘要模型，不只主对话模型。

### 5.3 AgentRunner 改造

- 从 `SessionStore` 直接修改全局状态改为接受明确消息快照和 RunContext。
- 从 `self.tools.execute(name,args)` 改为注入 ToolGateway；全局 Registry 仅保存无身份的工具定义。
- 审批、事件、usage 不再依赖 HTTP 层 Future 或 generator 的存在。
- Planner、team 子步骤、汇总都记在同一 Run 的 Step 与预算内，不能在汇总时悄悄调用未授权模型。
- 工具上下文按 token/大小预算截断，全文保存在获权 Artifact/内容存储，不能把数据库当无限 prompt 缓存。
- 只读模型/工具单元测试继续使用 fake，避免测试调用真实模型或写外部系统。

## 6. EngineAdapter 与 Codex App Server

### 6.1 首版选型结论

**先稳定当前 Local Harness 的平台适配，再做 Codex PoC；不同时把多租户、沙箱、数据层和编排引擎全部替换。** 用户最初的问题由安全执行层解决，不由换一个 Agent 名称自动解决。

| 维度 | 当前 Harness 路线 | Codex App Server 路线 |
|---|---|---|
| 现有代码复用 | UI 行为、工具、Provider、测试可直接参考 | 需新协议适配和状态映射 |
| 模型接入 | 已有 OpenAI-compatible Provider 代码 | 具体模型/认证能力以固定版本文档和 PoC 为准 |
| 审批和事件 | 需要平台化持久重构 | 有引擎事件/审批协议，但企业授权仍自己做 |
| 执行边界 | 工具可统一路由 RunExecutor | 需要把整个执行宿主放隔离单元并审核内置接口 |
| 上线风险 | 主要是我们自己的重构和安全验证 | 额外有协议成熟度/实验接口/版本变化 |
| 推荐位置 | V1 默认 EngineAdapter | 后续可选引擎，功能开关默认关闭 |

### 6.2 统一适配接口

```text
EngineAdapter.capabilities() -> tool/stream/cancel/resume capability set
EngineAdapter.validate(agent_version, policy) -> compatibility result
EngineAdapter.start(context, messages, manifest) -> EngineHandle
EngineAdapter.events(handle) -> AsyncIterator[PlatformEngineEvent]
EngineAdapter.cancel(handle) -> cancellation status
EngineAdapter.checkpoint(handle) -> supported checkpoint metadata
EngineAdapter.close(handle) -> cleanup result
```

resume 只有引擎/任务确实支持时才声明；不伪造所有引擎可恢复。平台定义 Run/权限/审批/审计真相，不把某引擎内部 thread_id 当外部资源授权。

### 6.3 Codex 部署边界

- 独立用户/Run 执行单元内运行 App Server，至少独立 HOME/配置/历史/工作区/浏览器状态。
- 平台后端代理协议，浏览器不能直接连接 App Server 的原始端口。
- 采用固定版本、生成对应 schema、维护协议契约测试；stdio 或受控本地连接的桥接也要符合该版本文档。
- 不透传任意 method。尤其原始 shell/process 接口、配置写入、凭据管理、任意路径操作必须列入拒绝或严格授权清单。
- 业务 MCP 经平台 Gateway；动态 tools 或替代机制必须验证能否满足统一授权和审批。不能假定任意版本都支持完整拦截。
- 引擎内置文件/命令可能不经过平台 ToolGateway，必须由外部 OS 沙箱限制，并将其事件映射审计。**没有实现通用拦截前，不能宣称每个内置命令都被业务 Gateway 二次鉴权。**
- 不把全局模型长期凭据放入执行单元；优先验证受控模型代理/短期限权身份的兼容性。无法满足凭据边界时不能进入生产候选。
- 尽可能保留引擎自带 sandbox 作为纵深防御；若需 externalSandbox，必须先证明外层边界完整，不把它当简单的“关掉安全限制”。

### 6.4 官方资料核查与限制

2026-09-10 实际读取 OpenAI Docs：

- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Codex sandboxing](https://developers.openai.com/codex/sandboxing/)

对应事实：

1. App Server 是嵌入 Codex 客户端体验的协议接口，提供会话、审批、事件等能力，不是现成企业多租户平台。
2. 当前官方页对 App Server 命令/相关 WebSocket 使用标明实验和不支持生产负载的提示；动态 tools 也有实验标记。选型前要再次核查固定版本，不能以本文替代未来官方支持声明。
3. 文档明确 `thread/shellCommand`、实验性 `process/spawn` 在 Codex 自带 sandbox 外执行；若平台开放它们，安全最终由外层隔离承担。
4. Codex 自带 sandbox 作用于启动的命令，而不仅是内置文件 API；这与本项目单纯 cwd/workspace 不同。
5. 不推断公司共享登录、账号复用、计费或第三方模型兼容已经被允许。产品条款、企业采购和认证方式单独确认。

### 6.5 Codex PoC 的完成条件

- 用合成文件跑一条与 LocalHarness 相同的分析任务，完整映射 Run/Step/工具/审批/用量/取消事件。
- 两个用户/执行单元不能共享 thread 历史、HOME、工作目录、凭据或 Cookie。
- 危险 RPC 被拒绝；内置命令无法访问宿主或管理面。
- 工具撤权、模型预算、外部 MCP 审批在该引擎路径同样有效。
- API/App Server/执行节点任意重启后不误判完成、不自动重复外部写。
- 记录版本、启动参数、schema、实验功能清单、已知缺口和回退方案。
- 未达成上述条件时只保留实验环境，不改变 V1 默认引擎。

## 7. 能力建设顺序

1. 固定少量内置文件/计算工具，完成两用户 Run 隔离。
2. 导入审核过的现有 Skill，先只读与本地文件生成。
3. 接一个远程只读 MCP，验证身份与网络边界。
4. 完成上传知识库和文档 ACL，再接企业数据源。
5. 接受个人连接和经审核的 stdio MCP。
6. 开放少量可核对、幂等、审批明确的写工具。
7. 在同一权限/执行契约下验证第二种引擎。
8. 最后扩展自助发布、长期记忆、多源同步和更广能力市场。

每增加一种能力，都要添加至少一条成功、一条权限拒绝、一条资源/网络限制、一条故障恢复测试。能力数量不是平台成熟度的指标。
