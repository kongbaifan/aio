# 独立 MCP 凭据网关

固定代码的私有服务，负责 MCP HTTP 协议、隔离 stdio 委派、连接身份隔离、加密凭据/结果缓存、实际出口检查与一次性派发记录。它**不是任意 Python/Skill/MCP 程序执行器**，不接受客户端命令、模块路径、任意 URL、任意 Header，也没有读取令牌原文的 HTTP API。stdio 第三方代码只在独立 Manager 创建的批准 cell 中执行。

```text
业务浏览器 -> BFF / PG 权限与 Run -> 私有 Connector Gateway -> 批准的 MCP 服务
                                  |-> 当前授权回调 /internal/v1/connectors/authorize
                                  |-> 独立 AES-GCM 凭据与调用事实卷
                                  |-> 专属 stdio Manager API -> 按 Run/连接隔离的无网 MCP cell

任意 Python / Skill -> 独立无网 compute cell（无上面的密钥/卷/管理网络）
```

## 当前支持和不支持

- 固定 `2025-06-18` MCP 握手协议，Streamable HTTP，JSON 和 SSE 响应；与锁定的官方 `mcp==2.2.0` 服务端兼容握手实际测试。
- initialize、initialized、tools/list 分页、tools/call、关闭会话；不把 WebSocket/gRPC 或旧 SSE endpoint 握手称为已经支持。
- Bearer 或由操作员明确配置的匿名端点。每次操作创建独立 HTTP/MCP session；不复用跨连接/凭据身份的 Cookie/session。
- 支持有界文本、structuredContent、内嵌文本；resource_link 仅返回元数据，**不自动抓取**。二进制内容报告大小/摘要及 `BINARY_ARTIFACT_IMPORT_UNAVAILABLE`，不是已导入可下载产物。
- 不开放 sampling、elicitation、roots、动态客户端执行；服务器 ping 可响应，其他客户端能力请求明确拒绝。
- **仅操作员显式列出的只读工具**。只读权限必须由源系统账号/权限真正限制；工具 `readOnlyHint` 不是安全边界。
- 配置后的 HTTP OAuth code/PKCE、OIDC/JWT 校验、自动刷新与 RFC7009 撤销已实现。stdio 使用固定模板、Bearer/匿名模式及独立无网 cell，不将 HTTP OAuth 配置解释成 stdio 授权。
- stdio 按 Run/代次/连接复用进程，发现单独短时运行；撤权、挂起、完成与清理停止进程。隔离程序可读取其获授 Token，但拿不到平台/模型/控制密钥。凭据通过 exec stdin 传递，Manager 仅记录摘要和生命周期，不落明文结果。
- stdio 受控联网、其他传输、真实业务写、二进制产物、供应商费用核算、完整保留/HA/专业审计尚未交付，不能声称 MCP 全生命周期完成。

OAuth 示例见 [`connector-oauth-endpoints.example.json`](../../config/connector-oauth-endpoints.example.json)。预登记 client、固定 metadata/JWKS/token/revoke URL 与端点专属回调；秘密值只注入网关的 `CONNECTOR_OAUTH_CLIENT_SECRET_*` 环境变量。平台数据库只持有绑定和授权意图，不存 access/refresh token。完整配置/状态/限制见 [OAuth 契约](../../docs/engineering/platform-mcp-oauth-contract.md)。

## 启动和部署边界

```sh
python -m pip install -e services/connector-gateway
# 将配置明确注入进程环境后运行；不会自动加载旧 .env。
aio-connector-gateway
```

环境模板：[connector-gateway.env.example](../../config/connector-gateway.env.example)，端点格式：[connector-endpoints.example.json](../../config/connector-endpoints.example.json)。需要：

| 配置 | 责任 |
|---|---|
| CONNECTOR_ENDPOINTS_FILE | 绝对 JSON 路径，操作员批准的固定 endpoint id/URL/auth/read_tools/网络范围 |
| CONNECTOR_VAULT_ROOT | 独立、持久、仅该服务可读写的绝对目录 |
| CONNECTOR_VAULT_KEY | 来自密钥服务的随机 256-bit AES key（Base64）；不放源码、命令参数或 API/Worker 环境 |
| CONNECTOR_SERVICE_TOKEN | API/Worker -> 网关；强服务凭据 |
| CONNECTOR_CONTROL_ORIGIN/TOKEN | 网关 -> 平台实时授权；与上面的 token 不同 |
| CONNECTOR_CA_FILE | 可选公司 CA 文件；绝不关闭 TLS hostname/certificate 校验 |
| CONNECTOR_STDIO_MANAGER_URL | stdio 使用的固定私有 Manager；没有配置时 stdio endpoint 使启动失败，不回退本机执行 |
| CONNECTOR_STDIO_MANAGER_TOKEN | 匹配 Manager 的 SANDBOX_CONNECTOR_TOKEN，与普通 compute token/其他控制凭据分离 |

