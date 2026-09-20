# P3：共享能力与业务工作台

> 父任务共 23 项：CAP-03～06、MCP-01～08、KB-01～08、UI-03/05/07。全部待实施。P2 的网关和执行边界是前提，本阶段不再建立第二套授权或直接运行脚本的捷径。

## 1. 进入条件和分批范围

P2 至少一条“获权任务→专属执行→产物→销毁”闭环通过。Skill 发布、stdio MCP、parser、浏览器等新增路径分别扩展 G1/G2/G3；Python 单路径通过不能为它们背书。

分批：P3-A 内部 Skill/Agent 与一个远程只读 MCP；P3-B 上传 KB/ACL/引用；P3-C 个人连接、stdio 和可核对写的合成测试；P3-D 管理工作台与业务旅程联调。真实业务写、任意第三方发布、任意网络继续关闭。

## 2. Skill 和 Agent 模板任务卡

<a id="cap-03"></a>

### CAP-03 — Skill 包上传与准入扫描

**位置/契约**：`APP/capabilities/skill_packages.py,admission.py`、隔离 package scanner；包清单是权限申请，不是授予。

- [ ] **CAP-03.01** 定义 manifest schema：name/version/entrypoints/依赖/镜像/网络/数据/输出约束，未知危险字段拒绝。
- [ ] **CAP-03.02** 上传进入不可变 quarantine，用服务端 key、hash、owner 和 resource grant 绑定；禁止直接解压到控制代码目录。
- [ ] **CAP-03.03** 在隔离处理器校验压缩比、总大小/数量/层级、路径/链接/特殊文件、Secret 与来源许可证。
- [ ] **CAP-03.04** 验证脚本与引用存在、entrypoint 输入 schema、依赖锁与镜像兼容，不自动执行 setup/install/import 读取 metadata。
- [ ] **CAP-03.05** 保存结构化扫描状态、错误与人工复核标记，维护者只能访问自己的包/被授予版本。
- [ ] **CAP-03.06** 测恶意归档、重复版本/digest、越权包读取、伪造依赖和扫描中断，未通过保持不可执行。

**验收**：CAPTEST-05/06、SBXTEST-13；扫描不是安全证明，执行仍进沙箱。**PR/回滚**：停止新包准入，已批准版本固定引用不被覆盖。

<a id="cap-04"></a>

### CAP-04 — 获权不可变 SkillPackageReader

**位置/契约**：当前 `APP/skills/registry.py` 重构、`APP/skills/packages.py`；输入为 Manifest 中的 version_ref，不是全局目录。

- [ ] **CAP-04.01** 抽取 frontmatter/目录/引用读取逻辑，保留现有兼容用例，不再全局 rglob 后展示全部 Skill。
- [ ] **CAP-04.02** reader 只接受已获权 capability_version，校验内容 digest/文件清单/字节限制。
- [ ] **CAP-04.03** `read_skill` 与执行 entrypoint 分权限，能看脚本不代表可运行；禁止调用者换根目录。
- [ ] **CAP-04.04** 引用解析按版本包相对路径执行边界检查，处理 Unicode、符号链接和敏感文件名，跨包引用必须显式依赖授权。
- [ ] **CAP-04.05** context 仅提供授权描述/按需正文，控制 token 数量，缺能力返回明确不可用而不读旧目录兜底。
- [ ] **CAP-04.06** 测两部门同名包、版本更新、禁用、缺引用、大文件、跨根路径和旧测试回归。

**验收**：CAPTEST-01/03/04/07；版本更新不污染正在运行的上下文。**PR/回滚**：回到上一批准包版本，而不是全局共享 skills 目录。

<a id="cap-05"></a>

### CAP-05 — Skill 隔离测试、审核、发布、禁用和回滚

**位置/契约**：`APP/capabilities/releases.py`、Skill test Run、发布 API；发布是不可变版本状态变化。

