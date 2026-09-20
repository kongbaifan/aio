# 本轮 Skill 增量相对完整规划的覆盖与缺口

> 规划文件保持原设计快照；这里说明实际代码覆盖，不把 718 子任务或任何完整 Gate 批量勾选。v1 文本包、v2 固定依赖环境与隔离 ZIP/TAR/TAR.GZ 导入均是可运行路径，不是缩减后的最终目标。

| 规划 | 本轮实际覆盖 | 仍缺少/不能据此放行 |
|---|---|---|
| CAP-03.01～02 | 显式文本 manifest、服务端规范摘要、不可变 DB 内容、owner/org/resource、私有草稿；归档 quarantine/上传/hash/配额/租约/清理协议 | 完整依赖/网络/分类申请模型；任意二进制资产 |
| CAP-03.03～04 | 受限路径/大小/数量、引用存在、固定 image、隔离 Python AST 与入口测试；新增依赖构建见下一行，不在控制进程执行 metadata | 专业 malware 和来源许可证审核体系、完整发布运营 |
| SBX-03 / CAP-03.04 依赖增量 | 固定 wheels/哈希锁、隔离离线安装、包清单/闭包/CycloneDX SBOM、Ed25519 镜像批准、v2 兼容与实际环境检查；见 [依赖契约](../engineering/platform-dependency-runtime-contract.md) | 完整 Registry/签名/漏洞/许可证运营和构建节点生产 Gate；不能把签名当作无漏洞保证 |
| CAP-03.05～06 | 私有作者/指定审核人、持久步骤/错误、重复版本拒绝、恶意归档矩阵、路径、输出洪水/超时/中断/读越权测试 | 更多解析器/二进制格式和扫描质量 Gate |
| CAP-04.01～04 | 新版本读取器不调用 legacy 全局目录；read/use/tool 权限分离；固定路径和摘要；旧 registry 保持兼容；native `SKILL.md` 单目录转 instruction-only 草稿 | 自动 frontmatter 元数据语义、批量旧库迁移、跨包/跨模块依赖、部门命名空间和链接型内容 |
| CAP-04.05～06 | 指令有字节限额、引用按需读取、当前授权与撤回、新旧版本隔离、真实运行入口不受同名 workspace 文件替换 | 按 token 的上下文预算、完整长上下文裁剪、原规划全部同名包/兼容场景 |
| CAP-05.01～03 | draft/validating/validated/rejected/published 与独立 active/disabled；验证队列/lease/generation、合成输入、镜像/命令/结果摘要、确认清理 | 完整 deprecated/灰度状态、逐测试资源指标/产物保留、其他执行 profile |
| CAP-05.04～05 | 指定不同 org_admin 审核、当前 author/reviewer/profile 复核；工具和发布状态原子提交；Agent 固定版本引用 | 业务审批角色/多级风险审核、灰度 scope、真实业务责任人验收 |
| CAP-05.06～07 | 当前禁用阻止调用及派生数据读取；旧命令/输入不能换内容；未知清理不自动重跑/发布；恢复 fence | 批量安全事件工作流、完整发布竞争/灾难恢复矩阵、自动回滚编排 |
| CAP-06 | 管理页面组合模型/工具/Skill、预算和轮次，显式部门/成员依赖授权 | 现有 archive/skills 种子迁移、模板市场/生命周期、多引擎适配 |
| UI-03/05/07 | 实际 Web/API 表单、部门授权、持久任务、Skill 验证/审核、错误和清理状态；后续 MCP/知识库页面见对应增量契约 | 真实浏览器视觉/无障碍全量验收、完整企业治理页面 |

## 关键安全发现与修复

### 历史回答不能成为撤权绕过

- **根因（跨层契约/覆盖缺口）**：页面会遮蔽失权回答，但旧 Worker 从原始 messages 装载历史；checkpoint、后续 Run 和产物没有完整继承历史来源。
- **修复**：装载时通过旧 Run 当前授权过滤；有效历史来源与新 checkpoint 同事务保存。计算 workspace 分配不能覆盖已继承来源；输出 staging 合并来源。Skill use/read 来源分别传递。
- **验证**：在装载前、checkpoint 后、后续回答完成后撤权的三组 PG 回归；真实 Docker 的 Skill 引用撤权、Run/SSE/产物拒绝与消息遮蔽。

```text
错误：UI 隐藏 old_answer，但 Worker 继续使用 raw_messages；新文件变成“无来源”。
正确：Worker 授权 old_run → 缺权占位 / 获权内容+来源 → checkpoint → 后续调用和产物重新授权。
```

### 清理恢复不得被旧 deadline 无限抢占

- **根因（状态条件）**：恢复查询对 leased/stopping 都使用“lease 到期 OR 原执行 deadline 到期”，后者永远为真，新的清理租约可被另一个 Worker 立即抢走。
- **修复**：执行 deadline 只用于 leased；进入 stopping 后只按当前清理 lease 到期允许接管。旧 owner/generation 无权继续提交。
- **验证**：过期执行被接管后第二个清理 Worker 不能再次抢占；旧 Worker 回执拒绝，确认删除后记 failed 而非自动发布。

### Schema 也是不可信的程序输入

- **风险**：回溯正则、递归 `$ref`、无界 uniqueItems 可能在隔离执行前耗尽控制进程资源。
- **修复**：明确有界 dialect、禁危险正则/动态递归特性、引用展开配额；输入校验先做类型/大小，再做集合约束，不依赖 JSONB 的字段顺序。区分 schema 语法与字面数据，URI 百分号解码与实际引用解析一致，禁止 `$id`/dialect 改变解析边界。
- **验证**：独立危险 schema 拒绝、合法有限/编码引用仍可用；超长唯一数组不进入昂贵校验函数；业务 `pattern` 属性不被误伤，编码引用不能把危险规则藏在未检查的 metadata 中。

## 如何继续完整目标

1. 在已实现的固定依赖构建/签名/兼容检查上，按原 CAP-03/04 在已完成隔离归档导入上继续二进制资产、跨模块/种子与完整镜像发布运营，不能把压缩解析/安装放回 API/Worker。
2. MCP 走独立 connector 身份/凭据和受控出网，复用当前资源授权/审批/unknown-effect 事实，不把密钥交给 compute cell。
3. KB 摄取/检索/引用/删除必须复用来源传递，尤其检查历史回答、缓存、Workspace 与二次派生产物。
4. 完成 team/更多 runtime、治理/保留/备份/HA、公司真实提供方/UAT 后，逐条执行原安全与生产 Gate。
