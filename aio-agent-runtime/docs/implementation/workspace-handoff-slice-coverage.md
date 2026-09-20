# 文件检查点交接增量：实际范围

> 对应 RUN-07/08/09/11、SBX 文件导出与 Workspace 单写边界的交叉部分，不把这些父任务或生产 Gate 整体标完成。

| 要求 | 当前实现/证据 | 限制 |
|---|---|---|
| 旧环境不交给新 generation 直接使用 | Manager 导出并销毁；新 binding/cell 从文件恢复；派发检查 workspace lease generation | 无 ready 检查点的活跃旧环境仍停止核对 |
| 同 Run 继续使用已完成步骤文件 | 独立私有快照，不建子 Run/子项目；多次快照选择最新 ready；真实 42→43 用例 | 文件 <=64、合计 <=8 MiB；不恢复进程/内存/HOME |
| 审批与重启不重复执行 | 保存原 invocation/cursor；审批决定竞争强制结束旧代次；ready 后 crash 恢复 | 执行中/半写/未知效果不是可盲目重试场景 |
| 不破坏共享项目版本 | 原 base_version 不变，暂停期间单写锁仍归 Run，最终 CAS 发布 | 不是多人并行写同一工作副本 |
| 不绕过权限与费用 | 原 Run Actor/来源/审批/预算/deadline，恢复前校验原 blob 字节；没有新免费模型预算 | 组织/部门财务与全供应商对账仍待治理 |
| 暂停不绕过存储额度 | 预留转移、已绑定 byte hold、恢复输出预留、知识/文件统一总额；SQL/JSON null 回归 | 跨节点存储/完整 orphan 与备份治理未完成 |
| 清理有证据不误删 | stop receipt 回写、ack 去掉旧 spec/cache、引用校验 GC，损坏/未知保留 | 不靠清理完成自动解除外部效果 blocker |
| 业务用户能查看进展 | 工作区事件、文件数量/大小、文件-only 提示；审批人无私有内容旁路 | 浏览器视觉和真实公司 UAT 尚待完成 |

实现签名、状态机、失败矩阵、测试与升级步骤见 [工作区文件检查点契约](../engineering/platform-workspace-checkpoint-contract.md)。

下一条完整平台关键路径转向 MCP OAuth/刷新与 stdio/批准写的完整生命周期、Skill 包与依赖治理、更多运行时和企业运维/数据保留。此增量不代表这些能力已实现。
