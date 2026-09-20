# 06. Skill、MCP、知识摄取和派生数据契约

> 关联 CAP-03～06、MCP-01～08、KB-01～09、GOV-01/06。统一资源授权和执行框架已经存在才可集成；不能每个连接器自建用户权限。

## 1. 能力目录的三种不同数据

| 对象 | 内容 | 可变性/权限 |
|---|---|---|
| CapabilityDefinitionVersion | 工具/Skill/KB adapter 定义、schema、入口、依赖、风险建议 | 发布后内容不可变；使用范围由 Grant/策略决定 |
| Binding/ConnectionVersion | 实际 endpoint/数据源/账号 scope/SecretRef/允许范围 | 有 owner/org/revision；更换身份导致旧审批失效 |
| Run ManifestSnapshot | 这一次任务允许的版本/alias/资源上限 | 固定内容，仅作为上限；当前撤权仍重新检查 |

Skill 声明 `requires: database.write` 只是申请，不授予权限；MCP 声明 `readOnly=true` 只是提示，不能把危险工具变只读。

## 2. Skill 包的可执行契约

### 2.1 包清单最低字段

```text
schema_version, name, semantic_version, publisher_ref
content_digest, file_manifest[(relative_path,type,bytes,sha256)]
instruction_ref, reference_refs
entrypoints[(id,language,fixed_path,input_schema,output_schema)]
runtime_image_digest, dependency_lock_refs
requested_capabilities, requested_network_profile
requested_data_classification, output_limits
license/source_refs, scan_report_refs, test_report_refs
```

- YAML/JSON manifest 使用安全解析器，禁自定义对象构造、动态 import、模板求值、重复字段和超深结构。
- 扫描包不能为了读取 metadata 而直接跑 setup.py/npm install/custom hooks。
- 相对路径拒绝越界、绝对路径、NUL、特殊节点和未经允许链接；归档解压边界包括数量、大小、压缩比和时间。
- file manifest 在隔离检查后由可信边界重新计算；不相信上传者声明 hash/size。
- 标准化只针对协议定义的路径表示，脚本内容和外部 opaque ID 的字节不任意改变。

### 2.2 发布步骤

1. 上传对象→quarantine；绑定 owner/org，任何人不能通过包 ID 读取其他人草稿。
2. parser/scanner cell 只见这个包，无业务 Secret/外网。
3. 检查依赖/许可证/镜像兼容和请求权限是否超过组织上限。
4. 用受控测试 Run、固定合成输入、允许 profile 执行已声明入口。
5. 审核者核对用途/风险/效果/成本/测试和权限；扫描通过不等于行为安全。
6. 创建不可变 published version，授予组织/部门/个人的使用 Grant；活跃 Run 继续固定旧版本。
7. disable 撤回后阻止新的工具调用；severe incident 可取消活跃 Run，但不篡改旧内容。

### 2.3 三类 Skill 区别

- instruction-only：仍是不可信指令；可影响模型选择但不能更改平台权限。
- typed entrypoint：平台用固定版本脚本+schema 执行，输入摘要与版本可审批。
- arbitrary-code helper：可生成任意 compute 代码，但无 connector Secret、无管理网；不因一份 SKILL.md 让它拥有任意业务写能力。

## 3. MCP 连接与协议边界

### 3.1 首版范围

选定并锁住客户端/协议版本。远程主路径采用已验证的标准 HTTP 传输；旧 SSE 仅为必要存量服务做明确兼容；stdio 在独立执行 cell；WebSocket/gRPC/自定义 HTTP 是额外 adapter，不能凭图上框声称已支持。

### 3.2 初始化和工具发现

```text
authorize connection.use
→ 验证 endpoint/实际解析目标/当前身份和 SecretRef
→ initialize/协商已支持能力
→ tools/list（有界）
→ 校验名称/schema/风险/结果类型
→ 对比已批准 schema_digest
→ 构建当前可用工具版本，不自动开放新增工具
```

