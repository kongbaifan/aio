# 私有工作区文件检查点与执行代次交接

> 代码：`app/workspaces/{checkpoints,exports,references}.py`、`app/execution/`、`runtime/{execution,worker,service}.py`；Manager 新增 checkpoint 操作。
> 迁移：`0009_workspace_handoff`。本文描述文件交接，不承诺进程快照、任意时刻无损恢复或生产 HA。

## 1. Scope / Trigger

适用于一个 Run 已执行 Python/Skill 计算，后续命中持久 R2 审批，需要释放 Worker 与计算资源的情况。Single 和 Team 复用同一机制。

- 只保存 `/workspace` 下经 Manager 校验的普通文件；不保存 Python/浏览器内存、后台进程、HOME、系统目录或任意安装状态。
- 旧 cell 在导出后确认销毁；恢复使用新 generation、新 binding、新容器。不是重用旧 generation 或放宽旧 permit。
- 文件检查点独立于 `Artifact` 和已发布项目版本，不在等待审批时推进 project head，不成为用户可猜测的下载 URL。
- 当前支持明确的审批安全边界；已完成文件检查点之后、释放租约之前的 Worker 丢失可恢复。执行中丢失、未完成导出/写入、未知外部效果仍需核对，不回滚到旧文件后重放工具。

## 2. Signatures / Persistence

```text
WorkspaceCheckpointStore.begin(handle) -> no active compute | bound checkpoint intent + original CellSpec
WorkspaceCheckpointStore.authorize(c,run,spec) -> exact quiescent boundary authorization
WorkspaceCheckpointStore.accept(handle,id,manager_result) -> ready filesystem checkpoint
WorkspaceCheckpointStore.resume(handle) -> verified new-generation workspace lease, no code execution
WorkspaceCheckpointStore.inputs(handle,profile?,image?) -> verified file bytes | no checkpoint input
WorkspaceCheckpointStore.assert_operable(c,run) -> reject unverified/pending/same-generation handoff
WorkspaceCheckpointStore.mark_acknowledged(org,id) -> purge receipt + retire old spec payload
WorkspaceCheckpointStore.gc(org,limit=20) -> purged checkpoint IDs
maintain_once(checkpoints,manager_client,org) -> owned cleanup confirmation / ack / GC
ExecutionStore.suspend_approval(handle) -> waiting_approval | queued | None

Manager POST /v1/cells/checkpoint {spec: CellSpec} -> binding_id,spec_digest,state=destroyed,files
Manager POST /v1/cells/acknowledge {spec: CellSpec} -> binding_id,state=acknowledged
```

新增 `aio_workspace_checkpoints`：绑定 org/run/project、原 generation、engine checkpoint seq/digest、原 cell、审批 invocation、base_version、profile/image/spec digest、五类来源、文件 manifest/digest、存储预留、ready/ack/purge 事实。Actor 继承不可变 Run 身份，不由新 Worker 自选。

`aio_workspace_leases.resume_checkpoint_id` 使用 org/run/project 的复合外键。Run/project 与 cell/run 额外唯一约束保证关联范围；检查点表 FORCE RLS，有维护队列与有效存储 hold 索引。旧 schema v1～v8 不改，Checkpoint v1 payload/hash 不改。

```text
preparing -> bound -> ready -> retiring -> purged
             |
          中断/不确定 -> Run recovery_required，保留意图、费用事实和存储 hold

workspace lease: active -> checkpointing -> checkpointed
next generation: checkpointed -> active(新 cell) -> staged -> released
无后续计算:      checkpointed -> staged(从已确认文件) -> released
```

## 3. Executable Contracts

### 3.1 暂停边界

1. 必须是已提交的 tools checkpoint，当前 logical tool 为 R2、存在持久 Approval，invocation 尚未发送。`process_state_dependent` 不进入文件交接。
2. 不存在 started/unknown 模型或未确认工具效果；仍持有当前有效 Worker lease，当前 Actor/来源权限有效。
3. 建立检查点意图后，将现有 8 MiB 工作区输出预留转移到检查点，不重复计数，也不先释放再无额度写入。
4. Manager 独立验证 checkpoint 授权；普通 finalize 仍仅允许最终汇总，不能用中间步骤的 final checkpoint 提前结束工作区。
5. Manager 按既有隔离导出规则冻结/读取普通文件并销毁 writer；拒绝活动执行、链接、特殊文件、越界路径与超额输出。API/Worker 不自行解压用户目录或执行文档/代码。

### 3.2 提交文件

