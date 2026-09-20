# Skill 归档隔离导入：实施记录

> 2026-09-14 开始。承接已验证的固定依赖 Skill v2；完整目标仍为原 110 父任务 / 718 子任务，不以本增量替代全部 CAP-03～06 或生产 Gate。

## 目标与边界

管理员上传 ZIP、TAR、TAR.GZ 格式的单个 Skill，得到私有且不可变的 v1/v2 草稿，再走已有隔离测试、不同审核人和显式共享授权。API、Worker、Gateway 不解压/解释用户归档，不执行 setup、安装钩子或归档内代码；解析只在无网、非 root、限额的短寿命 cell。

- `skill.json` 模式：根目录（或唯一一层外包装目录）含原 Skill 元数据和入口/测试/依赖声明，不含内联 `files`；实际文本文件来自归档。兼容 v1/v2，不由声明自动授予权限。
- 原生文件夹模式：根目录含 `SKILL.md`，名称/版本/描述/来源/许可证由上传人明确填写；保留 Markdown 原文，不在宿主解析 YAML，不从 frontmatter 自动创建执行能力。先导入 instruction-only 包，脚本是数据而非自动执行入口。
- 仍保持现有文本包边界：最多 48 文件，JSON 包最多 256 KiB；不把该路径描述为任意二进制资产或跨模块执行支持。
- 原始归档先进入按 owner/resource/hash 绑定的私有 quarantine；上传、解析、结果、物理清理、Manager payload ack 和草稿创建各有明确事实。
- 导入成功不等于发布或共享；源码/引用读取与执行权限仍分开，专业 malware/CVE/许可证认证不被结构检查替代。

## 实施顺序

- [x] 纯请求/结果契约、固定解析程序与 ZIP/TAR/GZIP 恶意归档矩阵；在真实 cell 中验证，不向控制服务增加解析 fallback。
- [x] v12 不可变迁移快照：独立 SkillImport resource/记录，唯一上传意图、大小/hash、预留、队列租约/代次、执行证据、清理/ack、生成 Skill 引用；RLS 与复合组织外键。
- [x] 私有上传与 quota/blob 引用：稳定 request_id、相同字节幂等、角色/版本当前验证；不允许删除/GC 与迟到上传互相复活对象。
- [x] 有界持久导入 Worker 与 authority：固定 scanner profile/image/code、stdin/文件输入只进 cell；未知结果不得自动建草稿；撤权不阻止结构清理。
- [x] 复用 SkillCreate 的同事务草稿创建：不创建可变占位 Skill、不自动发布、不自动继承上传人的跨部门 Grant；执行环境当前兼容检查。
- [x] 原始归档取消/删除/回收：停止确认、payload ack、引用检查、quota 释放；不删除已经生成的不可变 Skill。
- [x] API 与 Web：上传、状态、扫描/清理错误、转到新草稿与审核流程；默认不开放无配置的归档执行器。
- [x] 实际 Docker/PG/HTTP、两用户与撤权/恢复/重复导入/故障验收，生成类型和文档同步。

## 当前决策

1. 新增独立导入记录，不用一个可变/假内容 SkillVersion 占位；解析完成并确认清理后才原子创建真正草稿。
2. 解析器读取归档成员并生成 JSON 包，不把成员路径提取到任何控制或部署目录；链接、设备、隐藏配置、路径别名和压缩炸弹拒绝。
3. 解析结果通过已停止 cell 的固定 `package.json` 导出；不把整包塞进日志/stdout，也不提高全局工具输出限额。
4. 只有操作员配置的扫描环境可调度；最终 Skill 的执行环境独立指定并按现有签名/依赖兼容规则验证。
5. 共享当前 BlobStore/组织存储配额与引用判定，独立限制归档条数和 quarantine 字节。持久解析状态不与个人对话 Run 混为一谈。
6. 所有新生命周期写遵循组织→资源→导入行/租约顺序；外部 Docker/网络/解析不能在 PG 事务内运行。

## 必须保持的验收点

正例：三种归档格式、根/单层目录、native instruction-only、含声明入口的 v1、固定依赖 v2、同内容上传重试、作者转到草稿、不同人验证/审核、明确部门共享后使用。

反例：绝对/越界/反斜杠/NUL/Unicode/大小写路径别名、links/devices/sparse、加密或未知压缩、多包/尾随内容、成员/大小/比例/时间超限、非 UTF-8/二进制、秘密形状内容、metadata 与实际文件不符、伪造环境、重复 name/version、跨用户读取/上传/删除、撤权与代次竞争、上传/结果/停止/ack 响应丢失。

本文件勾选只随实际代码与证据更新；尚未实施的项保持未完成。

## 2026-09-14 本增量验证结果

| 验证 | 实际结果 |
|---|---|
| 真实 Docker scanner / 完整 Manager | 43 / 136 passed |
| 归档 PG 流程 / 归档纯契约 / 完整平台 | 14 / 14 / 436 passed，0 failures/errors/skipped |
| Web | 6 项归档用例；全套 69 passed；类型、格式、生产构建通过 |
| 完整 HTTP | 234 项连续两轮通过，含私有上传、v1/v2/native、拒绝恶意包、隔离验证/独立审核、清理保留 Skill |
| 兼容 | legacy Harness 142、Sandbox-lite 24；pip check 通过 |
| 生成契约 | 87 路径 OpenAPI 与 TypeScript 逐字节复现 |
| 自有资源 | 两轮 HTTP 与最终 PG 的 label 范围容器/卷均已清理；未动其他服务 |

上述勾选仅表示本归档增量有代码与参考验收，不是完整 CAP-03～06 或生产放行。浏览器/native-upload 视觉、公司真实提供方、二进制资产/跨模块/旧库种子/完整发布治理仍未完成。依赖增量文件保留其 2026-09-13 的历史统计，不改写为本轮结果。

完整报告与哈希：`var/verification/implementation-progress.json`；最终 HTTP：`workbench-archive-http-final.json`；最终运行标记：`archive-final-run.json`。
