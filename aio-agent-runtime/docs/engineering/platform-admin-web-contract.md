# 管理后台、部门授权与 Web 契约

> 当前实现契约，不是生产验收证书。入口：`app/admin/`、`app/api/v2/application.py`、`web/platform/`。完整目标仍按企业平台规划。

## 1. 身份与数据库边界

- 只允许精确 issuer+subject 匹配的预登记身份；不接受自助角色/组织归属或明文密码。
- `/api/public/login` 只公开安全登录配置；`/api/v2/me` 返回当前角色、显示名、部门和已实现 UI 能力。
- 每次请求重新认证，写请求再验 Origin/CSRF；隐藏按钮不代替授权。
- v4 增加组织内显示名、部门/成员/部门 Grant，继续采用复合组织外键和 FORCE RLS；迁移账号与 runtime 分离。
- GUC/RLS 依赖可信应用设置租户 scope，不宣称能抵御 runtime DB 凭据被盗后任意 SQL。

## 2. 管理权不等于私人内容读取权

| 行为 | 服务端边界 |
|---|---|
| 配置成员、部门、模型、工具、Agent、预算、策略 | 当前 active org_admin |
| 运维列表与停止请求 | 当前获准运维角色；仅 Run 元数据，不含消息/文件/原始 Prompt |
| 审计 | 有权管理/审计角色；安全投影，不回显任意 metadata |
| 项目分享 | 当前资源管理权；明确 user/department subject |
| 私有 Session、文件下载 | 当前资源及来源授权，没有管理员通读旁路 |
| 审批 | 当前资格、固定 ActionSpec、不同责任人；不隐式开放会话 |

部门 manager 角色已记录，但全套部门委派管理尚未完成，目前由组织管理员管理部门。通讯录仍是人工预登记，未宣称外部目录自动同步。

## 3. 授权、版本与预算

- Grant 按 resource kind 限制合法 action；不能对项目授 model.use。私人 Session、特殊 Run/Approval 不走通用共享。
- 禁部门/移除成员影响当前 facts；停用成员提升其 revision 并撤销认证会话。最后一位有效 org_admin 不可无替代地被停用/降权。
- 资源、Grant、成员操作只改相关事实，**不随意提升全组织 policy_revision**。只有组织策略修改才提升，避免一人分享让全组织在途 ActionSpec 失效。
- Agent 绑定固定模型/工具版本；依赖授权必须显式选择。撤 Agent Grant 不盲目删除仍被其他 Agent 使用的独立依赖 Grant。
- 模型配置仅引用操作员允许的 origin/凭据变量名，不接受原始 Key、shell 取密钥或任意代理。
- Python 工具仅允许固定 profile/image digest/no-network/timeout，不接受 Docker flags、宿主目录或宿主执行 fallback。
- 预算不能降到 consumed+reserved 以下。实际/预留/未知费用分别显示，不伪造指标。
- v13 增加组织 / 部门附加上限和不可变计费归属，保留个人预算 / 原始 ledger；范围重叠不得相加、成员调动不挪旧账、移除限额不清消费。接口 / Web / 迁移边界见 [共享预算契约](platform-shared-budget-contract.md)。

## 4. Web 持久任务协议

1. 身份切换提升 epoch 并中止旧请求；迟到响应不能覆盖新身份缓存。
2. Run 意图保存稳定幂等键；网络未确认时重试原键，不重建第二个任务。
3. SSE 验证 schema、Run ID、seq、帧大小；去重/回放以服务端事实为准。
4. 会话切换有独立 view identity，旧会话事件不能串流；断开浏览器不等于取消后台任务。
5. 取消等待持久终态；未知效果/未清理 blocker 不展示为安全成功。
6. 归档保留历史，未解决 Run 拒绝归档；共享项目不共享私人会话。
7. 来源撤权影响消息、事件和产物读取；客户端清除已不可展示的派生流。
8. Agent 发布可明确开放有界 Team，具体会话返回 supported_modes；选择的 mode 和幂等请求一起冻结。规划与汇总也消耗同一 Run 预算。
9. Team 的计划/步骤事件触发授权投影刷新，不等 SSE 关闭；低 revision 响应不能覆盖新状态。中间输出不混入最终回答，撤权清空步骤与草稿。详见 [Team 契约](platform-team-contract.md)。

Markdown 禁 raw HTML、外链安全打开；HTML/Office 为附件，**不是已杀毒或已安全解析**。模型文字/第三方说明不成为平台授权。

## 5. 接口和验证矩阵

- 具体路径/签名以 `docs/api/platform-v2.openapi.json` 为准。管理入口在 `/api/v2/admin/*`，授权在 `/api/v2/resources/{id}/grants`。
- `tests/platform/test_administration.py`：跨身份/租户、last-admin、私有内容、预算、依赖显式授权、局部变更不污染组织策略 revision。
- `web/platform/tests/`：请求契约、安全渲染、身份隔离、任务重试/流控、管理表单。
- `scripts/platform/test_workbench.py`：合成 IdP/model 加真实 PostgreSQL/Worker/Docker；有限时长、有所有权检查的资源清理。
- 未完成浏览器视觉检查、真实公司 IdP/provider 互操作、生产 HA/备份恢复。不能用本机绿灯替代生产 Gate。

## 6. 升级和失败策略

先备份并在隔离环境验证迁移，再运行 `manage_platform.py migrate`、`refresh-runtime-grants --runtime-role <role>`；API 不自动迁移/bootstrap。数据库版本/账号错误导致就绪失败，不降级 legacy-local。缺预算/模型/profile/授权明确不可用，不回退服务器命令。Web 可回退兼容构建，不通过删除持久 Run/部门/审计实现回退。

## 7. 撤权与并发投影：本轮修复记录

### 根因与漏点

- 类别为变更传播遗漏/隐含串行假设：`useRun` 新增 SSE 期间的并行步骤投影请求后，原流读取的 401/403/404/409/410 分支如果只清空 UI，较早发起的 200 响应仍可能迟到并重新填入内容。
- 只在投影请求自身失败时 abort 不足以覆盖主 SSE/最终 GET 失败的路径；仅比较 revision 也不代表仍有授权。

### 已实施机制

- 两条不可继续读取的错误分支都清空 Run、事件、草稿与文本缓存，并 abort 同一个观察生命周期。
- 所有投影接纳都检查该生命周期是否已中止；正常并发响应另按 revision 保持单调。
- 回归测试故意先挂起旧投影，再让流后的读取返回 404，最后返回一个 revision 更高的旧 200，断言私有步骤不会重新出现。
- 此规则适用于今后加入的审批、产物、费用等并行投影：权限失效必须取消整个视图生命周期，不能只清一个 React state。

```text
Wrong: clear UI on 404; another pending request may call setRun(old_private_data)
Correct: abort the observation scope, clear all projections, reject late responses even with higher revision
```

这不能召回用户此前已经读取/下载的数据；修复的是撤权后客户端并发回包把已清空内容重新展示的问题。证据在 `tests/team.test.tsx`，不是浏览器视觉验收结论。
