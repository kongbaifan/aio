# Source Map

## Canonical sources used

| Target | Source | Reason |
|---|---|---|
| `services/python-runtime` | `full_source_archive/python_server` | 保留原始 `application/` 包结构和 `start_server.py` |
| `services/node-repl` | `full_source_archive/repl-servers/nodejs` | Node REPL 完整源码和依赖声明 |
| `services/hijack-proxy` | `full_source_archive/hijack_proxy` | Go 源码、证书材料和 Linux 二进制 |
| `packages/fastmcp` | `ultimate_complete_archive/07_fastmcp_python_framework` | FastMCP Python 源码 |
| `packages/bytedance-apaas-sdk` | `ultimate_complete_archive/06_bytedance_apaas_sdk` | aPaaS Node SDK 集合 |
| `skills/business` | `skills` | 当前业务 Skill 副本 |
| `skills/business/office-*` | `full_source_archive/skills` | 补齐 Office Word/Excel Skill |
| `skills/system/aio-sandbox` | `opt_system_skills/aio-sandbox` | 系统级 AIO Skill |
| `infra/gem` | `final_bonus/gem` | Nginx、Supervisor、浏览器和运行时配置 |
| `apps/sandbox-lite` | `aio-sandbox-lite` | 最小可运行教学版本 |

## Deliberately excluded

- `complete_archive`、`c83fc...`、`ultimate_complete_archive` 中与 canonical source 完全相同的重复副本。
- `super-doubao-runtime/workspace` 中的运行时用户数据、备份 Skill 和临时文件。
- `__pycache__`、`.pyc` 和 `node_modules`，依赖应按各自的 lockfile/requirements 安装。
- `final_dive/bytefaas` 等与核心沙箱源码无关的完整运行时二进制集合。

## Important caveat

`full_source_archive` 是源码提取，不是原始 Git 仓库。部分文档引用的 `../ARCHITECTURE.md`、Docker 构建脚本和生产编排器源码没有随提取物提供。
