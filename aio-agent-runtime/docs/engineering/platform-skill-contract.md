# 共享 Skill 的实现契约（文本包 v1 / 固定依赖 v2）

> 实际入口：`app/skills/`、`app/runtime/catalog.py`、`app/execution/`、`web/platform/src/features/Skills.tsx`。数据库迁移 `0005_skills`。这是可运行的增量，不代表 CAP-03～06 或企业平台全部验收完成。

## 1. 共享什么，不共享什么

共享的是**不可变版本 + 明确资源授权**。包内容保存在组织范围的受限数据库中；它不是宿主机上的共享可写 `skills/`，不会自动扫描个人 Codex/旧 Harness 目录，也不会执行 metadata 的安装钩子。

- 普通员工使用管理员配置的 Agent，不需要安装 Python/Skill 或管理容器。
- 组织管理员创建私有包；指定另一位有效组织管理员审核。指定审核人产生明确的 `skill.read` Grant，并记录审核任务/人员/包摘要。
- 审核者身份不带来其他作者草稿、私人 Session 或文件的通读权；撤销审核人的读取 Grant 同样有效。
- 使用包需要 `skill.use`；读取脚本/引用需要独立 `skill.read`。执行入口还需 `tool.use`，Agent 和模型也各自检查权限。
- 这是平台读取接口与执行授权的分离，不是源代码保密/DRM 保证：获准执行的同一 compute cell 若还允许运行任意代码，代码可能被进程自省观察；说明内容也会进入模型上下文。Skill 不得嵌入业务凭据；需要隐藏实现的能力必须另设可信服务边界。
- 通过 Agent 授权对话框可显式将依赖授给部门或成员。撤销 Agent 不自动删除其他独立依赖 Grant。

## 2. 包格式及已实现边界

管理员可直接编写 instruction-only 草稿，或导入 JSON 文本能力包。v1 示例：[`example-calculation.json`](../../config/skill-packages/example-calculation.json)；固定 NumPy/Pandas 环境的 v2 示例：[`example-analytics.json`](../../config/skill-packages/example-analytics.json)。示例不是财务政策或生产批准。

ZIP/TAR/TAR.GZ 通过独立的 [归档隔离导入](platform-skill-archive-contract.md) 转成同样的 v1/v2 私有草稿；该入口不是让 `SkillCreate` 接收二进制或让 API 解压文件。原生 SKILL.md 文件夹导入只产生指令/引用，不隐式产生执行能力。

```text
SkillPackage:
  schema_version=1
  name, version（SemVer x.y.z）, description, source, license
  instruction_path, reference_paths[]
  files[{path, content}]
  entrypoints[{name,path,description,input_schema,output_schema,tests[],timeout_seconds}]
DependencySkillPackage:
  schema_version=2, base package fields above
  runtime_manifest_digest, dependencies[{name, exact version}]
```

| 边界 | 当前值/行为 |
|---|---|
| 名称/版本 | 组织内 name+version 唯一；已保存内容不可覆盖，修改要新版本 |
| 内容 | Markdown/Python/JSON/CSV/TXT 与 LICENSE/NOTICE/COPYING/README 声明，UTF-8 文本；归档由独立隔离入口转换，不支持任意二进制资产 |
| 整包/文件 | 整包 JSON ≤256 KiB；≤48 文件；单文件 ≤64 KiB |
| 模型上下文 | 主说明 ≤32 KiB；单个按需引用 ≤32 KiB；每 Agent ≤16 个 Skill |
| 路径 | NFC、相对路径；拒绝绝对/越界/反斜杠/控制字符/大小写别名和隐藏配置文件；不存在符号链接节点 |
| Python 入口 | ≤4 个，固定文件中的同步 `run(payload)`；单入口源代码 ≤32 KiB |
| 测试 | 每入口 1～3 个，总计 ≤8；声明超时总和 ≤120 秒；验证 cell 固定总期限 180 秒 |
| 注册库 | 每组织 ≤200 版本、16 MiB 包 JSON；每版本 ≤10 次验证 |
| 环境 | 操作员允许的 profile + image digest；无网络、无业务凭据；不允许自定义 Docker 参数 |

v2 对依赖环境使用独立包摘要域；环境的 wheel 哈希、只读镜像、Ed25519 审批与信任公钥独立于 Skill 作者。创建/验证/发布检查精确环境与依赖版本，验证新增实际 cell 环境检查步骤；缺包不在宿主临时安装。部署、准入、当前撤回和剩余供应链 Gate 见 [依赖运行时契约](platform-dependency-runtime-contract.md)。v1 默认值和旧包摘要保持不变。

只接受已实现字段，不将 `requires`、脚本注释或 SKILL.md 里的权限声明当作授权。source/license 是待人工审核的来源声明，**没有声称已自动证明版权合规**。

### 输入输出 schema