- [ ] **CAP-05.01** 建 draft/scanning/testable/review_pending/published/deprecated/disabled 迁移和拥有者/审核者授权。
- [ ] **CAP-05.02** 从包 manifest 提取实际测试所需工具/网络/镜像，按组织上限裁剪，测试也不能扩大权限。
- [ ] **CAP-05.03** 在合成数据专属 Run 执行测试，保存输入摘要/镜像/产物/错误/资源和权限证据。
- [ ] **CAP-05.04** 审核覆盖权限、依赖、来源、业务效果、外部写和成本；高风险版本不能由维护者自批。
- [ ] **CAP-05.05** 发布版本不可变，AgentVersion 指向明确版本；灰度 scope 与正式 Grant 分开。
- [ ] **CAP-05.06** 禁用立即阻止新调用，严重事件取消相关活跃 Run；回滚只改新任务指针，不自动撤销旧业务写。
- [ ] **CAP-05.07** 测已批脚本/输入被修改、发布竞争、版本撤回、旧 Run 固定和缺测试证据发布被拒。

**验收**：CAPTEST-04/07/08、RUNTEST-11；测试按钮不运行控制服务脚本。**PR/回滚**：撤回版本、停相关能力并保留来源与审计。

<a id="cap-06"></a>

### CAP-06 — Agent 模板、发布版本与现有 Skill 种子导入

**位置/契约**：`APP/capabilities/agents.py`、AgentVersion API、受控导入脚本；模板不覆盖组织安全上限。

- [ ] **CAP-06.01** 定义模板名称/用途/指令引用/模型/能力/轮次/费用/profile/审批策略及 owner/scope。
- [ ] **CAP-06.02** 校验引用全部是已发布、获权、兼容的版本；员工覆盖项只允许语言/格式等白名单。
- [ ] **CAP-06.03** 实现草稿、评审、版本发布、灰度、禁用，运行中 Run 固定旧版本不热更新。
- [ ] **CAP-06.04** 从当前 `skills/` 选择少量内部种子，经过来源/扫描/测试后导入，不直接把整个归档目录公开。
- [ ] **CAP-06.05** 建三个试点模板并绑定明确数据政策与预算；没有权限的模型/工具不列在用户目录。
- [ ] **CAP-06.06** 测版本回滚、引用被禁、同名模板、超上限配置、模板作者试图注入管理指令。

**验收**：CAPTEST-01/04/06/08；业务人员只需选模板，不接触底层秘密。**PR/回滚**：禁模板或回上一批准版本，旧历史保持可解释。

## 3. MCP 任务卡

<a id="mcp-01"></a>

### MCP-01 — 标准远程协议适配器

**位置/契约**：`APP/mcp/client.py,protocol.py`；首选选定版本的 Streamable HTTP，存量旧 SSE 另列兼容。

- [ ] **MCP-01.01** 锁客户端/协议版本，明确支持 transports/capabilities；不把任意 WebSocket/gRPC 都称为标准 MCP。
- [ ] **MCP-01.02** 实现 initialize/协商/tools list/call/close，限制握手/响应大小与时间。
- [ ] **MCP-01.03** Tool schema 经平台验证/alias 映射后进入目录，不直接用远端名称调任意 handler。
- [ ] **MCP-01.04** 映射进度、错误、文本/二进制/resource link 的统一结果形态；返回内容是数据不是授权指令。
- [ ] **MCP-01.05** 不自动开放未实现的 sampling/elicitation/roots 等扩展；每类新增能力另评身份/费用/文件访问。
- [ ] **MCP-01.06** 建只读假服务与一个批准测试服务的互操作用例，包含拒绝/错误/协议差异。

**验收**：MCPTEST-01/05/06/08；当前 mcp_server.py 不能代替此 Client。**PR/回滚**：禁 connector 版本，不向浏览器透传原始服务。

<a id="mcp-02"></a>

### MCP-02 — 连接实例和身份隔离连接池

**位置/契约**：`APP/mcp/connections.py,pool.py`；DefinitionVersion、ConnectionInstance、CredentialBinding 三对象分离。