- 最多 64 个文件，总字节数 <= 8 MiB；校验路径、唯一性、严格 base64、整数 bytes 与实际 SHA-256。排序后的 manifest 有独立摘要。
- 在任何持久 blob 写入前，先提交不可变 manifest 与真实字节 hold，状态为 bound，同时记录已确认停止的 cell。
- 随后的**有界本地 blob 写入和 ready 提交持有同一个组织存储锁**，与 GC 串行。它们不含网络、模型、容器调用或用户代码执行。
- 这避免取消 `asyncio.to_thread` 后，底层写线程迟到把 GC 已删除的对象重新写成无引用文件。失败则保留 bound manifest/hold，不能当作 ready。
- ready 事务要求同一 engine checkpoint、writer/base、generation，并确认该 Run 没有剩余活动 cell。此前已完成步骤和参数不重生成。
- 新 ready 检查点可以使此前快照 retiring；只有新快照完整提交后才切换恢复指针，不把失败的候选当作新真相。

### 3.3 审批竞争与换代

- 正常情况下，Job=`waiting_approval`，lease_owner 清空，Worker 返回。
- 如果审批在保存文件期间已经被决定，仍将旧 Job 重新排队并结束原代次，不在被销毁的环境上继续执行。
- 新 Worker 先核对 binding、engine checkpoint、manifest、原文件字节、当前来源权限、原 project head、存储额度与旧 writer 停止事实，再把工作区 lease 交给新 generation。
- 调度/派发边界还校验 workspace lease generation，不能绕过 `load/resume` 直接准备模型或工具。
- 新 Python/Skill cell 的 profile/image 不能改变；后续调用若只有文字/远端动作，最终可直接从已确认快照构建产物，不为导出多开一个容器。
- 全过程使用原 Run 的预算、审批 ActionSpec、逻辑 operation key、取消与 deadline。文件交接不重置模型 round，也不延期。

### 3.4 来源、配额、清理

保留并重新检查：`provenance_source_ids`、`capability_source_ids`、`capability_read_source_ids`、`mcp_source_refs`、`knowledge_source_refs`。恢复合并到 Run，不能因重建消息或环境丢失来源。

- checkpoint hold 计入组织/项目文件配额，也计入知识库上传的组织总配额；恢复时另外预留下一次输出，不能把旧快照当免费缓存。
- 暂停期间项目 writer 仍逻辑属于原 Run，其他 Run 不获得其可变工作区。排队交接被取消时释放 writer，并退休检查点。
- ready 后 acknowledge 可清除 Manager 的导出/command result 缓存；确认后旧 PG CellSpec 清空，恢复依赖 checkpoint manifest 与批准 profile，而非旧 spec 里的输入副本。
- ack 是幂等清理，可重试，不重放用户命令。损坏的检查点元数据不自动删除它的恢复副本。
- 后台维护会请求停止过期代次或已停止/需核对 Run 的**确切自有 cell**，并把 Manager 的停止事实回写 PG；不会因为计算清理完成就自动解除未知效果 blocker 或把任务改成功。
- GC 在组织存储锁下校验摘要与当前引用。引用包含知识版本、Artifact、上传意图、workspace export/version、其他未 purged 文件检查点；相同 hash 仍有引用就不删除。
- 未确认 ack、仍需恢复的快照、元数据损坏或待核对状态，不静默释放对应 hold。正常清理保留必要元数据/审计，不宣称所有历史文本、备份与供应商副本已经物理删除。

### 3.5 API / Web

`GET /api/v2/runs/{id}.workspace_checkpoint` 仅在原 Run/project/session/来源授权后返回 id、state、generation、engine_checkpoint_seq、file_count、bytes、`preserved_state=filesystem_only`、manager_acknowledged。

不返回原始 manifest、CellSpec、命令、凭据或内部下载地址。审批人能决定获权动作，不因此获得私人 Run/工作区读取权。

创建、提交、ack、恢复、清理事实对应事件及 Run revision；迟到的同一视图请求不能覆盖新投影。Web 显示“计算环境”而非把停止 cell 误称所有数据已删除，并明确提示仅保留文件。

## 4. Validation / Error Matrix

