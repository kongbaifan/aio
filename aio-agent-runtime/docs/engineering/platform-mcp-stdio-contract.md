# MCP stdio 专属执行契约（无网络）

> 代码：Manager 的 `stdio_{contracts,process,service}.py`、Gateway 的 `stdio_{contracts,client}.py`、平台 `connections/stdio.py`；stdio 由 `0011_mcp_stdio` 引入，当前应用迁移为 `0013_shared_budgets`。
> 范围是同一 Run **代次**内的专属 MCP 进程，不是 API/Worker/Gateway 宿主 subprocess，也不是任意第三方程序的安全认证。

## 1. Trust / Scope

- 第三方 MCP 程序运行在独立 Linux Docker cell，使用 UID10001、只读根、无网络、独立 HOME/tmp/workspace、CPU/memory/PID/字节/inode 约束。
- UID10000 的 PID1 定时器独立于用户程序；MCP 进程不能延长其寿命。Docker socket/宿主目录/平台和网关管理凭据不进入 cell。
- **凭据型 stdio 进程及同单元代码可以读取它自己的注入凭据**。平台不能用上层工具白名单阻止恶意 server 在自身代码中使用整个凭据 scope；因此必须审核镜像，并使用最小范围凭据。当前 cell 无网，尚不作为任意联网业务连接器开放。
- 默认计算入口拒绝使用 stdio profile。stdio API 使用独立 Gateway→Manager token，不能拿普通 Worker compute token 调用。
- 同 Run/generation/connection 复用一个 MCP session；不同用户、连接或 Run 不复用进程/HOME/可变工作区。发现任务是独立短生命周期单元，不伪造业务 Run。
- 显式 Run 附件复制是独立的双 opt-in 能力：模板 `input_policy=run_attachments` 加上本次 `allow_stdio_attachments=true`；默认零文件。只接受所选附件的校验副本，不挂宿主或自动读取 Project head。完整边界见 [附件输入契约](platform-mcp-stdio-input-contract.md)。

## 2. Signatures / Persistence

```text
Operator StdioProfile:
  id,image_digest,executable,arguments,dependency_digest,credential_env?,network_profile=none,input_policy=none,
  memory/workspace/temp/home/PID/CPU/frame/stderr/session-output/deadline bounds

StdioSpec v1 (no inputs; original digest preserved):
  org_id,binding_id,target_kind(run|discovery),target_id,generation,
  connection_id,credential_ref,credential_revision,endpoint_id/endpoint_digest,
  profile_id/image_digest/template_digest,deadline,target_slot
StdioInputSpec v2: base scope + metadata-only input_manifest; aio-stdio-spec-v2 digest

Private Manager:
  POST /v1/stdio/open {spec,context,credential,input_files?}
  POST /v1/stdio/rpc {spec,context,request_id,method,params,timeout_seconds}
  POST /v1/stdio/stop {spec}
Private control: POST /internal/v1/connectors/stdio {operation:prepare|inputs|cleanup,payload}
Private Gateway: POST /v1/stdio/cleanup {org_id,run_id,generation} or bounded internal cleanup context
```

新增 `aio_mcp_stdio_leases`：Run/discovery 二选一，组织/连接/凭据版本复合外键，固定 spec/digest、deadline、state、manager_id/backend_id、close_reason；FORCE RLS。没有 token、可执行命令或 stdout/stderr transcript 列。

首个 Manager claim 将执行单元绑定实际 manager installation ID。其他节点不能把相同 logical lease 当成自己的进程并报告清理成功。跨节点 HA/迁移仍未实现。

回调遵守组织共享锁 → 固定资源锁序 → Run → stdio lease 的顺序，停止/事件写入不能反向等待 Worker 持有的 resource 行。此结构性锁不授予权限，失权后的 owned cleanup 仍可执行。确定性死锁回归和原理见 [锁顺序契约](platform-stdio-lock-order.md)。

Manager 复用统一 cell/memory/CPU 准入账本，stdio RPC 另外只记 request/result digest 与 sent/completed/unknown，不把可能含 Secret 的结果写到 Manager journal。已知结果只在 Gateway 的加密 effect journal 缓存。