- [ ] **MCP-02.01** 保存连接 owner/scope/endpoint template/协议/凭据版本/status，与资源 Grant 关联。
- [ ] **MCP-02.02** 每次调用校验当前用户能使用的连接及目标工具/资源，不信任前端任意 connection_id。
- [ ] **MCP-02.03** 池键包含 org/连接/外部身份/凭据 revision，headers/Cookie/session 不跨主体共享。
- [ ] **MCP-02.04** 限制每连接并发、空闲 TTL、错误熔断，关闭/撤销时释放远端 session 与本地连接。
- [ ] **MCP-02.05** 部门共享必须显式配置部门服务身份及 scope；发布连接器定义不能顺带公开个人凭据。
- [ ] **MCP-02.06** 测相同 endpoint 两用户不同 Token、凭据轮换、停用、并发初始化和 stale session。

**验收**：MCPTEST-02/10、AUTH-05；共享 HTTP client 只有在无身份可变状态时才可复用底层设施。**PR/回滚**：关闭关联池并使连接失效，不转用公共 Key。

<a id="mcp-03"></a>

### MCP-03 — OAuth/凭据绑定、刷新和撤销

**位置/契约**：`APP/mcp/oauth.py`、连接授权 API；OAuth 回调绑定用户与连接，而非全局登录。

- [ ] **MCP-03.01** 审查授权服务器/资源服务器、metadata 端点和回调允许集，发现 URL 也受 SSRF 出口策略。
- [ ] **MCP-03.02** 实现 state/nonce/PKCE、client/issuer/resource/audience/scope 校验，按供应商协议要求记录最小授权。
- [ ] **MCP-03.03** Secret 只写密钥服务，浏览器/日志不回显 refresh/access token；不能把平台登录 Token 原样透传给其他服务。
- [ ] **MCP-03.04** 刷新按 connection+revision 加锁/去重，避免并发刷新互相作废；失败变成需重新授权。
- [ ] **MCP-03.05** 撤销连接递增 revision，关闭池、阻止排队/后续调用，按外部能力撤销远端 Token。
- [ ] **MCP-03.06** 测回调重放/串用户/过期 scope、刷新竞争、外部 revoked、Secret 服务故障和断网。

**验收**：MCPTEST-03/10、GOVTEST-04；不以 UI “连接成功”替代实际身份验证。**PR/回滚**：断开连接要求重新授权，不保留旧宽权限 Token。

<a id="mcp-04"></a>

### MCP-04 — 端点、schema 变更和 SSRF 约束

**位置/契约**：`APP/mcp/admission.py,endpoints.py`；测试连接与正式调用用同一路径。

- [ ] **MCP-04.01** ConnectorDefinition 限制 scheme/域名/端口/地址范围，内网业务只允许精确批准目标。
- [ ] **MCP-04.02** 校验解析和实际连接 IP、每次重定向、IPv6/loopback/link-local，不只创建时检测 URL。
- [ ] **MCP-04.03** tools list 保存 schema_digest，新增/变更工具进入待审核，不自动扩张 Manifest。
- [ ] **MCP-04.04** 风险由平台确认，第三方 readOnly/destructive annotations 只作提示。
- [ ] **MCP-04.05** resource link/图片/文档自动获取同样限网络/大小，用户内容不能驱使控制服务访问管理网。
- [ ] **MCP-04.06** 测 schema/名称冲突、重定向/重绑定、连接器偷偷增加写能力和管理员测试入口。

**验收**：MCPTEST-04/05/06/07、SBXTEST-15。**PR/回滚**：端点/版本 quarantine，不以跳过证书/地址检查恢复连接。

<a id="mcp-05"></a>

### MCP-05 — stdio MCP 专属执行单元

**位置/契约**：`EX/mcp_stdio.py`、connector 镜像/启动模板；本地 server 进程不在 APP 宿主启动。

