# Docker 并发清理的幂等与确认契约

## 1. Scope / Trigger

适用于 `services/sandbox-manager` 的 compute、parser、Skill 与 stdio 执行 cell。HTTP stop/finalize、失联/到期回收和服务关闭可能同时清理同一绑定，不能假定每个 Docker 对象只有一个清理调用者。

后续复验又记录到同一容器 DELETE 的 **409 Conflict**，说明只处理“已经删除”的 404 不足以覆盖“另一路可能正在删除”的竞争。409 不能一律当成功：必须独立检查所属与当前状态，并最终确认不存在。

2026-09-13 的真实 HTTP 复验捕获：stdio 附件任务的业务调用已完成，但结束阶段为 `failed / RUNTIME_UNAVAILABLE / cleanup_state=clean`。受限诊断定位到 `stop_stdio → StdioManager.stop → SandboxManager.stop → DockerBackend.destroy → container.remove`，异常为 Docker **NotFound / HTTP 404**，不是 PostgreSQL 授权失败、安装失败或 MCP 业务 RPC 失败。

在检查与 DELETE 之间对象已消失。测试用另一个清理动作**真实删除已确认所属的 Docker 容器**，再让原调用执行 DELETE，旧实现稳定产生相同 404。证明该合法并发清理场景需要处理，不依赖增加 sleep 或偶然重跑成功。真实失败状态保存在 `workbench-docker-failure.json`；旧实现的确定性失败见 `manager-cleanup-before.xml`。

## 2. Signatures / Boundaries

```text
DockerBackend.checked(spec, container_id | None) -> owned Container | None
DockerBackend.stop(spec, container_id | None) -> None (confirmed stopped/absent)
DockerBackend.destroy(spec, container_id | None) -> None (confirmed container/volume absent)
DockerBackend._cleanup_lock(binding_id) -> per-binding RLock (cleanup only)
DockerBackend._confirm_removal_conflict(spec, container_id, error) -> None | raises
SandboxManager.stop(spec) -> {binding_id, state: "destroyed"}
```

`checked` 必须匹配 installation、binding、org、Run、generation、spec digest、role 与指定的完整 container ID。volume 名称来自绑定，不来自用户路径，并核对所属标签。没有扩大 stop 权限、增加宿主目录挂载、改变 CPU/内存/进程限额、修改批准镜像，或提供用户 Docker 参数。

## 3. Current Contract

0. 同一个 Backend 实例对同一 binding 的 stop/destroy 使用可重入清理锁，覆盖 API、回收与关闭路径；弱引用锁表不永久累积已结束任务。执行、RPC、导出及其他 binding 不持此锁；不把全局排队或业务脚本运行时间加到清理等待中。
1. get 与 reload 之间出现 `NotFound`，按当前对象不存在处理；不能继续用过期对象执行操作。
2. unpause 与其他停止动作竞争时，重新读取状态：已消失可结束；仍 paused 则保留原错误；已被另一个调用者 unpause 则继续停止。
3. kill 失败后继续核实当前状态：已消失/停止才确认停止；仍运行则保留错误。原有停止等待上限不变。
4. 对经过所属校验的容器/卷执行 DELETE，`NotFound` 可进入“可能已被另一清理者删除”的分支；**随后仍必须重新检查对象是否不存在**。
5. 容器 DELETE 的 409 只做状态确认，不重发 DELETE：若已不存在则继续清理；若仍为同一所属、`Status=removing` 且非 running，则在固定 5 秒窗口内等待不存在。仍在运行、状态不是 removing 或其他冲突保留原错误；窗口结束仍存在则 `CLEANUP_UNCONFIRMED`。卷的 409 不使用此分支，不能强删仍被引用的卷。
6. 假 404、超时未确认或其他删除错误不得标成功；权限/服务故障原样保留。
7. container 与 volume 均确认清理后，Manager 才更新 journal 为 destroyed/exported；不凭 DELETE 404/409 清空配额或状态。
8. 这不是业务成功判定。未知工具效果、未完成模型响应、来源撤权、未确认的其他执行资源和费用 hold，仍由原 Run 协议处理；不重放任何模型或业务 RPC。

