# Skill 归档隔离导入契约

## 1. Scope / Trigger

实现：`app/skills/archive_*`、`0012_skill_imports`、`web/platform/src/features/SkillArchives.tsx`。面向管理员上传的单个 Skill，不提供宿主解压、远程仓库任意拉取、setup/install hooks 或隐式发布。原 v1/v2 文本包、代码验证、不同人员审核和显式 Grant 仍是最终使用边界。

当前支持 ZIP、TAR、单 gzip member 的 TAR.GZ。解析发生在指定的无网络、非 root、只读根、CPU/内存/PID/磁盘限额 cell；控制宿主只处理有界请求元数据、原始不透明字节和解析后的有界 JSON。归档成员**不提取到宿主或部署目录**，也不作为文件树写进执行搜索路径。

## 2. Signatures / Configuration / API

```text
PLATFORM_SKILL_IMPORT_PROFILE=<approved scanner profile ID>
PLATFORM_SANDBOX_PROFILES=<operator profile JSON>
PLATFORM_RUNTIME_TRUST_KEYS=<independent public keys for dependency profiles>
PLATFORM_MANAGER_URL / PLATFORM_MANAGER_TOKEN / PLATFORM_ARTIFACT_ROOT
```

API 与 Worker 使用一致的当前批准环境；Worker 不需要 OIDC 浏览器 client secret。扫描环境是操作员选择的标准 Python profile，最终 Skill 的执行 profile 由管理员从获准目录选择，两个用途不混为一谈。扫描建议配置至少 4 MiB 工作区、至少 256 KiB 导出额度、允许固定 Python 命令和至少 10 秒单命令时限；实际限额只由 Manager 操作员配置，上传者不能放宽。

```text
GET  /api/v2/admin/skill-imports/config
GET  /api/v2/admin/skill-imports
POST /api/v2/admin/skill-imports
GET  /api/v2/admin/skill-imports/{id}
PUT  /api/v2/admin/skill-imports/{id}/content      application/octet-stream
GET  /api/v2/admin/skill-imports/{id}/download     attachment, no-store, nosniff
POST /api/v2/admin/skill-imports/{id}/delete

SkillArchivePrepare:
  request_id: UUID (stable for retry of the exact same intention)
  archive_format: zip | tar | tar.gz
  bytes: integer, 1..2097152
  sha256: 64 lowercase hex
  sandbox_profile: final Skill validation/execution profile
  native?: {name, version, description, source, license}

SkillArchiveRevision: expected_revision
CellSpec.target_slot: "skill/archive-import"
```

写请求仍需 BFF 身份、当前 org_admin、Origin/CSRF。每个原始导入只允许作者访问；其他管理员或误插入的 read Grant 不产生原始归档读取权。不可变 Skill 生成后再按原 Skill 规则给审核人/部门/员工授权。

## 3. Archive Layout and Limits

### 显式能力包

```text
skill.json        # v1/v2 元数据，含入口/schema/tests/精确依赖声明，但不含 files
SKILL.md
scripts/entry.py
references/guide.md
LICENSE          # 也接受 NOTICE / COPYING / README 文本声明
```

可以有一层共同外包装目录。`skill.json` 沿用 [文本/固定依赖包契约](platform-skill-contract.md)，文件内容由归档提供。导入不是依赖安装：声明必须符合已批准环境，固定依赖 v2 的签名/摘要/精确版本要求不变。

### 原生文件夹

没有 `skill.json` 时，上传人显式选择原生模式并填写 `native` 元数据，根目录或一层目录内提供 `SKILL.md`。保留 Markdown/frontmatter 原文作为数据，**不解析 YAML 来授予权限**，不把 `scripts/` 自动变成可执行工具。生成 v1 instruction-only 草稿；最多 24 个有界引用，更多内容应使用明确 manifest。

| 边界 | 当前约束 |
|---|---|
| 上传 | ≤2 MiB，意图中固定大小与 SHA；字节不同拒绝重试 |
| 成员 | ≤128 个含目录；最终内容 1～48 文件 |
| 内容 | UTF-8 文本；单文件 ≤64 KiB，说明/按需引用依原包规则 ≤32 KiB；整个包 JSON ≤256 KiB |
| 描述文件 | ≤128 KiB，重复 JSON key / 非有限数 / 无界深度拒绝 |
| 压缩 | ZIP stored/deflate；不支持加密、ZIP64/self-extracting/多卷、任意额外尾随记录；比例 ≤200 |
| TAR/GZIP | TAR 总展开 ≤8 MiB；拒绝 sparse/link/device、串接 gzip、多余非零尾随内容 |
| 路径 | NFC、相对、≤256 UTF-8 bytes/8 层；拒绝越界、反斜杠、控制字符、隐藏配置、大小写与文件/目录别名 |
| 环境 | 固定命令最多 30 秒（可被 profile 收紧），cell 总期限 60 秒；不提高全局工具输出限额 |
| Quarantine | 组织最多 100 个未清理导入、32 MiB 原始归档，另受组织总存储额度约束 |

固定结构程序复用已有 AST/入口签名/凭据形状检查；也检查归档元数据中的已知凭据形状。这不是专业 malware/DLP/CVE 或版权认证。许可证/来源字段是人工审核声明，不是自动合规证明。

## 4. Durable Lifecycle and Trust Boundaries