- [ ] **MCP-05.01** 发布固定启动 executable/args、镜像/包锁、允许环境变量与输入输出协议。
- [ ] **MCP-05.02** 由 Run binding 创建私有 HOME/workspace/依赖和 stdio 通道，用户不能给控制服务传任意启动命令。
- [ ] **MCP-05.03** 凭据仅在必要时用最小短期 scope 注入，进程和同单元代码可读取这一事实写入风险声明。
- [ ] **MCP-05.04** 控制协议与进程日志分离，输出洪水/畸形帧/挂起不能耗尽 Gateway 内存。
- [ ] **MCP-05.05** 进程/session 与 Run 绑定，结束/撤权/timeout 时停止整个进程树；不池化租用过的有身份实例。
- [ ] **MCP-05.06** 重跑该新 executor 的 G1/G2/G3 差量，含跨用户 session、HOME、Secret、网络和清理。

**验收**：MCPTEST-09/10、SBXTEST-04/08/10/20。**PR/回滚**：关闭 stdio transport，远程已验收能力可保持，不能转宿主执行。

<a id="mcp-06"></a>

### MCP-06 — 可核对的外部写调用

**位置/契约**：`APP/mcp/write_actions.py,reconciliation.py`；真实开放必须逐工具批准。

- [ ] **MCP-06.01** 对每工具记录风险、业务对象、最大影响、下游幂等/查询/取消/补偿能力；不可核对高风险工具默认不准入。
- [ ] **MCP-06.02** Gateway 冻结参数/版本/连接 scope/输入摘要并审批，执行前再次授权与数据检查。
- [ ] **MCP-06.03** 在可靠意图记录后发请求，稳定业务幂等键跨网络重试/Worker 接管不改变。
- [ ] **MCP-06.04** 区分明确未发送、已发送未响应、可查询已成功/失败和未知，unknown 不自动入普通重试队列。
- [ ] **MCP-06.05** 实现有权限的结果核对与证据链接，补偿属于新审批动作，不能把平台回滚视为业务撤销。
- [ ] **MCP-06.06** 用假写服务覆盖“成功后断响应”、幂等冲突、查询延迟、旧 Worker 与用户重复点击。
- [ ] **MCP-06.07** 保留真实写 feature flag 关闭；P5 才按工具和业务范围逐项准入。

**验收**：MCPTEST-11、RUNTEST-11/13/14；不承诺通用 exactly-once。**PR/回滚**：阻止新增写/进入核对，保留已发生影响和意图事实。

<a id="mcp-07"></a>

### MCP-07 — 结果、限额、超时和熔断

**位置/契约**：`APP/mcp/results.py,resilience.py`；异常不会直接变成模型的管理指令。

- [ ] **MCP-07.01** 映射 protocol progress/result/error 到 Invocation/Event，工具名/ID/seq 可以稳定关联。
- [ ] **MCP-07.02** 限制文本/二进制/图片/资源链接数量、响应深度和大小，原始大对象写受限内容存储。
- [ ] **MCP-07.03** timeout 取工具/Run 剩余时间与连接上限的最小值，取消停止后续读取和新增调用。
- [ ] **MCP-07.04** 只对明确可重试的安全情况退避，429 尊重限制；非幂等写不得使用通用 HTTP 重试器。
- [ ] **MCP-07.05** 连接级熔断/限流不拖垮其他用户；错误脱敏，未知结果与普通网络失败区分。
- [ ] **MCP-07.06** 测巨响应、畸形 JSON、流不结束、progress 洪水、慢消费者和连接恢复。

**验收**：MCPTEST-07/08、GOVTEST-04；资源有界。**PR/回滚**：禁异常连接器/收紧限额，不提高到无限超时。

<a id="mcp-08"></a>

### MCP-08 — MCP 全链路互操作与安全验收

**位置/契约**：`HTEST/integration/mcp/`、真实隔离 stdio 测试；不同传输分别记录通过情况。