## 3. Executable Contracts

### 3.1 发布与启动

1. 操作员构建固定镜像，提供完整依赖版本锁与 `aio.mcp.dependency_digest` image label，批准固定绝对 executable/argv。模板摘要覆盖镜像、命令、env key、依赖和资源限制。
2. Gateway/BFF Endpoint 只引用 profile/image/template digest；浏览器不能提交命令、shell、包名、工作目录、Docker flags 或任意网络配置。
3. 由当前获权 Run dispatch 或 Discovery 意图创建持久 lease；Manager 再独立验证当前 Actor、来源、连接、凭据版本、generation、deadline、节点和精确调用。
4. Manager 通过 Docker exec 启动固定 bootstrap，再在 cell 内 exec 已批准程序。**没有控制宿主 subprocess。**
5. scoped credential 通过 exec stdin 传递，不放进 Docker Config.Env/Cmd、不写宿主临时文件、spec/journal 或容器日志；启动 payload 和服务输出仅在有界内存处理。
6. Runtime 环境只能包含固定基础变量和模板指定的一个凭据 env key。禁止覆盖 PATH/HOME/解释器选项/平台管理变量。

### 3.2 协议与授权

- 使用 JSON-RPC 2.0 的逐行 UTF-8 stdio。初始化、notifications/initialized、tools/list、tools/call 是独立控制动作；工具名与 arguments 必须匹配已冻结的原调用。
- 初始化协商当前固定 `2025-06-18`。同进程已初始化时可复用该初始化结果；业务调用绝不重放。
- 第三方 stdout 是协议，不是任意日志；stderr 单独计量并丢弃，不向模型/审计回显可能包含 Secret 的日志。
- 每帧、每个 session 输出总量、stderr、队列、消息数量和 RPC 时间均有上限；大包按固定小块进入有界队列。未知 server-initiated requests 返回 method-not-enabled，不读取宿主 roots，不调用 sampling/elicitation。
- 发送前持久化 request intention。一旦可能发送，响应丢失/超时/进程退出不以新 request_id 重跑同一动作。相同 Manager RPC ID 再次提交返回 `STDIO_RPC_ALREADY_SENT`；Gateway 有已提交密文结果才可复用。
- 帧/工具结果始终是不可信数据，不能把其中的 `state=destroyed` 当作真实生命周期证明。

### 3.3 生命周期

- Run 完成/失败/取消或审批挂起前，MCPDriver 请求回收该代次的 credential-bearing processes；确认停止后才可最终发布或释放相应执行边界。
- Manager 独立检查 deadline/当前控制授权；撤权、旧 generation、进程故障、配额失败会停止实际容器与卷。
- 正常 cleanup 先把 lease 标为 stopping，确认后 close_reason=requested。异常丢失为 lost；Worker 恢复看到 lost 状态不新开进程并继续旧 cursor，转入核对。
- 进程状态只在同一运行代次中保留。审批/换代次会结束该进程，不能把文件检查点当作 MCP 事务/内存恢复。
- 只回收已经确认属于本 Manager 的 binding；节点不匹配、Docker 不可达、清理未确认继续保留状态和 blocker，不对外谎报成功。
- 长期 journal/metadata 达到配额会拒绝新分配；per-binding 临时锁使用弱引用，不因历史 binding 无限累积锁对象。

## 4. Configuration / Deployment

新增 Manager 配置：

- `SANDBOX_STDIO_PROFILES`：独立、绝对路径的批准模板 JSON，最多 8 个模板；ID 不与普通 compute 冲突。
- `SANDBOX_CONNECTOR_TOKEN`：只用于 stdio 私有 API，必须与 `SANDBOX_MANAGER_TOKEN` 不同。

新增 Gateway 配置：

- `CONNECTOR_STDIO_MANAGER_URL` / `CONNECTOR_STDIO_MANAGER_TOKEN`：批准的私有 Manager。配置了 stdio Endpoint 却没有专属 Manager 时启动失败；不使用本机 fallback。
- Endpoint 的 `transport=stdio`、`url=stdio://<profile_id>`、`stdio={profile_id,image_digest,template_digest,credential_env,network_profile}`。当前支持 opaque bearer/anonymous 注入；不将 HTTP OAuth metadata 自动挪用成 stdio 授权。

