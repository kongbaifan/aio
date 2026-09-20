# OAuth 增量：当前覆盖与差额

| 原任务 | 当前证据 | 仍需完成 |
|---|---|---|
| MCP-02 身份隔离 | OAuth 与 bearer 共用 Connection/Binding 权限；两用户 Worker 各用其 grant；刷新不替换 grant 身份 | 更完整连接限流/熔断/跨节点池治理 |
| MCP-03.01 配置与出口 | 固定 issuer/PRM/AS/JWKS/token/revoke/callback，实际地址与 TLS peer 校验，不跟随发现 URL 或重定向 | 更多供应商扩展与真实公司接入 |
| MCP-03.02/03.03 绑定与秘密 | 原 BFF session、state/code hash、PKCE、OIDC nonce/claims、resource/scope、独立加密 vault；没有平台 token passthrough | 可选供应商协议与全面 DLP/Secret 生命周期治理 |
| MCP-03.04 刷新 | per-grant 锁、token generation、持久 refreshing、丢回复 reauth、401 仅在业务前有限刷新 | 全局公平队列/供应商速率策略 |
| MCP-03.05 撤销 | 本地先拒绝、late refresh 不复活、RFC7009 已知 token 撤销、unknown/unsupported 明确区分 | 远端不明授权仍需源系统人工核对，不能假装可证明全部 grant 回收 |
| MCP-03.06 测试 | 回调跨用户/跨会话/重放/过期、claim/scope、刷新竞争、Secret 存储线程取消、HTTP 双身份链路 | 真实公司授权服务器、浏览器视觉、长期故障/HA Gate |

详见 [OAuth 可执行契约](../engineering/platform-mcp-oauth-contract.md)。Bearer/匿名和原 Skill/KB/Team/文件交接继续回归，没有用 OAuth 新路径替换掉原测试范围。

后续无网络 MCP stdio 专属执行单元已落地，见 [stdio 覆盖](stdio-slice-coverage.md)。下一主要功能路径是 stdio 受控联网/输入协作、可核对写/二进制结果、Skill 完整包和依赖治理、更多运行时与企业治理。完整目标保持 active。