- [ ] **MCP-08.01** 建固定版本 HTTP、旧式兼容（若启用）、stdio 和可核对写测试服务。
- [ ] **MCP-08.02** 执行授权/凭据隔离、OAuth/revocation、schema 变化/风险注解、SSRF/resource link 测试。
- [ ] **MCP-08.03** 注入 401/429/超时/断流/进程退出，验证有界资源和 Invocation 状态。
- [ ] **MCP-08.04** 重复写/响应丢失/旧 generation 不导致重复业务动作；unknown 可人工核对。
- [ ] **MCP-08.05** 列出每连接器的允许用户/数据/工具/profile/外部身份和真实写开关状态。
- [ ] **MCP-08.06** 对任何未通过能力保持 API 级关闭，不只从目录隐藏，形成 G4 MCP 证据。

**验收**：MCPTEST-01～12 全部适用用例；只读上线不能顺带启用写。**PR/回滚**：按 connector/version/transport 禁用，保留正常只读能力。

## 4. 知识库任务卡

<a id="kb-01"></a>

### KB-01 — 知识库、文档版本与 ACL

**位置/契约**：`APP/knowledge/models.py,service.py`、KB/document API；文档 ACL 可以比 KB 更窄。

- [ ] **KB-01.01** 建 KB、Document、Version、source、classification、ACL revision、deletion epoch 与资源关联。
- [ ] **KB-01.02** 创建/管理/读/检索/引用权限分别定义，默认私有；缺来源 ACL 时 quarantine，不推断全部门可读。
- [ ] **KB-01.03** 文档版本不可变，active_version 切换原子；source_key 去重不跨组织误合并。
- [ ] **KB-01.04** API 列表/详情只返回获权标题/摘要/状态，输入 upload slot 验证属于同项目/调用者。
- [ ] **KB-01.05** 文档级来源/分享限制向 chunks、答案、Artifact 传播，不能因创建 KB 而放宽源权限。
- [ ] **KB-01.06** 测同名跨部门/组织文档、缺 ACL、错误 FK、旧版本与停用。

**验收**：KBTEST-03/04/14、AUTH-05；不提前开放未索引文本。**PR/回滚**：禁 KB 访问或保留旧已获权版本，不公开隔离内容。

<a id="kb-02"></a>

### KB-02 — 摄取状态、Job 与发布一致性

**位置/契约**：`APP/knowledge/ingestion.py,jobs.py`；输入获权 upload，输出可查询阶段状态。

- [ ] **KB-02.01** 定义 uploaded/scanning/parsing/chunking/embedding/indexing/ready/failed/deleted 与每阶段重试边界。
- [ ] **KB-02.02** Job 采用同一 PG lease/generation 框架，摄取与交互队列配额分开但共享节点总限制。
- [ ] **KB-02.03** 每阶段保存输入 hash、处理器/模型版本、输出引用和错误码，失败可解释。
- [ ] **KB-02.04** 重试使用 content hash+版本幂等，不能重复添加 chunks/收费请求或公开半份索引。
- [ ] **KB-02.05** 发布前比较 active source/deletion/ACL epoch，旧 Job 不复活已删除文档。
- [ ] **KB-02.06** 测上传中断、重复 Job、阶段退出、PG/存储故障、取消与状态查询权限。

**验收**：KBTEST-01/09/10、RUNTEST-04/05；状态日志不含原文/Secret。**PR/回滚**：停止摄取并保留已发布版本，未完成候选受控清理。

<a id="kb-03"></a>

### KB-03 — 隔离 parser 与不可信文档

**位置/契约**：parser 镜像、`EX/parsers/`；不在 API/Worker 控制进程解码恶意文件。

- [ ] **KB-03.01** 明确首批 PDF/DOCX/TXT/Markdown/CSV/XLSX 类型与大小/数量上限，拒绝不支持类型。
- [ ] **KB-03.02** 禁 Office 宏、文档外链、自动取远程内容，parser profile 默认无业务出网。
- [ ] **KB-03.03** 对解压/解码/页数/图片/OCR/表格单元格设置有界限制和超时，防压缩炸弹与巨大结构。
- [ ] **KB-03.04** 输出规范化文本/页码/标题/表格位置与处理器版本，保留来源映射，不把所有内容盲切字符。
- [ ] **KB-03.05** 错误/截图/临时文件受原文权限与 TTL，所有子进程回收；损坏文件可重试或提示人工转换。
- [ ] **KB-03.06** 新 parser 执行路径重跑资源/网络/Secret/清理差量和恶意文件夹具。

