# 独立文档解析器

此包处理不可信文档，**产品文件只能在 sandbox-manager 管理的无网络 parser cell 中解码**。API/Worker 不导入它解析用户文件，不在失败时回退到宿主机。

## 已支持的输入

| 格式 | 提取内容/位置 | 重要限制 |
|---|---|---|
| TXT/Markdown | UTF-8 文本、行范围、稳定字符偏移 | 不执行 HTML/代码；其他编码明确拒绝 |
| CSV | 行/单元格文本、行号 | 不执行表格公式；行列/单元格大小有上限 |
| PDF | 可提取文本和页码 | 拒绝加密与已识别活动内容；扫描图片无 OCR，不伪装成有文本 |
| DOCX | Word 段落/表格内文本、段落位置 | 有界 OOXML ZIP；禁实体/DTD、宏/嵌入活动内容；外链不抓取 |
| XLSX | 工作表名、行号、单元格坐标和值 | 不计算公式，缓存值明确标注；隐藏表/行不索引并返回提示 |

依赖固定：`pypdf==6.18.1`、`defusedxml==0.7.1`。这些结构检查**不是专业恶意软件扫描，也不是原始附件安全执行证明**。原文下载始终作为附件。

## 输入输出契约

固定工作目录中只有受控输入：

```text
document.bin                         原始不可变文档字节
parse-request.json                   {schema_version:1,format,source_sha256}
```

平台只批准固定命令：

```python
import runpy; runpy.run_module('aio_document_parser', run_name='__main__')
```

成功输出 `parsed-document.json`：schema/parser version、原文件 SHA-256、format、text_bytes、warnings 和 chunks。每个 chunk 含 ordinal、text、location、sha256。stdout 只返回结果文件大小/摘要/数量，不打印文档原文。错误仅返回安全错误码。

Worker 检查 Manager 绑定、结果文件摘要、来源摘要、格式和块边界；不能因为 stdout 写了“成功”就公开索引。Manager 外部停止写者并收集文件后才允许候选索引进入 PG；数据入库后 acknowledge 清除 Manager 保留的原文/导出 payload。

## 硬边界

- 原文件 ≤8 MiB；展开归档 ≤32 MiB、≤2048 个节点、单条 ≤16 MiB、受限压缩比。
- ZIP 原始名称必须安全；不是只检查平台可能已经规范化的 `ZipInfo.filename`。拒绝越界/绝对路径/反斜杠/特殊节点/大小写重复等。
- 正文 ≤1 MiB，≤512 个块，每块 ≤4096 UTF-8 字节；JSON 输出 ≤2 MiB。
- PDF ≤100 页；表格 ≤5000 行/表、≤128 列、≤200000 个单元格；工作表 ≤32。
- 当前发布 profile 使用非 root UID10001、独立 UID10000 watchdog、只读 root、cap_drop ALL、no-new-privileges、network none，CPU/内存/PID/工作区大小和到期时间均受限。
- parser/compute 中均没有 OIDC/模型/业务连接器凭据或 Docker Socket。镜像预先构建，不动态运行用户 setup/install 钩子。

## 构建与验证

```sh
python -m pip install -e services/document-parser
python -m pytest services/document-parser/tests -q
python scripts/platform/test_sandbox.py
```

最后一条构建固定基础镜像的 compute/parser 镜像、运行真实 Docker/PG 测试，输出 `var/verification/document-profile.json`。控制进程的单元测试只使用明确的合成夹具，不代表产品文档可以在宿主解析。

部署 API 的 `PLATFORM_DOCUMENT_PROFILES` 指向操作员允许的绝对 JSON 文件。Manager 独立配置同一 profile/image digest，文档 profile 至少支持 60 秒命令和足够的有界导出预算。完整接口/授权/计费见 [知识库契约](../../docs/engineering/platform-knowledge-contract.md)。
