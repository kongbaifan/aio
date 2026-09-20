# 固定依赖运行时、签名准入与 Skill v2

## 1. Scope / Trigger

对应 SBX-03、CAP-03.04、CAP-05。实现位于 `packages/runtime-policy/`、`services/dependency-runtime/`、Manager、`app/skills/` 与操作员构建脚本。当前参考环境提供固定 **NumPy 2.5.3 / Pandas 3.0.5 / python-dateutil 2.9.0.post0 / six 1.17.0**，只用于明确审批后的 Linux amd64 / CPython 3.12 环境。

目标是**共享不可变依赖镜像，不共享可写工作目录，也不在 API/Worker/Gateway 宿主执行用户安装或包代码**。构建属于独立受信 CI/操作员域；企业部署应使用专用构建节点。本机 Docker 构建和 smoke 不是构建节点硬化、漏洞/许可证认证或全部生产 Gate。

## 2. Signatures / Commands / API

```text
RuntimeManifest v1:
  name, python=3.12, platform=linux-x86_64, base_image, recipe_sha256
  packages[{name, exact version, wheel filename, bytes, sha256, fixed smoke imports[]}]
  install_path=/opt/aio-deps, network_profile=none
  digest = aio-runtime-manifest-v1 + RFC8785 content

RuntimeApproval v1:
  release_id, exact image_digest, manifest, inventory/sbom/smoke SHA256
  approved_at, key_id, purpose(production|test), review_note, Ed25519 signature
  signing domain: aio-runtime-approval-v1

Manager Profile.runtime_approval?: signed RuntimeApproval
PLATFORM_RUNTIME_TRUST_KEYS: explicit absolute operator public-key JSON
SANDBOX_RUNTIME_TRUST_KEYS: separately supplied Manager public-key JSON

SkillCreate.package:
  v1: original text package and original aio-skill-package-v1 digest
  v2: base package + runtime_manifest_digest + dependencies[{name, exact version}]
  v2 digest: aio-skill-package-v2; dependency/file order normalized
```

操作员入口（在项目根目录、受信构建环境运行）：

```powershell
python -m pip install -e packages/runtime-policy -e services/sandbox-manager
python scripts/platform/build_runtime.py `
  --lock config/runtime-locks/analytics-python.json `
  --wheelhouse var/runtime-wheels/analytics --output var/runtime-candidates/review-001 `
  --download-pinned-pypi-wheels

python scripts/platform/approve_runtime.py `
  --candidate var/runtime-candidates/review-001/candidate.json `
  --key-file <private-operator-key-file> --key-id <trusted-key-id> `
  --purpose production --review-note "<actual operator review of this immutable candidate>" `
  --output var/runtime-candidates/review-001/approval.json

python scripts/platform/export_runtime_profile.py `
  --approval var/runtime-candidates/review-001/approval.json `
  --trust-keys <absolute-public-trust-store> --profile-id analytics `
  --output var/runtime-candidates/review-001/profile.json
```

`--download-pinned-pypi-wheels` 是可选的显式原始字节下载，只访问固定 PyPI release 元数据和匹配的 files.pythonhosted.org 文件；不解析版本范围、不追随重定向、不使用环境代理、不解压/执行 metadata。公司私有 wheel 可由操作员从批准镜像源放入 wheelhouse，同样必须匹配完整 hash 锁。API/Worker 没有这些操作员构建/签名 HTTP 接口。

## 3. Build / Installation / Isolation contracts

- 每 wheel ≤64 MiB，总输入 ≤128 MiB；只允许 wheel，禁止源发行包、VCS/任意 URL、setup.py 或安装命令作为 Skill 字段。
- 固定 Dockerfile 的非 root 构建阶段先校验 SHA/大小，再在 cell 内检查 ZIP 的 EOCD/数量、路径、Unicode/大小写别名、链接/特殊节点、加密/压缩方法、膨胀比例和总量。单个文件 ≤64 MiB，总展开 ≤512 MiB、≤20000 条目；`.pth` 和受信 Python/启动模块覆盖拒绝。
- 安装只在 `RUN --network=none` 内，使用 `--no-index --no-deps --require-hashes --no-compile --target=/opt/aio-deps`。安装者 UID10001，不能覆盖基础解释器；最终目录以 root 所有复制到只读镜像，wheels/CI 缓存/操作员私钥不进入最终环境。
- inventory 探针在无网络、只读、非 root、有内存/CPU/PID/输出/期限限制的 cell 内运行，以 `-I -S` 禁止 site hooks；只读取分发元数据和文件摘要，不 import 第三方包。验证完整依赖闭包、实际版本、根所有权/非组写权限、树限额与 SHA。
- functional smoke 在另一个同样受限 cell 中 import 已声明模块；参考环境实际执行 NumPy/Pandas 计算，并检查只读运行目录、UID、网络和 Socket。它是功能证据，不能证明恶意代码不会伪装通过。
- 输出候选状态为 `review_required`，含 manifest、inventory、CycloneDX 1.6 Python SBOM、smoke 与各 SHA；不会因为构建退出码为零就自动批准。
- 审批脚本再次核对完整文件哈希、通过状态、精确包集合、依赖闭包、镜像、imports 和限制事实后签名。签名不存私钥，部署只配置独立公钥 trust store；审批对象自己携带的新公钥无效。

## 4. Runtime / Application / Lifecycle contracts