使用有界的封闭 object JSON Schema。总字节 ≤32 KiB、遍历深度 ≤16、展开节点 ≤1024；本地 `$defs` 引用必须可解析且无环，先按 URI 解码再解析 JSON Pointer，与实际验证器解析到同一对象。禁止远程/动态/递归引用、改变解析根的 `$id`/anchor、切换到其他 dialect、回溯正则 `pattern`/`patternProperties` 和 unevaluated 扩展；uniqueItems 数组要求 maxItems≤128，验证器先检查类型和大小，再做可能昂贵的约束。检查区分 schema 关键字、业务属性名称与 enum/default 字面数据，不会因为业务字段叫 `pattern` 就拒绝它。不能把 schema 当作可在 API/Worker 线程任意运行的校验程序。

这是明确受限的 dialect，不是所有 Draft 2020-12 特性的实现。更丰富格式/正则/依赖需独立安全方案，不通过放宽控制服务限制临时兜底。

## 3. 状态与事务

```text
Skill: draft -> validating -> validated -> published
                         \-> rejected <-/（审核拒绝）
ValidationJob: queued -> leased -> stopping -> passed/failed
Resource.status: active/disabled（独立于发布内容）
```

- 创建、name/version 唯一、服务端摘要/文件清单、拥有者资源及审计在事务内完成。操作员配置决定 image，不信任浏览器提交镜像或凭据。
- 提交验证使用 expected_revision；包已固定，不能一边测试一边修改源文件。队列与交互 Run 分开，仍共享 Manager 的节点资源限制。
- Worker 领取后，先持久化 spec、binding、generation、每步 dispatch ID、实际命令和截止时间，再请求 Manager。
- Manager 继续使用私有鉴权 `/internal/v1/sandbox/authorize`；`target_slot=skill/validation` 走专用 Job 权威检查，不伪造普通 Run，也不绕开原 Run 的权限条件。
- Guard 检查当前作者身份/组织角色/资源状态、租约、代次、包摘要、整个 spec、当前步骤和精确命令。验证 cell 不能调用 finalize 导出业务产物。
- Scanner 在无网络 cell 里执行静态 AST/入口和凭据形态检查；不会在 API/Worker import、compile 或执行上传代码。随后声明测试也只在 cell 执行。
- 已通过结果保留结构化步骤/结果摘要；失败保存安全错误码，不复制原始 traceback/输出到审计页面。样例可被恶意代码刻意迎合，**测试通过不是行为安全证明**。
- 所有步骤通过还不够：必须先确认 Manager 已销毁 cell，再置为 validated。停止回执丢失时保持 stopping，禁止发布和再次验证。
- 过期 Worker 被 generation/owner fencing 阻止；恢复 Worker 只清理旧 cell 并记 failed，不盲目重跑代码。清理租约不会因为原执行截止时间已过而被第二个恢复 Worker 抢走。
- 人工审核再验证作者、审核人权限、最新 profile、当前包 revision、验证任务及清理证据。发布工具和版本状态同事务提交；作者不能自批。

## 4. Agent 运行接入

- `AgentCreate.skill_ids` 固定 Skill id/digest 和发布工具；同名 alias 冲突拒绝。新版本不会改变旧 Agent/Run。
- 指令内容作为明确标记的“不可信任务辅助资料”进入上下文，不作为平台 system 权限。
- `skill.read` 仅按固定版本和获权路径读取数据库内容，不使用全局文件搜索或用户指定宿主根路径。
- `skill.python` 使用标准 compute 管理路径。入口源代码嵌入当次精确命令，**不从可写 workspace 的同名脚本加载**；支持单文件入口、标准库与批准的固定依赖镜像，不宣称支持任意跨模块包/在线安装。同 Run 的计算工具必须使用兼容的单一主 compute profile，创建 Agent 时即拒绝混合环境。
- ActionSpec 包含版本工具摘要、入口摘要、镜像摘要、输入摘要、资源 scope 和 deadline；Manager 对实际命令再次比对。
- 输出需成功退出、未截断、唯一结果标记、严格 JSON 及 output_schema。工作文件仍按既有 staging/CAS/停止写者/原子发布流程处理，测试 cell 不复用为业务 cell。

## 5. 来源、撤权与历史复用

Run/Artifact 分别记录 `capability_source_ids` 与 `capability_read_source_ids`，避免把 use 和 read 混为一个授权。来源跨输入文件、Project workspace、历史回答、后续 Run、生成产物传递。

Worker 在装载历史时重新检查旧回答的来源；不可读内容用占位替代。读取过的有效历史，其来源会和新 checkpoint 一起持久化，后续模型/工具/心跳以及结果/事件/下载再次检查，不能只在 Web 隐藏旧消息却继续把原文送给模型。

版本禁用/授权撤销会阻止新访问和后续动作；Manager 周期复核使在途代码停止。已发生的操作、模型已接收的数据及员工已下载的副本无法被“倒退撤回”，这里不承诺通用 exactly-once 或数据远程收回。

