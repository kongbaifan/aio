# 05. 执行 cell、可信控制协议、网络与持久数据

> 关联 SBX-01～14、MCP-05、KB-03、OPS-01/02。此文把“按 Run 隔离”进一步精确到权限域；所有配置需在实际运行时验证。

## 1. 一个 Run 可包含多个不同权限 cell

| cell role | 执行内容 | 可读数据 | 可用凭据/网络 | 默认禁止 |
|---|---|---|---|---|
| compute | 模型生成的 Python/Node/文件计算 | 当前 Run 获权输入与私有工作副本 | 默认无长期业务凭据；限定包源/必要出口 | DB/管理网、connector Secret、任意宿主路径 |
| connector | 固定版本 stdio MCP/本地业务连接器 | 明确调用参数/最少输入 | 该连接的最小 scope 与固定 endpoint | 任意用户代码 exec、compute 整目录、其他连接凭据 |
| parser | 不可信 PDF/Office/压缩包等解析 | 单个批准上传/候选对象 | 默认无网无业务 Secret | 宏/外链/控制数据库/通用项目读写 |
| browser（profile/独立 target） | 网页交互 | 必要获权输入、专属 profile | 按网站/身份限制；必要登录需单独授权 | 共享 Cookie、全公司默认账号、宿主用户 profile |

可合并的前提是同一信任/权限域，不能仅因同 Run 就合并。V1 默认将 credentialed connector 与任意代码分开，不提供 compute→connector 文件系统读取或通用 exec。

### 1.1 为什么工具审批需要这层隔离

如果 compute 能读到 connector 的高权限 Token，又能直接访问同业务 endpoint，那么即使 ToolGateway 审批拒绝，任意代码仍可直接发请求。这时网关审批不是强制边界。

因此二者分 cell、凭据不下发 compute、网络只允许 connector 访问指定服务；compute 若需业务动作，通过绑定本 Run 的窄能力请求回到 Gateway。固定 connector 自身也要审核、最小权限和输出限制，因为被攻破的 connector 仍可能滥用它自己的权限。

普通容器同 Pod 共享网络 namespace 也可能留下绕路：必要时分 Pod/网络域、禁共享 PID/volume，不能只把进程放进两个 sidecar 就宣称隔离完成。

## 2. ExecutionTarget 与 SandboxSpec

```text
ExecutionTarget:
  role, target_slot, connector_binding_version? , task_scope

SandboxSpec:
  org_id, run_id, execution_generation, target_slot
  role, security_profile_id, image_digest
  input_manifest_ref, workspace_lease_ref?
  credential_capability_ref?    # 只适用于受信连接器，非通用 Key
  network_profile_id
  cpu_limit, memory_limit, pids_limit
  disk_bytes_limit, inode_limit, tmpfs_limit
  deadline_at, idle_expiry_at
```

安全字段来自批准 profile/连接器定义，不允许任意用户覆盖。客户端传 profile ID 时平台仍校验其权限。多 cell 的每一个都计入组织/用户/节点并发与资源预算。

建议内部接口：

```text
ensure_target(context, target_ref, approved_profile) -> TargetBinding
get_target(context, binding_id) -> verified lifecycle status
execute(context, binding_id, ExecutionSpec) -> execution handle/events
stop(context, binding_id, reason) -> stopping/confirmed stopped
destroy(context, binding_id) -> destroying/verified destroyed
```

幂等范围是 `(org,run,generation,target_slot)`，同键不同 digest/profile/输入权限拒绝。更新后的 `ensure` 仍可为纯 compute 默认 target_slot，但不能吞掉连接器身份差异。

## 3. 可信控制平面与不可信输出

### 3.1 信任划分

1. 外部 manager 使用固定模板创建/查询/销毁资源，拥有受控管理权限。
2. executor/connector 在 cell 中处理用户输入，应视作可能被其权限范围内的代码干扰。
3. stdout/stderr、工具返回 JSON、网页文本、用户生成文件都是不可信数据。
4. manager 通过运行时 API/主机隔离域核实进程退出、OOM、实际资源和销毁，不采信用户输出声明。
5. Artifact collector 在边界外核验获权挂载、类型/hash/大小/链接，不由沙箱自己签名承诺安全。

