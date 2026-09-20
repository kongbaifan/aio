# 企业 Agent 工作台

React/TypeScript Web 连接真实 `/api/v2`，不是旧 Harness 调试页。当前支持 SSO、获权 Agent、私有会话、持久任务、审批、项目文件、显式共享、个人用量和组织管理。尚未实现的能力不伪装成可用功能。

共享 Skill 页面已接入私有草稿、隔离验证、指定不同管理员审核、固定版本与部门/个人授权。支持 instruction-only 或显式 JSON 文本能力包；ZIP、二进制依赖与任意安装命令不在当前支持范围。

依赖不作为用户二进制包上传到 API。现在可选择操作员签名批准的固定 NumPy/Pandas 镜像，导入带 exact dependencies/runtime digest 的 v2 文本 Skill；环境版本和摘要在管理台可见，实际验证仍在隔离 cell。示例与构建/签名部署见 [依赖运行时契约](../../docs/engineering/platform-dependency-runtime-contract.md)。同一 Agent 的主计算工具不能混用不同 profile；需要其他包时走受信 CI/审批流程，不在页面执行 pip/npm/apt。

“我的连接”和“MCP 服务”已接入只读 Streamable HTTP MCP 与固定模板的隔离 stdio：管理员登记固定服务、发现并审核工具，使用者配置自己的 Bearer/匿名连接或获权的部门服务身份。保存凭据后还需连接检测；Agent 只分享工具定义，不借用创建人的个人 Token。HTTP OAuth 授权码/PKCE、会话绑定回调、自动刷新与有条件远端撤销已接入。stdio 当前只支持无网络 profile，会明确提示隔离第三方程序可以读取它获授的凭据；不提供宿主安装/命令表单。受控联网、真实业务写和二进制产物导入仍未启用。操作员需先登记 OAuth client 和端点，界面不会要求用户粘贴 refresh token。

“知识库”已接入六种文档格式的隔离摄取、受限/继承权限、版本更新、关键词预览、Worker 混合检索和文档引用。默认受限文档不会随知识库公开。嵌入模型与未知费用核对在管理中心配置；浏览器预览不调用收费模型。

管理员发布 Agent 时可明确启用 Team 并限制步骤/轮数。对应会话提供“直接执行 / 多步骤协作”选择；右侧显示服务端持久步骤，规划和步骤文字不混入最终回答。各阶段共用预算和来源授权。安全审批边界可保存私有文件并在新代次恢复新环境，但不接管旧进程或内存；无完整检查点仍停止核对。详见 [Team 契约](../../docs/engineering/platform-team-contract.md) 与 [文件交接契约](../../docs/engineering/platform-workspace-checkpoint-contract.md)。

## 构建与部署

在项目 `aio-agent-runtime` 目录运行（Windows 使用 `npm.cmd`）：

```sh
npm ci --prefix web/platform
npm run format:check --prefix web/platform
npm test --prefix web/platform
npm run build --prefix web/platform
```

- 锁文件与精确版本一并保留；`dist`、`node_modules` 不提交。
- API 的 `PLATFORM_WEB_DIST` 指向 `web/platform/dist` 绝对路径；默认从显式项目根或可识别项目根查找。
- API 在 `/`、`/app`、`/app/*` 提供 SPA，`/assets` 提供构建资产；回退不吞掉 `/api`、旧执行接口或未知服务端路径。
- Web/API 同源，使用 HttpOnly BFF Cookie。前端构建变量不放 IdP/模型密钥。
- 反向代理终止有效 HTTPS，保留 SSE，不缓存认证 API/事件/文件。不得把旧 Harness 端口当备用后端。
- IdP 注册回调必须等于 `PLATFORM_PUBLIC_ORIGIN + /auth/callback`；登录组织 ID 来自 bootstrap，不按邮箱猜测。
- Vite 仅用于本机代码调试，不是生产认证/代理配置的替代品。

## 首次配置

