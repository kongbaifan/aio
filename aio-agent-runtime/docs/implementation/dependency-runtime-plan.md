# 固定依赖运行时与 Skill v2：实施计划

> 本增量对应 SBX-03、CAP-03.04 和 CAP-05 的运行环境关键路径；完整企业平台目标不缩减。本轮之前基线：370 平台测试、64 Manager、82 Gateway、62 Web、175 HTTP 检查，数据库 v11 / 58 表。

## 目标与信任边界

业务管理员可发布真正使用 NumPy/Pandas 等依赖的 Skill，用户运行时不在 API/Worker/Gateway 宿主安装任何包，也不临时开放网络或只读根。依赖只从固定 wheels/哈希锁构建为不可变镜像，经操作员签名准入；多个 Run 共享镜像层，不共享可写环境。

构建/审批属于独立受信 CI/操作员域，不是用户 Run 的 HTTP 能力。企业部署应在专用构建节点执行；不将本机参考构建器描述为完成了全部供应链、内核和生产安全 Gate。

## 任务顺序

- [x] 公共纯 Python 运行时契约：版本/平台/依赖轮子哈希、固定摘要、Ed25519 审批、独立部署 trust store；不能信任审批文档自行提供的公钥。
- [x] 固定 OCI 构建模板：基础镜像 pinned；wheel 校验/解包/安装只在构建 cell 中；安装目录 `/opt/aio-deps` 与受信 Python 分离，最终 root 只读/目录非用户所有。
- [x] 离线安装、完整锁、包清单/CycloneDX SBOM/固定检查与运行 smoke 记录。测试 wheel 下载仅取固定 PyPI 元数据与匹配哈希的原始 bytes，控制进程不解压/import/setup。
- [x] 操作员审批与撤回：签名覆盖 image 和 manifest/证据摘要；只有独立配置的可信公钥可准入，合成 test 审批不能误用在 production。
- [x] Manager：分配/执行前复核批准镜像/签名；PID1 用 `-I -S`、不加载依赖；只有用户进程显式追加固定依赖目录，不处理 `.pth` 或修改宿主 Python。
- [x] API：管理员目录显示已批准环境/版本；Skill v2 固定环境摘要与 exact dependency requirements，创建/验证/发布都检查兼容，保持 v1 包摘要语义。
- [x] 持久 Worker/Skill 验证：版本校验和实际依赖探测只在隔离 cell；执行使用同一批准镜像，原来源/预算/审批/检查点与清理边界不变。
- [x] Agent 创建前拒绝同一主计算 cell 无法满足的混合 profile，不能等运行到一半才无声换镜像。
- [x] Web：显示依赖/环境摘要和双人审核语义；可导入 v2 包，但不提供 pip/npm/apt 或 Docker 参数表单。
- [x] 真实 Docker/PG/HTTP：NumPy/Pandas 执行与产物、独立用户环境、签名/镜像/版本不符拒绝、无网络/只读/限额与旧功能回归。
- [x] 文档/类型/证据更新；原 110 父任务、718 子任务与全部生产 Gate 不整体勾选。

## 2026-09-13 实施与验证收尾

本切片的上述实现/参考验收已完成；勾选仅对应本文件的固定依赖增量，不是原 110 父任务、718 子任务或任何完整生产 Gate 的放行。

| 证据 | 实际结果 |
|---|---|
| 运行时策略 / Manager | 15 / 93 通过 |
| 平台 / Gateway / 文档 parser | 408 / 82 / 16 通过，均无失败/错误/跳过 |
| Web | 63 通过；TypeScript、Prettier、生产构建通过，npm 官方审计 0 已知漏洞 |
| HTTP 全链路 | 182 项连续两轮通过；真实镜像、文件字节、部门/用户边界与自有服务清理 |
| 队列/控制专项 | 64 项核心 PG 回归通过；负向旧锁序证据保留，完整套件包含新用例 |
| 兼容与类型 | 旧 Harness 142、Sandbox 24、旧前端 45；81 路径 OpenAPI/TypeScript 逐字节复现 |
| 浏览器 / 公司外部系统 | 未完成；CUA 仍报认证不可用，没有冒充视觉/真实文件上传 QA，未接公司真实提供方 |

- 最新参考构建：`verify-3bbc937eb36bac0cd07e-dependencies`。
- 依赖 manifest：`84dd466c717ceec4bab9f5193efa4254088d30860c4b0c60cc5a49b685c44600`。
- 依赖镜像：`sha256:8d74c6df37532804c99ceb70b48759599290554d543a48fb8e096f2d61112051`；镜像与公钥配置以 `var/verification/dependency-profile.json` / `runtime-trust.json` 为准。
- 构建、inventory/CycloneDX SBOM/smoke/签名保存在 `var/runtime-candidates/verify-3bbc937eb36bac0cd07e-dependencies/`；批准用途为 **test**，生产消费者拒绝此测试批准。
- 汇总、各报告及 SHA-256：`var/verification/implementation-progress.json`。两轮 HTTP 报告是 `workbench-http-final-1.json` / `workbench-http-final-2.json`，对应状态诊断没有业务正文。
- 本轮还扩展修复并证明了生命周期、队列与控制入口的并发锁序，见 [锁序契约](../engineering/platform-stdio-lock-order.md)。没有延长锁超时、删除断言或重放业务 RPC 来制造成功。
- 最终复验曾再次抓到 `RUNTIME_UNAVAILABLE`，底层明确为 Docker 清理 DELETE 的 NotFound/404；实际并发删除在旧代码稳定复现。现已补齐幂等清理与独立不存在确认，17 项真实 Docker 资源/故障注入回归（含后续发现的 409 并发冲突）及新的完整/两轮 HTTP 栈通过，见 [Docker 清理契约](../engineering/platform-docker-cleanup-contract.md)。更早的无底层帧异常不能强行归为同一原因，长稳/故障/生产 Gate 仍保留。

## 明确不替代的剩余工作

Skill ZIP/TAR/种子导入、跨模块包支持、更多语言/浏览器、任意在线安装、MCP 联网/真实写/二进制产物、完整漏洞与许可证审核运营、密钥轮换/签名服务/Registry HA、公司 UAT 与生产 Gate 仍按完整计划推进。锁定、签名和 smoke 证明来源/批准/已测试行为，不等于第三方包不存在恶意行为或漏洞。