- 远端工具描述可能含恶意指令，不把它作为平台级 system policy。
- capabilities 中 sampling/elicitation/roots 等默认不自动启用；模型费用、文件路径、用户输入收集分别需要平台代理/审批。
- 工具 schema 长度、深度、类型、名称、alias 冲突要验证；不能用工具名拼 Python getattr/模块导入或命令。
- session/cookie/header 池按 org+binding+外部主体+凭据 revision 隔离，出错时只影响该连接而非全体用户。

### 3.3 OAuth 和 endpoint 安全

- OAuth state 绑定当前用户和 connection，PKCE 按客户端/供应商协议实施；若使用 OIDC ID token，再验证对应 nonce/issuer/audience，不能要求所有 opaque OAuth Token 都有 JWT claims。
- 授权 metadata、token endpoint、resource link 和重定向同样受出口检查，不能因为来自“协议发现”就允许 SSRF。
- Token 只进 Secret 服务；不要将平台 BFF Cookie 或登录 Token 转发给任意 MCP。
- refresh 操作按 binding revision 单飞/加锁，新 Secret 写成功后再切引用；并发失败不恢复已撤销 Token。
- 外部服务器不支持撤销时明确 token 余效风险；平台阻止新使用并轮换，而非承诺下游立即无效。

### 3.4 写工具与业务资源范围

每个允许写的工具必须记录：外部目标、可作用资源、最大数量/金额、凭据 scope、风险级别、审批策略、幂等有效期、结果查询方法、补偿负责人。

允许发 SQL 的数据库工具不因为提示词写“只读”就安全：使用实际只读/行级权限账号、查询约束/受控操作集；不要连接平台自己的管理数据库，也不将管理员 DSN 给任意计算脚本。

真实副作用通过 TX-03/05/06；没有可核对能力的高风险写工具保持关闭。

## 4. 凭据连接器的独立执行模式

`compute code → ToolGateway → approved connector cell → business endpoint`

compute 只提交获权工具参数，不见 connector Secret、整个 stdin 控制句柄、文件系统或任意 exec 接口。connector 固定程序和镜像，不接受用户动态安装包改变其行为。需要附件时传明确 immutable object refs，不共享 writable root。

若由于兼容只能 co-locate，必须记录此时任意代码具有同凭据权限，禁高风险写/敏感 Secret 或换方案。不能继续宣称 Gateway 审批是不可绕过边界。

## 5. 知识摄取的数据契约

```text
DocumentVersion:
  org_id, kb_id, document_id, version_id
  source_id, source_revision, acl_epoch, deletion_epoch
  raw_object_ref, content_hash, data_classification
  parser_version, chunker_version
  embedding_config_id, dimension, distance_metric
  state, active_index_version?, provenance_refs

Chunk:
  org_id, document_version_id, ordinal
  content_ref, token_count, page_range, section_path, table_coordinates?
  embedding_vector, embedding_config_id
  source_acl_ref, source_epoch
```

- Chunk 不复制一份永远不变的宽 ACL 作为唯一授权；引用当前文档/来源权限和 epoch。
- 原文、归一文本、向量元数据、摘要、引用与下载相同范围约束。
- 向量本身也可能敏感；不能向第三方 embedding/reranker 发送未获准原文或向量。

### 5.1 阶段状态和重入键

| 阶段 | 幂等键 | 可公开条件 |
|---|---|---|
| upload | slot_id + verified content hash | 不公开，quarantine |
| parse | document_version + parser_version | 不公开，来源映射有效 |
| chunk | parsed_digest + chunker_version | 不公开，数量/范围校验 |
| embed | chunk_digest + embedding_config | 不公开，费用/维度可核对 |
| index | document_version + index_config | 候选索引，不进入活跃查询 |
| publish | source/ACL/deletion epoch + expected active version | TX-10 相关检查通过后原子切换 |

重复 Job 可重复计算安全纯阶段，但外部 embedding 可能再次收费，须预算和稳定调用账本，不把内容幂等误当费用只发生一次。

### 5.2 删除与旧 Job 的竞争

删除事务先改变 epoch/访问状态；已启动 parser/embedding 可以结束并被清理，但不能发布为 ready。Job 在每阶段尤其 publish 重新检查版本/删除 epoch。