参考镜像和测试：`services/mcp-stdio-runtime/`，实际 profile 输出在 `var/verification/stdio-profile.json`。可用以下操作员工具生成双方一致的引用，它不执行 MCP 程序：

```powershell
.\.venv\Scripts\python.exe scripts/platform/export_stdio_endpoint.py `
  --profiles var/verification/stdio-profile.json --profile-id stdio-reference `
  --endpoint-id company-stdio --read-tool identity `
  --output var/verification/stdio-endpoint.json
```

升级需先停/排空旧 Worker，迁移到 v11、刷新 runtime grants，同步升级 API/Gateway/Manager；不可混跑不理解 stdio lifecycle 的旧 Worker。

## 5. Validation & Error Matrix

| 情况 | 行为 |
|---|---|
| profile/image/template/依赖声明不符 | 不启动，`STDIO_TEMPLATE_NOT_APPROVED` / dependency mismatch |
| 普通 compute token 请求 stdio | 401；stdio token 也不能请求通用 compute API |
| 缺专属执行器 | `STDIO_EXECUTOR_UNAVAILABLE`，不转 host subprocess/HTTP |
| Spec、连接、凭据、Run/generation、节点变更 | 拒绝，不读别人的 HOME/结果 |
| 同 RPC 身份重复发送 | `STDIO_RPC_ALREADY_SENT`，不再次执行业务函数 |
| stdout 非 JSON/过长、stderr 洪水 | 有界失败、停止 cell，不回显日志 |
| RPC/管道写阻塞 | 有界超时，外部回收进程，不让 Manager 长时间锁死 |
| Manager 重启失去 socket | quarantined / lost，不采用旧会话 |
| 未确认进程清理 | Run/项目保持受控状态；不能清 blocker 或发布为全部成功 |

## 6. Good / Base / Bad + Tests

- Good：同 Run 两次 identity 调用的 server instance 相同、counter 连续；第二个用户得到不同进程与 token 摘要，HOME/workspace 中看不到对方文件。
- Base：无网络只读 stdio 服务；每次发现完成即回收，Run 内复用到终止；凭据仅作为该进程已声明的最小能力。
- Bad：把 stdio 当 `subprocess.Popen` 在 API/Gateway 宿主跑；将实例池跨用户/Run复用；错节点报告旧容器清理完成；把 MCP stdout 自报当作停止证明。

证据：Manager `test_stdio.py` 使用真实 Docker 与官方 MCP SDK，检查身份/文件/环境/secret/log/journal/协议/洪水/超时/重复执行；平台 `test_stdio_integration.py` 使用真实 PG+Gateway+Manager+Docker，检查 Worker、来源、节点/参数绑定与异常恢复；HTTP 工作台含两用户 stdio 发现、运行与销毁；UI 测风险声明与没有宿主命令表单。

## 7. Wrong vs Correct / Limits

```text
Wrong: put credential into Docker environment/argv or persist the entire stdio response
Correct: transient exec stdin + private Gateway vault; Manager retains only bounded lifecycle/digests

Wrong: same Image/Endpoint means two users can share a stdio process
Correct: org + Run/discovery + generation + connection + authorization binding scope

Wrong: output flood or worker restart -> recreate server and replay
Correct: bounded queues/timeouts + externally verified teardown + honest unknown/lost state
```

当前只有 **无网络** profile。双 opt-in 的显式 Run 附件复制已实现；受控联网出口、活动 compute 工作区协作、其他语言镜像的差量隔离验证、进程状态跨代次恢复、跨节点/HA、可核对业务写、二进制产物导出和完整保留/支持治理仍未完成。凭据注入风险不能被称为与无凭据 compute 同等信任级别。完整企业平台目标仍在实施。

并发结束/回收时的 Docker 404、独立不存在确认和非 404 错误保留见 [Docker 并发清理契约](platform-docker-cleanup-contract.md)。确认容器/卷已清理不代替业务结果、PG 回执或未知效果核对。