```text
awaiting_upload -> uploading -> queued -> leased -> stopping
  -> imported (a private immutable Skill draft)
  -> rejected / cancelled

separate facts:
  upload_bound + uploaded_at
  frozen request/profile/image/code/spec/dispatch + generation/lease
  scan_receipt -> candidate (bounded package JSON + digest)
  cleanup_state=confirmed -> manager_acknowledged
  atomic Skill creation + import.skill_id
  purge_requested -> archive_purged + reserved_bytes=0
```

- 不创建假内容/可变占位 Skill。生成草稿与导入成功回执使用同一事务、同一当前权限和目录配额检查；同名版本不能被覆盖。
- 上传先保存不可变意图与存储预留，再写有界原始 bytes；写盘与 GC 使用组织存储锁。已绑定但写入未完成的记录保留 quota，不让取消后的迟到写入复活孤立对象。
- 原始归档不进入 stdout；固定 cell 生成 `package.json`，只有命令回执和已停止 writer 的导出均匹配后才接收候选内容。控制进程重新验证 Skill schema、依赖兼容和摘要。
- Manager 只允许本次固定 scanner code、dispatch ID、语言和时限，不接受调用方任意替换命令。`ensure/alive/finalize` 都检查当前身份、导入状态与批准环境。
- 未确认的执行、停止或 payload ack 不能创建草稿。丢失结果不自动重跑扫描；旧 Worker/generation 被 fence。已停止且持久候选完成的 cleanup 恢复只处理确认/草稿事务，不重放业务动作。
- 撤权/取消阻止继续扫描或生成草稿，但不阻止精确旧绑定的 stop/status/ack；结构性清理不授予私人内容读取。
- 原始归档清理不删除或撤回已经生成的 Skill。共享 BlobStore 的其他 Artifact/KB/检查点/导入引用仍会保护相同哈希；逻辑预留只在确认安全后释放。
- 上传/排队期限在意图创建时固定，不能因另一 Worker 的配置不同无声延长；同名请求 ID 仅可重试相同内容。接口和页面不会把失败结果当成功。

## 5. Validation / Error Matrix

| 情形 | 行为 |
|---|---|
| 三种合法格式、根目录/一层包装 | 真实 cell 检查后生成私有草稿 |
| 原生 SKILL.md 文件夹 | 只有指令/引用，不自动获得执行入口 |
| 精确依赖 v2 | 保留原包版本/环境摘要/依赖，创建前复核当前执行环境 |
| 变更 bytes/hash/request_id 内容 | 不覆盖原意图或已有版本 |
| 越权读/上传/删除原归档 | 默认拒绝，包括其他 org_admin |
| 恶意路径/链接/压缩/内容/元数据 | 隔离拒绝，不创建 Skill；错误不包含原始正文 |
| 扫描中撤权、取消、过期、Worker 丢失 | 禁继续执行/创建；确认清理，保留必要 hold |
| 同名版本已存在 | 拒绝第二次版本创建，保留原不可变内容 |
| 正常/丢失确认的重复原始上传 | 相同意图与字节幂等，不重复排一个新的包 |
| 未确认停止或 ack | 不发布、不生成草稿、不释放未确认事实 |
| 清理原归档 | 不隐式删除生成 Skill，也不删除其他有效引用的 blob |

## 6. Tests / Evidence

- `test_skill_archives.py`：真实 cell 解码 ZIP/TAR/TAR.GZ、native、包装目录、路径/链接/大小/元数据/凭据形状拒绝；测试包内有可造成副作用的 Python 文本，解析阶段不能执行它。
- `test_skill_archive_contracts.py`：纯格式契约、有界命令/结果、未知元数据、旧包摘要兼容与通知文本路径。
- `test_skill_archive_imports.py`：真实 PG/Manager 的 owner/quota/idempotency/候选/清理/恢复/Grant/共享 hash/v2/HTTP boundary，以及导入后继续原双人发布。
- `skill-archives.test.tsx`：不透明字节上传、稳定请求 ID、native 语义、未配置拒绝、原始归档清理确认、异步读文件时关闭页面不发请求。
- `verify_archive_http.py`：完整有限寿命测试栈中的实际上传/扫描/审核/原始归档清理/跨用户/恶意包；不冒充浏览器视觉或公司真实提供方验收。

完整统计以 [实施记录](../implementation/skill-archive-plan.md) / [进度](../implementation/README.md) 为准，当前增量完成前不借用旧回归结果声明全部通过。

## 7. Wrong vs Correct / Deployment / Remaining

```text
Wrong: upload.zip -> API extractall -> shared skills/ -> automatically publish
Correct: immutable private intention -> bounded no-network cell -> confirmed cleanup + ack
         -> current-authority private draft -> isolated entry tests -> distinct reviewer -> explicit grants

Wrong: scan succeeded means trusted code or an approved license
Correct: bounded structural evidence only; execution stays isolated and human/production gates remain explicit
```

部署前暂停接单并排空旧 Worker，备份后迁移至 v12、刷新 runtime grants，同步更新 API/Worker/Manager；旧 Manager 不认识新 slot 时拒绝而不降级。默认不启用 scanner profile。没有破坏式 downgrade。

仍需后续完成：跨模块执行、二进制 Skill 资产、完整种子/市场/灰度/回滚/弃用治理、专业内容与供应链审计、更多语言与网络 profile、跨节点存储/HA、目录委派和公司 UAT。不能因归档能导入而把全部企业平台放行。