控制帧与 stdout 分流是必要的，但不是单独的安全边界。如果 runner 和用户进程同 UID、共享可写代码/IPC/可读取同一 fd，恶意代码仍可能影响 runner。因此 runner 的 `success` 最多是执行结果信号，不能授予权限、修改 lease、放行审批或认定资源已清理。

### 3.2 私有控制请求示例

```json
{
  "schema_version": 1,
  "request_id": "uuid",
  "binding_id": "uuid",
  "run_id": "uuid",
  "generation": 3,
  "logical_execution_id": "exec_0007",
  "entrypoint_ref": "approved-entrypoint-id",
  "input_manifest_ref": "immutable-input-manifest-id",
  "deadline_at": "2030-01-01T00:00:00Z",
  "output_policy_id": "bounded-standard"
}
```

该请求仍须已验证的服务身份/能力票据，JSON 中的 org/run 不构成授权。禁止 root、hostPath、任意 Docker flags、容器命令拼接、管理 Socket 路径等字段。

响应分为 manager lifecycle event 与 untrusted execution output 两种 schema；用户输出不能通过伪造 `event: approval.accepted` 或 `state: destroyed` 改管理状态。

## 4. 安全目录和权限

```text
/opt/runtime       固定镜像内容，非 runner 可写
/opt/skills        获权不可变包，只读
/inputs            该 target 最小不可变输入，只读
/workspace         compute 的 Run 私有副本，限定配额
/output            当前任务候选文件，限定配额
/home/runner       当前 target 私有，结束销毁
/tmp               私有临时空间，限大小并计入内存/磁盘
```

- connector 不挂整个 compute workspace，参数/附件用明确 object refs 输入。
- parser 只看到本次文档和输出位置，不给整个知识库原文目录。
- `/opt/runtime` 不像当前教学 Dockerfile 那样把所有 app 代码都赋给执行用户可写；固定执行程序由镜像构建身份拥有。
- 不挂宿主 `/`、`/etc`、`/proc`、`/sys`、Docker/Containerd socket、Kube token、SSH agent 或用户 home。
- 容器自身 `/proc` 等必须由所选运行时按 namespace/安全策略提供，不把宿主 proc 目录 bind 进去。

## 5. 配额实施矩阵

| 限制 | 实施层 | 证据/反例 |
|---|---|---|
| CPU/memory/PIDs | cgroup/等效运行时硬限制 + 调度准入 | 有界负载测实际上限和 OOM/PID 退出原因 |
| disk bytes/inodes | 经验证的 project quota/固定容量卷/等效存储后端 | 写到上限只影响本 target，宿主余量不耗尽 |
| tmpfs | size + memory accounting | tmpfs 增长计入内存，没有无限免费临时盘 |
| stdout/stderr | 增量读取、有界内存/日志、累计上限 | 无换行输出洪水不能撑爆控制服务 |
| files/zip/pages | collector/parser 限文件数/页数/解压比/层级 | 少字节压缩输入不能变成无限输出 |
| 执行时间 | manager 硬 deadline + executor soft timeout | Worker 崩溃后仍停止进程树 |
| 并发 | 用户/组织/profile/节点原子预留 | 8 个 Run 各带 3 cell 不能只计 8 个容器 |
| 网络连接/流量 | 按域出口、连接/响应上限、节点资源策略 | 允许一个域名不等于允许无限并发/外传 |

超限不解除保护；返回可解释错误并核对清理。Kubernetes ephemeral-storage 驱逐策略不自动等价于字节级硬配额，必须实测。

## 6. 网络图的具体约束