API 设置 `PLATFORM_CONNECTOR_URL/TOKEN/CONTROL_TOKEN/ENDPOINTS`，Worker 只设置 URL/TOKEN，**不持有 vault key**。两侧端点 id/URL/auth 的摘要必须一致；端点改变不能复用原绑定去转发令牌。

stdio endpoint 使用 `transport=stdio`、`url=stdio://<profile_id>` 和批准的 image/template/credential_env/network_profile 引用，不从页面接受安装命令。操作员可用 `scripts/platform/export_stdio_endpoint.py` 从已审核 profile 生成引用；配置和升级见 [stdio 契约](../../docs/engineering/platform-mcp-stdio-contract.md)。Gateway 仍不持有 Docker Socket；只有 Manager 具备 Docker 权限。

可选 `input_policy=run_attachments` 仍需本次 Run 的 `allow_stdio_attachments=true`。Gateway 只在首开 preparing 进程时，经当前授权的私有 `inputs` 回调转交最多 4 MiB/32 个所选附件，不读取本地目录或建立明文附件缓存；ready 会话不再次覆盖输入。普通控制响应仍限制 64 KiB，输入专口响应限制 6 MiB。详见 [附件输入契约](../../docs/engineering/platform-mcp-stdio-input-contract.md)。

生产必须置于受控私有网络和 TLS 代理后，限制入口仅允许 API/Worker。Dockerfile 使用 UID10002；部署时继续设置 read-only root、cap_drop ALL、no-new-privileges、CPU/内存/PID 限额。只给它挂载私有 vault 卷和只读配置/CA；不给 Docker Socket、平台数据库、OIDC secret、模型密钥或用户 workspace。更不能把该凭据卷挂到 compute 容器。

一份 journal 只能由一个服务进程持有，持文件锁。**不要把多个独立目录/副本放到负载均衡器后冒充无状态 HA**，否则会分裂派发事实。多节点一致存储/密钥轮换/备份恢复需要后续独立验收。

## 数据、协议和出口约束

- 凭据和已返回工具结果用 AES-GCM 加密；AAD 绑定 org、connection、凭据 revision/ref 和固定 endpoint。不同租户/连接的 ciphertext 不能互换。误配密钥使服务失败关闭。
- 退役留下 tombstone，拒绝迟到的同 ref 上传重新激活。平台先撤回当前引用，再由后台维护删除网关 ciphertext；这不等于在供应商端撤销 Token。
- 请求必须通过专用服务 token 和平台权威回调。浏览器 Cookie 不能调用网关，模型或第三方描述不能修改身份/目标。
- 实际 DNS 地址和实际 TCP peer 都检查；连接到已验证 IP，同时保留原始 Host 和 TLS SNI。阻止 loopback/metadata/link-local、转换隧道地址和未允许私网；业务私网须显式配置，管理网应列入 denied_networks。
- 不跟随重定向，不使用环境 HTTP 代理，不自动获取返回链接，不将源服务 Cookie 变成下一用户的身份。
- 帧、JSON 深度、响应字节、工具数/分页、反向请求、并发和总耗时有界；不通过无限等候或自动重连恢复未知操作。
- 已知凭据的直接回显会被拒绝/遮蔽。这不是通用 DLP，也不能阻止一个已获准接收 Token 的恶意源服务在平台之外滥用它。

## 派发事实与故障

`preparing -> calling -> done`；明确未进入业务 RPC 为 `not_sent`，发送边界之后未确认一律 `unknown`。effect key 与固定输入/身份摘要绑定，不因新 HTTP 请求或 Worker generation 自动换含义。

`calling` 在发 tools/call 前持久提交。进程重启把 calling 变 unknown，不重跑；preparing 可证明业务 RPC 尚未派发。已完成结果可在当前授权仍有效时回放，不再次请求源服务。旧操作有潜在效果时，后续拒绝不能伪装成“从未发送”。

请求期间周期复核平台权限/lease/版本。撤权后中止当前等待、停止新增调用；已到达外部系统的效果不能倒退，unknown 仍进入平台核对流程。远端不支持/未确认 session DELETE 会明确记录，不能声称已销毁所有远端状态。

本地容量设硬上限（128 MiB 文件空间、10000 凭据历史、2000 调用记录）；达到上限失败关闭，不删除去重事实换容量。完整生产保留/压缩/共享存储方案仍待实施。

## 验证

```sh
python -m pip install -e 'services/connector-gateway[test]'
python -m pytest services/connector-gateway/tests -q
python scripts/platform/test_sandbox.py
python scripts/platform/test_connector_image.py
python scripts/platform/test_workbench.py
```

分别覆盖纯协议/加密/拒绝路径，真实 socket/TLS/官方 SDK，真实 PG/Worker/compute 数据来源，单独凭据镜像的启动限制，以及有限时长完整 HTTP 工作台。合成身份、模型、源业务数据不能作为公司真实系统接入证明。镜像 smoke 的网络为 none，只证明启动/权限配置；生产业务出口与 HA 另行验收。