**验收**：KBTEST-02、SBXTEST-04/09/10/13。**PR/回滚**：禁问题类型/处理器版本，不换到控制服务解析兜底。

<a id="kb-04"></a>

### KB-04 — 分块、嵌入、版本索引与计费

**位置/契约**：`APP/knowledge/chunking.py,embedding.py,indexing.py`；索引受 document version 与 org 约束。

- [ ] **KB-04.01** 选择初始 chunk/token/重叠策略并保留标题/表格边界，记录 parser/chunker 版本。
- [ ] **KB-04.02** 嵌入请求受数据端点与预算策略，批处理大小、timeout/retry 有界且记账。
- [ ] **KB-04.03** 保存 embedding model/version/dimension/metric，不混合不同维度或配置的向量。
- [ ] **KB-04.04** 以文档版本+序号/digest 幂等写 chunks 和候选索引，完成后原子切换 ready 指针。
- [ ] **KB-04.05** 模型/分块升级建立新索引，支持验证后切换和保留旧已批准索引，不边写边污染活跃查询。
- [ ] **KB-04.06** 测重复嵌入、断网、部分成功、维度错误、预算耗尽、source epoch 变更。

**验收**：KBTEST-10/11、GOVTEST-01/02/03。**PR/回滚**：切旧兼容索引或暂停检索，不跨维度强行查询。

<a id="kb-05"></a>

### KB-05 — 授权混合检索、中文质量与缓存

**位置/契约**：`APP/knowledge/retrieval.py,filters.py,cache.py`；未授权文本不进入模型/重排/日志。

- [ ] **KB-05.01** 根据 Principal/KB/document ACL/revision 计算允许范围，查询前实施 org/文档过滤。
- [ ] **KB-05.02** 选择 pgvector 与经过验证的中文关键词方案，不假定默认英文全文配置即可处理中文。
- [ ] **KB-05.03** 混合召回与 rerank 只接收获权候选，记录 top_k/候选预算；ACL 稀疏时有界授权回退而不放宽权限。
- [ ] **KB-05.04** 缓存键包含 org/授权 scope/ACL revision/index/model/query 配置，首版禁跨权限答案缓存。
- [ ] **KB-05.05** 查询改写/重排/摘要同样检查数据出口与预算，检索结果来源进入 Run provenance。
- [ ] **KB-05.06** 测跨用户同查询、撤权后缓存、ANN 过滤、关键词和中文表格检索、提示注入。

**验收**：KBTEST-03/04/05/06/08/13；拒绝“先给模型再过滤”。**PR/回滚**：禁缓存/回退获权精确检索，不能禁 ACL 换召回率。

<a id="kb-06"></a>

### KB-06 — 可验证引用与原文阅读

**位置/契约**：`APP/knowledge/citations.py`、引用 API、`WEB/features/knowledge/citations`。

- [ ] **KB-06.01** 定义 citation ID→文档版本/页码/段落/chunk 的服务端映射，不由模型自由编造下载地址。
- [ ] **KB-06.02** 原文、引用片段、页预览、下载分别再次检查当前 ACL，知道 chunk_id 不等于可读。
- [ ] **KB-06.03** 答案关联证据列表，证据不足/冲突/版本过期给明确说明，不用空引用伪装有来源。
- [ ] **KB-06.04** 前端显示标题/版本/位置仅限获权内容，链接不携带平台 Token，预览无脚本执行。
- [ ] **KB-06.05** 引用失效后解释来源不可访问，不悄悄改指向最新不同内容或暴露被撤权摘要。
- [ ] **KB-06.06** 测猜 citation ID、跨组织版本、撤权、文档更新、畸形模型引用和无答案。

**验收**：KBTEST-07/12、UITEST-05/06。**PR/回滚**：关闭引用阅读/给明确不可用，不公开原始对象链接。

<a id="kb-07"></a>

### KB-07 — 更新、删除、撤权与派生上下文失效