- Manager 分配/执行/导出前验证签名、独立信任 key、purpose 和精确 image。镜像/容器 label 必须对应审批 manifest 与固定 install_path；带依赖 label 的镜像缺签名不能伪装成普通 compute。隐式 Entrypoint 或错误平台拒绝。
- PID1 一律用固定绝对 Python 路径与 `-I -S`，UID10000，不加载业务依赖。依赖用户进程是 UID10001，使用 `-I -S` 并**追加** `/opt/aio-deps`，不执行 `.pth`、不替换受信 Python 的搜索顺序，也不把操作员公钥/私钥当成 guest 权限。
- profile 全局 cell/CPU/内存准入与原 tmpfs/输出/期限仍适用。参考 profile 为 512 MiB 内存、32 MiB tmp；库在镜像层共享，不按用户重新安装，不跨 Run 复用可写目录。
- API 启动验证签名后只给管理台投影公共环境信息。v2 创建、提交验证和发布均比较固定 manifest 与 exact requirements；这些 requirements 是兼容契约，**不是能禁止任意 Python 读取其他已批准库的安全边界**。
- v2 验证有独立 runtime 检查步骤，在实际 cell 中读取只读 manifest 和实际版本；随后原 AST/凭据形态扫描、声明样例、确认销毁、不同管理员审核流程不变。
- 发布工具冻结 `runtime_manifest_digest`；API 的当前执行/heartbeat authority 再检查环境批准。撤回后不继续新动作、不切宿主 fallback；owned stop/status/ack 不因业务批准撤回而被禁止。
- Manager 移除信任 key 后拒绝新 ensure/execute；清理仍可进行。部署 trust store 是启动配置，变更需协调排空/重启，不声称已实现跨节点实时信任广播或进程内存迁移。
- 同一个 Run 仍只有一个主 compute workspace；创建 Agent 时就拒绝混合不兼容 profile/image 的计算工具。不要运行到一半偷偷换镜像；MCP stdio/文档摄取仍是独立角色。
- 原 CellSpec 不变，固定依赖运行时没有新增数据库迁移，image 本身绑定依赖字节；Skill 包 v2 是独立摘要域，旧 v1 与文件检查点摘要不改变。已运行任务不自动换到新库。

## 5. Validation & Error Matrix

| 输入 / 条件 | 行为 |
|---|---|
| 信任 key 缺失/签名损坏/image 不符/未来审批 | `RUNTIME_APPROVAL_DENIED`，不执行用户代码 |
| production 消费 test 审批 | 配置/执行失败关闭，不使用测试信任当公司生产批准 |
| 依赖镜像无 approval | `RUNTIME_APPROVAL_REQUIRED`，不退化为普通 compute |
| label / install path / Entrypoint / 架构不符 | `RUNTIME_IMAGE_MISMATCH` / `RUNTIME_PLATFORM_MISMATCH` |
| v2 未选择签名环境 | `SKILL_RUNTIME_REQUIRED` |
| manifest / dependency version 不一致 | `SKILL_RUNTIME_MISMATCH` / `SKILL_DEPENDENCY_MISMATCH`，不尝试安装 |
| cell 实际环境检查不一致 | 验证失败、确认清理后不可发布 |
| 环境从当前 API 目录撤回 | `RUNTIME_PROFILE_WITHDRAWN`；后续动作拒绝，owned cleanup 仍可完成 |
| Agent 混用主 compute profile | `AGENT_RUNTIME_CONFLICT`，不创建可运行的坏组合 |
| 恶意 wheel/path/link/startup hook/膨胀/metadata | 构建校验拒绝，无批准运行时输出 |

## 6. Good / Base / Bad + Verification

- Good：操作员构建/审查一个锁定环境，多个部门引用同一签名镜像；各自的 Skill/Run 仍经过自己的资源授权、独立目录、预算、当前权限与实际清理。
- Base：原 v1 标准库 Skill 与已批准的旧执行器继续工作；额外依赖不能通过 SKILL.md 指令自动装到宿主。
- Bad：修改版本范围后继续复用旧签名；把输入自带公钥当作信任根；把 .pth 添加给 PID1；依赖缺失时在 Worker 上 pip install；把签名/smoke 称为无漏洞证明。

证据入口：公共 `test_runtime_policy_contracts.py`；Manager `test_dependency_runtime.py`（真实 NumPy/Pandas、跨环境文件、只读/无网、拒绝与清理、隔离恶意 wheel 校验）；平台 `test_dependency_contracts.py` / `test_dependency_platform.py`（真实验证/双人发布/两用户产物、目录撤回、混合环境拒绝）；Web Skill v2 数字版本/依赖提示与无安装表单；HTTP 固定依赖助手。完整本机结果与差额见 [实施进度](../implementation/README.md)。

### OpenAPI numeric-version gotcha

整数 `schema_version` 的 discriminator mapping 在 openapi-typescript 中可能变为字符串 `"1" | "2"`。当前使用受 `Literal` 与 extra=forbid 约束的二分支 union，保持真实 JSON 数字版本；缺字段的旧 v1 请求在验证前补默认值。不能用 TypeScript cast 掩盖客户端/服务端协议不一致。

## 7. Wrong vs Correct / Remaining

```text
Wrong: a Skill says pip install -> execute installation on API/Worker or shared system Python
Correct: exact reviewed wheel lock -> isolated offline CI candidate -> independent signed approval -> immutable runtime cell

Wrong: successful build/smoke means trusted for every department and production
Correct: verify source/approval/compatibility and current grants; keep vulnerability/license/organization gates explicit
```

仍未完成：全量漏洞/许可证审核运营、专用构建节点硬化与 Registry/签名服务 HA、跨节点分发/信任撤回、任意在线安装、Skill 归档/跨模块/种子生命周期、更多语言/浏览器、MCP 联网/真实写与公司 UAT。原 110 父任务/718 子任务及 G0–G6 没有整体标完成。