| 情况 | 行为 |
|---|---|
| 当前不是安全审批边界/有进程依赖 | `WORKSPACE_NOT_QUIESCENT`，不声称已保存进程 |
| live cell 却缺 checkpoint hook | `WORKSPACE_CHECKPOINT_REQUIRED`，不释放后继续执行 |
| 未完成检查点 | `WORKSPACE_CHECKPOINT_PENDING`；失败恢复保留 hold，不重放 |
| 未执行新代次恢复校验 | `WORKSPACE_HANDOFF_REQUIRED`，阻止模型/dispatch |
| 新 Actor、Run、project、cursor、digest 不符 | `WORKSPACE_CHECKPOINT_INVALID/CONFLICT` 或旧 lease 拒绝 |
| 原来源撤权/知识版本或连接版本失效 | 原来源权限错误；新模型/远端动作前停止 |
| 文件缺失/损坏 | `BLOB_UNAVAILABLE/INTEGRITY_ERROR`，不从旧工具重算 |
| project head 改变 | `WORKSPACE_CONFLICT`，不覆盖别人版本 |
| 新 profile/image 不符 | `WORKSPACE_PROFILE_CHANGED` |
| 存储不足 | `STORAGE_QUOTA_EXCEEDED`，不越额写入 |
| 旧活跃 cell 没有可用检查点 | `PROCESS_STATE_LOST`，清理与核对，不直接采用旧环境 |
| 同一导出在 checkpoint/finalize 间换用途 | Manager `EXPORT_PURPOSE_CONFLICT` |

## 5. Good / Base / Bad

- **Good**：第一步写 42 → 保存并销毁 cell1 → 另一人审批 → cell2 读取 42 → 发布最终产物。原计算和已批准远端动作都不重复发送。
- **Base**：审批后不再计算，仍能从检查点发布此前合法文件；拒绝/过期不会执行 R2，输出和失败状态分别保留。
- **Bad**：第一次快照 42、第二次快照 43；第二次恢复失败就使用 42 继续旧 cursor。这是文件回滚与效果重放，禁止。
- **Bad**：Manager 已销毁，回复/写入落库丢失，就凭没有活动容器标为已恢复。必须有完整 ready 证明；否则仍要核对。

## 6. Tests / Evidence

- `test_workspace_checkpoint_contracts.py`：有界文件、二进制、路径/编码/hash/重复、作用域及所有来源字段绑定。
- `test_workspace_handoff.py`：真实 PG/Manager/Docker 的审批后新 cell 恢复、无后续计算导出、拒绝/过期、并发决定、ready 后 Worker 丢失、多次快照/GC、源撤权/损坏/配额/head 冲突、未完成写不恢复、取消与写租约释放、丢回应后清理但不解除 blocker、跳过恢复的派发拒绝。
- `test_workspace_receipt_lock_order.py`：真实停止的 cell、丢失 PG ack 与并发 Worker 资源锁；ack/compute 观察遵循组织→资源→Run 顺序，组织停用仍可清理，各种清理事实不能互相冒充。旧实现已由 NOWAIT 回归稳定检出，详见 [生命周期锁序契约](platform-stdio-lock-order.md)。
- Manager `test_checkpoint_export_is_private_purpose_bound_stopped_and_idempotent`：私有 API、同用途幂等、不可换用途、停止与缓存 ack。
- Web 测工作区事件触发授权投影刷新；HTTP 验收增加真实计算→签名 SSO 第二身份审批→新代次恢复→下载 42。R2 是明确合成回执，**不证明真实业务写入或外部系统 exactly-once**。

## 7. Wrong vs Correct / 本轮教训

```text
Wrong: export_manifest IS NULL recognizes every Python None written by SQLAlchemy JSONB
Correct: v3-v8 may contain JSON null; unbound_manifest accepts SQL NULL and JSON null, but NOT []

Wrong: old actor authorized + no live container = free to resume
Correct: a ready immutable snapshot, current sources, byte verification and new-generation lease are all required

Wrong: cancel an asyncio wrapper, free the hold, let its background blob writer finish later
Correct: bounded local writes and GC share the storage lock; incomplete durable intent keeps its hold

Wrong: cleanup/ack metadata changes with the same Run revision
Correct: monotonic revisions for observable facts; repeated acknowledgements are no-ops
```

JSON null 问题属于跨层语义遗漏，真实排队取消测试暴露 writer 未释放；修复同时覆盖正常终结的存储 hold，不只修改单个断言。新的 None 写入使用 SQL null，兼容读取仍保留旧 JSON null 处理。

## 8. Deployment / Remaining

升级前停止新任务并排空/停掉旧 Worker，备份后迁移至 v9、刷新 runtime grants，再同步启动新版 API/Worker/Manager。Manager journal 在独占锁内增加导出用途字段；旧导出默认按 finalize 解释，不转换成 checkpoint。缺新端点不降级旧环境采纳。

仍未实现：任意运行中进程快照、跨节点 Blob/S3/KMS、全量历史/备份保留治理、所有故障的自动续跑、真实公司审批写系统验收及生产 HA/长稳 Gate。完整企业平台仍在实施。
