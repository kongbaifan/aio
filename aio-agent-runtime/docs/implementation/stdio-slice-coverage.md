# stdio 增量覆盖与明确差额

| 原任务 | 当前实现/证据 | 尚未交付 |
|---|---|---|
| MCP-05.01 | 固定 executable/argv、镜像/依赖声明/模板摘要、单独 env key 和资源 profile | 更多语言/供应商镜像的差量安全验证与发布运营 |
| MCP-05.02 | Run/discovery 持久 binding、私有 HOME/workspace、Docker exec stdio；模板+本次 Run 双 opt-in，最多 32 文件/4 MiB 的有界附件副本、无明文 journal/二次覆盖 | 活动 compute workspace 的进一步协作、跨节点输入后端；见 [附件输入](../engineering/platform-mcp-stdio-input-contract.md) |
| MCP-05.03 | bearer/anonymous 仅由 Gateway 输送到声明的独立进程；无控制凭据/host bind；UI风险说明 | 受控联网、短期凭据委派/更多身份方式 |
| MCP-05.04 | JSONL/UTF8、stdout与stderr区分、frame/queue/字节/期限限制，Manager不存原文结果 | 更细业务进度、专业诊断授权与完整日志治理 |
| MCP-05.05 | 同 Run 代次复用，跨身份/Run不复用；撤权/终止/故障清理，失联不盲重放 | 跨节点迁移、状态型会话跨代次恢复与HA |
| MCP-05.06 | 真实 SDK/Docker/PG/HTTP 的差量测试，配合既有 Python/Skill/KB/OAuth 回归 | 全量生产 Gate 与公司真实 MCP 系统UAT |

接口、部署、Node claim、停止事实和风险声明见 [stdio 契约](../engineering/platform-mcp-stdio-contract.md)。原 110 父任务/718 子任务和 G0–G6 没有因为本增量通过而全部标完成。

下一关键路径：受控运行时/依赖能力、MCP 可核对写和二进制结果，以及完整 Skill 包与企业治理；不把无网络参考服务器当作任意联网第三方进程已安全开放。