| source | destination | allow 条件 |
|---|---|---|
| browser UI | API | TLS+登录/CSRF/授权 |
| trusted Worker | manager | 服务身份+Run 当前代次+固定 spec |
| compute | ToolGateway 的受限调用入口 | Run capability+当前权限+ActionSpec/审批；无管理 API |
| compute | 包仓库 | 批准 profile/域/方法，安装仍无业务 Secret |
| compute | connector endpoint/业务数据库 | 默认拒绝；不能跳过工具网关 |
| connector | 对应业务 endpoint | 明确连接身份、最小 scope、方法/目标约束 |
| parser | 公网/内网 | 默认拒绝，不跟随文档外链 |
| 任意不可信 cell | control PG/Redis/K8s/metadata/其他 cell | 拒绝 |

URL 校验覆盖每次 DNS/连接/重定向、IPv4/IPv6/非标准表示；代理 env 可被代码忽略，所以主机/运行时层必须限制直连。

允许域名不解决所有泄露：一个合法聊天/文件上传网站也可接收敏感数据。外发仍需来源数据策略和业务动作约束，不能称 allowlist 本身完成 DLP。

## 7. 资源生命周期与收敛时间

1. manager 在数据库/受控容量账本预留 target 预算。
2. 创建卷/网络/容器，全部用 run/generation/slot 和实际 backend ID 标记。
3. 健康检查通过只代表 ready，不代表安全验收通过。
4. 执行 handle 受当前 lease 和硬 deadline 约束。
5. 取消/结束先禁止新派发并停止有关进程，收集候选在 writer 冻结后进行。
6. 销毁容器/卷/网络/凭据能力，外部运行时确认后标 destroyed。
7. 只有确认释放资源后减容量账本；清理失败仍占容量并告警/隔离，不假释放再超卖。
8. Reaper 双向核对 DB 与运行时，处理孤儿资源和失联 lease。

初始目标：普通本地任务取消后 P95 5 s 内停止；孤儿扫描可在 60 s 内收敛。只是测试目标，不是未验证平台的保证。控制面不可达时 manager 依据已签期限停止新任务并到期清理，不能无限延期。

### 7.1 预热与复用

可预热未放入任何用户输入/Secret 的空 cell。只要租给一个任务并运行了不可信内容，回收后销毁，不以清空 workspace、重置 Python 字典或删除 Cookie 当跨用户清洁证明。

## 8. 工作副本、收集与发布的精确边界

- Project 持久数据按不可变 WorkspaceVersion 保存，writer 用 Run 专属副本，不写已发布目录。
- 脚本或后台进程可能伪造任何输出，collector 必须停止/冻结 writer 后基于获权 mount 安全遍历。
- 路径校验不能只有 `resolve + startswith`；链接替换/硬链接/特殊文件需要安全句柄、no-follow/等效措施和隔离边界配合。
- 标准库读取到的文件名/MIME 不是可信事实；校验大小/hash/类型，原始名称只显示不用于对象 key。
- 候选对象存储是 immutable quarantine；TX-08 才打开 Artifact 可见性。
- 发布检验 generation、workspace head、当前权限、scan ready、来源限制；旧进程可以继续改它自己的临时副本，但不能发布覆盖新 head。
- workspace blocker 未解不能开始受影响的新 writer；它不是需要长期保留不可信容器的理由。

## 9. 数据面密钥泄漏的处置边界

如果某 connector 真的需要 Secret，应假定它可读取它；减少有效期/scope，并通过独立权限域减少其他代码接触。发生泄漏先撤销连接与相关 capability，核查外部访问，不能仅从 env 中删除变量就当凭据已失效。

Secret 文件是否只读不能阻止读取；HTTP header 是否未打印不能阻止同权限进程观察。真正边界来自独立进程权限/OS 隔离/网关代理和业务系统最小授权。

## 10. 本模块的验收证据

保存：实际镜像 digest、kernel/runtime、安全 profile、配额/DNS/网络规则摘要、manager 与运行时的资源清单、保护目录前后 hash、每 cell 的进程/volume 数量、取消与清理时间线。使用 ECASE-20～27 及原 SBXTEST/MCPTEST 相关场景。

测试必须在专用可销毁节点、合成文件和无生产凭据条件下完成。文档中写了 `cap_drop=ALL` 或“微 VM”不足以替代这些证据。