## 6. 验证与运维

```sh
python scripts/platform/test_sandbox.py
npm test --prefix web/platform
npm run build --prefix web/platform
python scripts/platform/test_workbench.py
```

- 契约：`test_skills_contracts.py`，包含路径/字节/引用、inert source、ReDoS/递归 schema 拒绝和输出边界。
- PG：`test_skills_integration.py`，覆盖私有草稿、不可变 DB 列、双人职责、当前读权限、部门授权、清理恢复 fencing 和 private authority。
- 真实 Docker：`test_skills_pipeline.py`，覆盖隔离扫描/测试/执行、无网/UID/只读/无凭据、workspace 同名脚本篡改不能替换入口、引用权限撤销与派生数据屏蔽，以及错误结果/语法/洪水/超时。
- HTTP：有限时长 stack 使用四个合成身份，实际通过 SSO、Web/API、独立 Skill Worker、HTTP Manager/control callback、Docker、发布/部门授权、生成文件与禁用后的撤权。模型/IdP 是合成的，不是公司真实提供方。
- Web：表单、固定 revision、不同审核人、清理未确认禁止发布、XSS 文本显示、Agent Skill 绑定。浏览器视觉验收仍另行执行，不把 jsdom/HTTP 当截图证据。

API 与 Worker 不挂 Docker Socket；Manager 的 service/control token 不同，并只配置在可信服务侧。升级前需排空并停止 v4/更旧 API 与 Worker，再迁移到 v5、刷新 runtime grants、启动新版本；未验证新来源字段兼容前不能混跑旧读取器。旧 schema_v1～v4 不改写，生产滚动升级 Gate 仍未验收。

## 7. 仍未交付的范围

ZIP/TAR 隔离解包与压缩炸弹检查、二进制依赖/锁文件/镜像构建、跨模块/跨包依赖、专业恶意软件扫描、现有 skills 目录的审核导入工具、按 token 的上下文预算、灰度/弃用/批量事件处置、完整保留与清理治理尚未完成。MCP/知识库/team/其他语言和真实公司接入也不由这一增量代替。

## 8. 可执行接口与失败矩阵

```text
POST /api/v2/admin/skills
  SkillCreate{package: SkillPackage, sandbox_profile: string} -> SkillVersion (201)
GET /api/v2/admin/skills/{skill_id} -> private package + bounded validation receipts
POST /api/v2/admin/skills/{skill_id}/validate
  SkillValidate{expected_revision, reviewer_id} -> {job_id,state,revision} (202)
POST /api/v2/admin/skills/{skill_id}/review
  SkillReview{expected_revision,decision:approve|reject,note} -> SkillVersion
GET /api/v2/skills -> currently authorized published metadata
GET /api/v2/skills/{skill_id}/file?path=... -> exact authorized text, id and digest
SkillValidationStore.claim(org_id,worker_id) -> durable command/spec handle | None
SkillValidationStore.authorize(operation,payload) -> allow or PlatformError
SkillValidationStore.record(handle,index,response) -> atomic confirmed step
SkillValidationStore.stopping/finish/recover_one -> fenced cleanup/terminal facts
```

| 输入/窗口 | 可观察结果 | 必须保持的事实 |
|---|---|---|
| 非管理员创建/读取草稿 | 403/404 | 不泄漏其他作者包正文 |
| 未登录/缺 CSRF | 401/403 | 不创建版本或验证 Job |
| 无效路径/未知字段/schema | 422（超限 413） | 不执行任何上传源代码 |
| 已存在 name+version | SKILL_VERSION_EXISTS / 409 | 不覆盖版本；没有第二份可变内容 |
| 自批/错误审核人 | SEPARATION_OF_DUTIES / 403 | 不生成发布工具 |
| 无验证/清理未确认 | SKILL_NOT_VALIDATED / 409 | 不可发布；unknown 不自动重跑 |
| 当前 profile 撤回 | SANDBOX_PROFILE_DENIED / 403 | 不能以历史测试批准新发布 |
| 错代次/错命令/错步骤 | STALE_GENERATION 或 MANAGER_ACTION_DENIED | 不允许旧 Worker 替换脚本或注入命令 |
| 引用 read 撤回但 use 仍有 | 源内容、派生 Run/事件/文件拒绝 | 不把两个权限合并成通读 |

**基本路径**：有限 instruction-only 包 → 独立扫描 → 确认销毁 → 不同人员审核 → 部门授权。  
**正常扩展**：声明 Python `run(payload)`、封闭 schema 和合成样例 → 真实 cell 测试 → 固定源代码/输入调用 → schema 合格结果与私有产物。  
**错误路径**：上传对象带绝对路径/安装字段；在 workspace 放同名恶意脚本；仅伪造 stdout“cleanup ok”；历史回答撤权后继续复用其原文。对应行为分别是准入拒绝、使用固定版本而非同名文件、等待外部清理事实、遮蔽/阻止后续使用。