**位置/契约**：`APP/knowledge/lifecycle.py,provenance.py`；访问失效优先于异步物理删除。

- [ ] **KB-07.01** 删除/撤权先更新状态与 epoch，立即阻止新读/检索/引用/外发，后续清理异步执行。
- [ ] **KB-07.02** 旧摄取 Job 发布前检查 source/ACL/deletion epoch，失败不能重新公开旧内容。
- [ ] **KB-07.03** 删除索引、缓存、对象、引用与派生内容建立可重试清单和计数，异常可告警追踪。
- [ ] **KB-07.04** 旧 Session/摘要在下一调用前根据 provenance 重建；无法分离受限来源的摘要不继续发送给模型。
- [ ] **KB-07.05** 文档版本更新与部门组变更同步失效，备份恢复时重放当前删除/撤权事实。
- [ ] **KB-07.06** 测删除与索引竞争、旧缓存/摘要、重复清理、部分失败、恢复后不复活；明确已披露内容无法收回。

**验收**：KBTEST-08/09/14、GOVTEST-10/11。**PR/回滚**：保持访问拒绝，即使物理清理失败也不恢复旧公开状态。

<a id="kb-08"></a>

### KB-08 — 知识质量与 ACL 联合验收

**位置/契约**：`HTEST/evals/knowledge/`、业务测试集和固定期望来源；质量不能以越权换取。

- [ ] **KB-08.01** 建至少 60 条脱敏/合成题，含中文表格、多页、多文档、无答案、冲突、新旧版本和越权诱导。
- [ ] **KB-08.02** 为可答题固定允许来源和业务答案，由业务负责人审核而非模型自评作为唯一标准。
- [ ] **KB-08.03** 记录召回/答案正确/引用支持/延迟/费用，数据/模型/索引版本可复现。
- [ ] **KB-08.04** 权限泄露负例必须零允许，质量门槛按已冻结目标验收，不能用平均分掩盖越权。
- [ ] **KB-08.05** 注入 parser/embedding/index 故障与预算耗尽，验证 UI 和任务状态可理解。
- [ ] **KB-08.06** 形成 G4 KB 证据、已支持文档类型、索引/模型配置和待优化清单。

**验收**：KBTEST-01～14 适用场景，业务来源审核与自动化证据齐全。**PR/回滚**：禁问题文档类型/索引/模型配置，保留已批准服务范围。

## 5. 工作台任务卡

<a id="ui-03"></a>

### UI-03 — Agent、项目与会话目录

**位置/契约**：`WEB/features/agents,projects,sessions/`；列表由服务端授权范围生成。

- [ ] **UI-03.01** 展示 Agent 用途、版本、数据提示、允许输入和可用状态，只列已获权发布版本。
- [ ] **UI-03.02** 项目/会话分页、创建/重命名/删除使用 revision，处理只读/活跃 Run/写 lease 占用。
- [ ] **UI-03.03** 项目共享与私人 Session 可见性分开解释，成员管理只给相应角色。
- [ ] **UI-03.04** 模型选择仅来自授权版本集合，不允许编辑 endpoint/Key/系统权限；模板被禁后清楚提示。
- [ ] **UI-03.05** 切项目/账号清理旧缓存与请求，未完成请求不能把旧用户结果刷到新页面。
- [ ] **UI-03.06** 测两个部门同名资源、无可用 Agent、权限撤销、成员变化与删除冲突。

**验收**：UITEST-01/09/10、AUTH-04/05。**PR/回滚**：目录不可用时明确错误，不调用旧全局 `/api/sessions`。

<a id="ui-05"></a>

### UI-05 — 上传、产物、预览、引用和分享

**位置/契约**：`WEB/features/files,artifacts/`；所有文件操作围绕资源 ID 和发布状态。

