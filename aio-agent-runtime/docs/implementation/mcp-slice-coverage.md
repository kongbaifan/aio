# MCP HTTP 只读增量：覆盖与差额

> 原 MCP-01～08 的范围保持不变。此文是事实映射，不将整套 MCP 或生产 Gate 勾成完成。

| 原规划 | 已落地的路径 | 未完成差额 |
|---|---|---|
| MCP-01 | 固定 2025-06-18 握手，HTTP JSON/SSE，初始化/工具发现/调用/关闭；有界帧与分页；官方 SDK 2.2 服务端真实互操作 | 新版协议、旧 SSE、完整进度展示；二进制仅显式标记未导入 |
| MCP-02 | ServerVersion、Connection、CredentialBinding 分离；个人/部门范围；每次调用独立 client/session；当前身份检查 | 更完整池化/TTL/连接级熔断与运维；高级委派管理 |
| MCP-03 | Bearer/匿名及 v10 OAuth/PKCE/OIDC、固定 metadata 验证、原浏览器绑定、refresh 单飞、稳定 grant/token generation 分离、有条件远端撤销 | 动态注册/全部供应商扩展、跨节点秘密轮换/保留与真实公司 Gate |
| MCP-04 | 操作员固定 URL/工具名、DNS 与 socket peer 校验、TLS SNI/证书不降级、不自动 redirect/resource fetch；工具摘要审核 | 逐供应商企业网络和数据分类 Gate；更丰富 schema 的安全适配 |
| MCP-05 | v11 独立 stdio cell、固定镜像/模板/依赖、按 Run/连接绑定、凭据 stdin 注入、独立令牌/节点 claim、双 opt-in 的显式 Run 附件副本、实际 Docker 与多身份 HTTP 证据 | 受控联网、活动 workspace 协作、更多运行时/供应商镜像的差量验收；见 [stdio 覆盖](stdio-slice-coverage.md) |
| MCP-06 | Run 固定身份、ActionSpec/generation/当前授权、稳定 operation key、持久 journal、未知结果不盲重试、状态核对基础 | 真实业务写保持关闭；逐工具结果查询/补偿/业务审计和风险批准 |
| MCP-07 | 错误脱敏、输出大小/类型/总超时/并发限制、鉴权失败与静态漂移拒绝 | 完整熔断、Retry-After/限流运营、二进制 Artifact、细粒度进度与源服务费用 |
| MCP-08 | 真实 PG + 网关、真实 HTTP/TLS/官方 SDK、凭据镜像 smoke、真实 compute 无凭据/来源传递、多身份 HTTP 工作台；OAuth 和无网络 stdio 另有差量 | 公司真实服务、联网 stdio、真实写路径、HA/完整生产安全矩阵仍未放行 |
| UI-07 | 我的连接、明确部门身份、密码型临时 Token 输入、稳定上传票据重试、连接检测、工具审核、Agent 定义选择、任务连接选择、撤销确认 | OAuth UX 已接通；复杂委派/跨节点密钥轮换、真实浏览器视觉和公司验收仍待完成 |

## 已验证的关键行为

- 同一 Agent 的两位使用者返回各自 MCP 凭据身份的数据；没有复制创建人的私人 Token。
- 即使测试夹具强行插入 connection.use Grant，其他用户仍不能借用个人连接；部门服务身份必须明确创建。
- 凭据保存状态仍为 pending；源服务初始化/工具发现成功后才为 active。不能把“加密写入成功”当作“源身份已验证”。
- Token/ref 改变后，旧任务/来源不会悄悄切到新身份；旧 ciphertext 退役失败仍由持久行触发重试。
- 远端工具描述或 schema 漂移，业务 tools/call 不发送；发送后断响应，Run 为 recovery_required，后续 Worker 不重发。
- DNS 查询结果与实际 socket peer 都受限；真实 TLS 使用原 Host/SNI，错误证书不收到凭据。资源链接只作数据。
- MCP 数据再经 Python compute 生成 Artifact，仍保留连接来源；给别人 Project/Artifact Grant 不能洗掉个人数据来源约束。
- API/Worker 的环境没有 vault key；真实 compute 无网且不含网关凭据。镜像 smoke 证明单独的 UID10002、只读 root 和私有状态卷，不是生产网络/HA 验收。

## 仍需特别说明

连接级来源不等价于每篇外部文档的实时 ACL；供应商 ACL 同步/查询适配与 KB 生命周期仍需落实。手工更换令牌/重新授权按新身份绑定处理；v10 的自动 OAuth refresh 单独记录 token generation，不重置 grant 版本。网关效果日志/密钥保留是有界原型，达到配额失败关闭，不能通过删除去重事实恢复容量。预览的用户、模型及源业务数据均为合成；视觉检查和公司真实 UAT 尚无证据。