1. 操作员设置独立 PostgreSQL 迁移账号，执行 `python scripts/platform/manage_platform.py migrate`。
2. `bootstrap --organization-name <名称> --admin-subject <IdP精确subject> --admin-name <姓名> --runtime-role <账号>` 创建组织/首位管理员和 runtime 账号。需要环境变量 `PLATFORM_MIGRATION_DATABASE_URL`、`PLATFORM_RUNTIME_DATABASE_PASSWORD`、`PLATFORM_OIDC_ISSUER`；不要把密码放命令参数。
3. 现有组织升级只执行 migrate 和 `refresh-runtime-grants --runtime-role <账号>`，不重新 bootstrap。
4. 配置 `PLATFORM_LOGIN_ORG_ID`、OIDC、Web 路径及 [API](../../config/platform.env.example)/[Worker](../../config/platform-worker.env.example) 环境。平台不自动加载旧 `.env`。
5. 部署 API、Worker、独立 sandbox-manager；只有 Manager 持 Docker 权限。
6. 管理员预登记成员、建立部门、注册操作员允许的模型 origin/凭据变量名和 Python profile，再创建不可变 Agent。
7. 设置员工预算，显式授权 Agent 及依赖，可按部门共享。撤销 Agent 不自动撤销模型/工具的独立授权。
8. 员工创建私人项目/会话。分享项目不自动分享私人会话；org_admin 不默认通读私人内容。

共享 Skill 的示例流程：在“管理中心 → 共享 Skill”创建说明或导入 [`example-calculation.json`](../../config/skill-packages/example-calculation.json)，选择固定 profile，指定另一位有效组织管理员，等待验证与环境清理完成，再由审核人确认发布。创建 Agent 时选择具体 Skill 版本，随后显式授权依赖。完整边界见 [Skill 契约](../../docs/engineering/platform-skill-contract.md)。

完整边界见 [管理台与 Web 契约](../../docs/engineering/platform-admin-web-contract.md)。

## API 契约与本机验证

```sh
python scripts/platform/export_openapi.py
npm run api:types --prefix web/platform
npm audit --prefix web/platform --registry=https://registry.npmjs.org --audit-level=moderate
```

`src/api/generated.ts` 由实际 OpenAPI 生成，请求表单使用这些类型；响应投影仍有手写类型，不宣称全接口双向强类型生成。

安装平台/manager 依赖、启动 Docker，并先完成 `python scripts/platform/test_sandbox.py` 生成已验证 profile，然后：

```sh
python scripts/platform/test_workbench.py
# 可选：手动有限时长预览，默认回环 8120/8121/8122/8123
python scripts/platform/preview_workbench.py --lifetime 900
```

预览使用**合成 IdP/模型/MCP 源数据**，但真实运行 OIDC 签名/PKCE、PostgreSQL、Worker、独立网关 API/授权回调、Docker 和文件产物。提供四个合成身份；销售/财务使用同一 MCP 定义但各自的连接身份。不能用作生产认证，也不证明公司真实系统已接通。服务按生命周期或停止文件退出，清理仅处理自身标签的资源，不动其他工作负载。

新增安装依赖：`python -m pip install -e 'services/connector-gateway[test]'`。MCP 部署需独立私有服务、凭据卷和密钥，详细配置见 [网关说明](../../services/connector-gateway/README.md)。不要在 API/Worker 环境配置 vault master key。

stdio 部署另需 Manager 的 `SANDBOX_STDIO_PROFILES` / `SANDBOX_CONNECTOR_TOKEN` 和 Gateway 的专属 Manager URL/token。`test_sandbox.py` 会生成 `stdio-profile.json`，本机 HTTP 预览提供两用户的“隔离进程资料助手”；这只是合成参考服务，不代表任意供应商镜像/联网出口已经验收。进程隔离、凭据风险及清理语义见 [stdio 契约](../../docs/engineering/platform-mcp-stdio-contract.md)。

需要本地文件的 stdio 模板还必须由操作员批准 `input_policy=run_attachments`。使用者在对话添加文件后，单独勾选“允许隔离 MCP 读取本次所选附件”；默认不勾选，最多 32 个/合计 4 MiB。改动附件或切换会话会复位，丢失提交回复时重试仍锁定原授权。只复制本次明确选中的文件，不共享宿主目录、项目其他文件或运行中的 compute workspace。详见 [附件输入契约](../../docs/engineering/platform-mcp-stdio-input-contract.md)。

文档验证还需要 `python -m pip install -e services/document-parser`。运行 `test_sandbox.py` 会生成 `document-profile.json`；部署的 API `PLATFORM_DOCUMENT_PROFILES` 与 Manager 要分别批准同一 parser image。v7 要求安装 pgvector 的数据库，不使用旧 plain-PostgreSQL 镜像冒充向量检索可用。知识库与原文/费用约束见 [知识库契约](../../docs/engineering/platform-knowledge-contract.md)。

Web 测试覆盖身份切换迟到响应、CSRF、严格 SSE/去重、稳定幂等键重试、管理权限、Markdown XSS 和共享确认。真实 HTTP 测试另外验证多个身份、权限、执行、预算与文件；**HTTP/jsdom 都不是浏览器视觉 QA**。当前浏览器视觉检查仍未完成。