stdio 的 PG 停止回执仍需独立提交，锁序和当前绑定检查见 [生命周期锁序](platform-stdio-lock-order.md)。物理清理完成不自动等于数据库回执或整段任务成功。

## 4. Validation / Error Matrix

| 情形 | 结果 |
|---|---|
| 第二清理者先删除已停止的同一容器 | 原 DELETE 可以 404；核实不存在、清理自己的卷，再返回成功 |
| 第二清理者先删除自己的卷 | 404 后再次 get，确实不存在才确认 |
| get/reload、kill、unpause 之间容器消失 | 依据不存在的观察完成该对象的停止，不输出假业务失败 |
| 已由另一个调用者 unpause | 重新读取非 paused 状态后继续停止 |
| DELETE 返回 404，但对象仍存在 | `CLEANUP_UNCONFIRMED`；journal 不标 destroyed |
| 同 binding 两条清理路径并发 | 只有一条执行物理 DELETE；另一条随后确认不存在，其他 cell 的清理仍能完成 |
| 容器 409，独立检查已不存在 | 确认该对象删除，继续自己的卷清理 |
| 容器 409，同一所属、非 running 且 status=removing | 只观察、不重发 DELETE；不存在后继续，否则固定期限后不确认 |
| 容器 409，但仍运行或并非 removing；卷 409 | 保留错误与未确认状态，不盲目重试/强删 |
| DELETE 出现其他 APIError | 原错误继续抛出；不能清空未确认状态 |
| 容器/卷所属不符、绑定/代次/id 不符 | 原所属校验继续拒绝；不删除其他任务对象 |
| 重复 stop，已确认对象都不存在 | 幂等返回；不重建容器，不重发业务动作 |

## 5. Good / Base / Bad

- Good：业务结果已确认，两条清理路径相遇；确认相同绑定物理资源均不存在，正常提交结束回执。
- Base：对象仍存在或 Docker 无法可靠确认；保留未确认状态和回收重试责任，不释放事实约束。
- Bad：catch 所有 DockerException 后无条件标 clean；或者为了避免竞争，把清理放进会等待任意业务脚本结束的全局锁。

## 6. Tests / Evidence

`services/sandbox-manager/tests/test_cleanup_races.py` 当前 **17 项真实 Docker 资源与定向故障注入回归**，覆盖原 10 项删除/消失/假 404/服务失败，以及同绑定清理串行、其他绑定不阻塞、409 后确认不存在、removing 的完成/超时、仍运行和不支持的冲突。原 404 用例先在旧实现稳定失败，见 `manager-cleanup-before.xml` / `manager-cleanup-after.xml`；新增 409 的独立不存在确认同样先在旧代码失败，再通过当前 17 项，见 `manager-conflict-before.xml` / `manager-conflict-after.xml`。等待负例只缩短测试常量，不延长生产等待窗口。

测试只操作本次安装 ID 与 binding 对应的容器/卷；继续运行原 Manager 所属校验、隔离和配额测试，以及平台/HTTP 的实际 stdio 与文件交接。合成诊断只记录类型、代码位置、HTTP 状态与任务状态，不保存原始异常正文、凭据或业务数据。

## 7. Wrong vs Correct / Remaining

```text
Wrong: get exists -> stop -> DELETE must succeed, otherwise the business task failed
Correct: verify ownership -> stop -> tolerate a DELETE NotFound -> independently confirm absence -> commit own cleanup fact

Wrong: every 404 or Docker failure means cleanup succeeded
Correct: still present -> unconfirmed; unrecognized DELETE failure -> propagate; unrelated ownership -> deny

Wrong: every 409 means another cleaner succeeded, or retry DELETE until it stops failing
Correct: serialize only this binding's cleanup; inspect known removing state; bounded wait for absence without another DELETE
```

更早的一次 `RUNTIME_UNAVAILABLE` 没有保留底层帧，不能把它强行归于同一原因。本修复证明已观察并确定性复现的删除竞态，不代表所有 Docker 故障、节点断电、存储故障、跨节点回收、未知内核问题或 HA/长稳 Gate 都完成。