- [ ] **UI-05.01** 上传使用 slot，显示进度/中断/大小/用途/扫描状态，不在客户端把文件标为已批准。
- [ ] **UI-05.02** 只展示 ready 的正式 Artifact，候选/扫描失败/仍保存的文件有明确状态与重试范围。
- [ ] **UI-05.03** Markdown/文件名/预览统一清洗，HTML/SVG/Office 使用隔离或下载策略，不执行同域脚本。
- [ ] **UI-05.04** 下载/引用每次获取获权能力，短期链接过期明确重取；不放长期 Token 到 URL。
- [ ] **UI-05.05** 分享界面说明对象范围/到期/来源限制，后端 GOV-06 未就绪时分享关闭，不能前端合成公开 URL。
- [ ] **UI-05.06** 测同名文件、多任务输出、存储失败、撤权、恶意文件名、签名链接到期和支持访问限制。

**验收**：UITEST-05/06/10、GOVTEST-09/11；共享功能正式集成在 P4 再验收。**PR/回滚**：关预览/分享但保留授权下载，不放宽文件权限。

<a id="ui-07"></a>

### UI-07 — Skill、连接和知识的管理页面

**位置/契约**：`WEB/features/skills,connections,knowledge/`；功能出现取决于角色和实际后端能力。

- [ ] **UI-07.01** Skill 草稿/版本/扫描/测试/审核/发布/禁用状态可见且能解释失败，普通员工不出现发布管理权。
- [ ] **UI-07.02** MCP Definition/Connection/Credential scope 分开展示，个人连接不会被误认为全公司共享。
- [ ] **UI-07.03** OAuth/Secret 输入只提交不回显，测试连接、撤销、重授权与 schema 变化有明确反馈。
- [ ] **UI-07.04** 知识上传显示 parse/embed/index 阶段、失败/重试、来源权限和引用状态，删除说明传播进度。
- [ ] **UI-07.05** 个人/部门/项目 scope 切换清空相关缓存，后端独立授权；未准入写/stdio 功能保持禁用。
- [ ] **UI-07.06** 测快速切范围、过期授权、两个审核人竞争、连接失效和摄取失败。

**验收**：UITEST-07/09/10、MCPTEST-03/10、KBTEST-01/09。**PR/回滚**：按功能 flag 禁管理操作，不影响安全读取已有发布资源。

## 6. 联调批次与 PR 边界

- PR-P3-A：Skill 包/reader；PR-P3-B：测试/发布/Agent 模板；各自带 ACL/版本负例。
- PR-P3-C：远程 MCP 只读协议/连接身份；PR-P3-D：OAuth/SSRF/schema/韧性；PR-P3-E：stdio/可核对写，仅测试启用。
- PR-P3-F：KB 元数据/Job/parser；PR-P3-G：embedding/ACL 检索/引用；PR-P3-H：更新删除/质量集。
- UI 可用相同契约 fake 并行，最终必须与真实服务跑双用户 E2E。未就绪分享/运营能力显示关闭，不跳过授权演示。

## 7. G4 演示与交接

1. 发布一个已扫描测试的 Skill，Alice/Bob 使用不同版本，旧 Run 不受新发布污染。
2. 同 endpoint 两个 MCP 身份返回不同授权业务数据，撤销 Alice 连接不借 Bob 凭据继续调用。
3. stdio 进程和 parser 在专属执行单元，结束后无进程/HOME/Secret 残留。
4. 知识同名文档按部门隔离；删除/撤权后旧缓存和下一轮上下文不能继续外发。
5. 外部写假服务成功后断开，进入待核对；生产写 flag 保持关闭。
6. 管理 UI 能看到扫描/摄取/授权错误，员工只看到可使用能力。

交 P4：能力准入清单、全部版本与来源、真实外部写开关、授权/隔离/恢复差量报告、业务样本与质量基线。任何新连接器/文档类型未通过时从试点清单排除，不拖累已批准能力，也不靠隐藏按钮假装关闭。

## 工程契约补充

持凭据 stdio MCP 默认独立 connector cell，compute 不能读取其 Secret 或直连业务系统绕过审批；知识检索/引用/派生数据的当前授权与删除 epoch 必须共同生效。 详见 [工程契约索引](../engineering/README.md)；任务 ID 和原有子任务顺序保持不变。