若源端权限暂时不可查询，按批准 freshness policy 保守停止访问/发布，不能使用旧缓存无限延续访问。一次同步失败不等于源内容已删除，完整同步成功前不得把未看到的页面批量删除。

## 6. 授权检索的实现顺序

1. 验证 KB/search 动作、当前 Principal、来源/项目权限与数据策略。
2. 在数据库查询边界约束 Org 和可访问文档/版本；应用返回的候选文本必须已获权。
3. 关键词+向量召回只返回可访问候选，ANN 过滤造成召回不足时有界增加候选或对授权子集精确查询，绝不扩大权限。
4. reranker 只接收获权内容并经过供应商/数据策略。
5. 按最小必要上下文送主模型，记录来源与引用，不把原始整库内容塞入 prompt。
6. citation/read/download 再次授权，ID 不是访问票据。
7. cache key 包括 org/授权 scope/current ACL epoch/index/model/query config；先以无跨权限缓存为基线。

DB 内部索引算法扫描候选向量不等同于将它们外发；关键是任何越界内容不能离开数据库授权边界进入应用可见结果、模型、重排或日志。

## 7. 来源传播与分享判定

定义一个派生对象的 `source_refs` 与保守 `derived_access_policy`：

- 直接来源的最高数据等级不能被输出自动降低。
- 分享接收者必须满足来源约束；对多个来源，不能简单求用户集合并集。
- 内容模型声称“已去敏”不构成解限证据；降级/公开需要批准的处理器和审查流程。
- 删除/撤权后下一次使用旧摘要或对话拼装模型上下文，要根据来源过滤/重建；无法拆分时拒用该摘要。
- 用户手动粘贴的文本未必有可机器追踪来源，平台需要输入分类和组织规范，不能声称 provenance 能识别所有语义泄露。
- 来源集合过大时用聚合策略引用而不是截断到前 N 个丢失限制；超出可解释上限保持私有/拒绝分享。

## 8. 内容、版本与授权缓存失效

| 变化 | 必须失效/再确认的对象 | 不能做 |
|---|---|---|
| Skill 新内容发布 | 新 Agent/Run 选择、对应测试报告 | 替换旧 digest 内容 |
| Skill/工具紧急禁用 | 新调用、待审批动作、按风险活跃 Run | 只隐藏目录条目 |
| MCP credential revision | 池/session、ActionSpec、dispatch permit | 沿用旧审批发到新账号 |
| KB ACL/deletion epoch | 检索缓存、引用、摘要来源和 publish Job | 只删 UI 文档卡片 |
| 模型 endpoint/数据政策 | 模型 client、待派发外发决策、预算价格绑定 | 自动换不合规供应商 |
| 原始对象 hash 变化 | 所有依赖该内容的审批/扫描/版本 | 仍用旧成功扫描报告 |

## 9. 新引擎与已有能力的契约

EngineAdapter 只可使用平台认可的工具/模型/资源委托，不能把原始引擎方法直接暴露为企业 API。未来 Codex 固定版本仍要验证内置命令是否经过 Gateway；未经过的调用依靠外层 cell 限制并有独立审计，不能假称所有内置调用被平台审批。

本轮不新增某个 Codex 版本的产品能力结论；具体协议/实验功能/认证与生产支持在 ENG-01 按官方材料再确认。不符合平台边界的功能保持禁用，不能为接入第二引擎放宽所有用户权限。

## 10. 交付物和验收

- SkillVersion manifest/schema + positive/negative golden package。
- MCP ConnectorDefinition + 当前身份/协议/风险/幂等清单。
- Knowledge Document/Chunk schema + parser/index 版本 + ACL/deletion 竞争测试。
- 来源/分享策略编译器和可解释拒绝原因。
- ECASE-22/28～32、原 CAPTEST/MCPTEST/KBTEST 和 GOVTEST-11 相关证据。

只要任何数据/凭据/工具通过另一条路径绕过这些约束，能力就不能放行；不是“主路径正常”即可。
