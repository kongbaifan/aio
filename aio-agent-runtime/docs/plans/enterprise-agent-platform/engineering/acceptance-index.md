# 原任务到工程契约的验收绑定

> 原有 110 个父任务、718 个子任务全部保持待实施。本索引将每项工作关联到设计/审查底线、证据画像和后续集成用例，不代表这些用例已实现或已执行。

## 1. 如何使用

1. 按下表打开原任务卡，再读该领域主契约。
2. 从子任务 JSON pointer 找到原工作描述/依赖，描述摘要用于防止两个索引漂移。
3. 领取前填写本次具体文件、接口、正负例和所需环境；实施后才填写 PR/实际证据/审查结果。
4. 相关 ECASE 是最终联调/发布回归义务。早期 schema/契约工作先证明局部不变量，不能因引用后期测试反向制造开工循环；相关集成 Gate 仍必须实测。

[验收绑定 JSON](acceptance-bindings.json) · [契约/事务/故障/用例目录 JSON](contract-catalog.json) · [原工作分解 JSON](../stages/work-items.json)

## 2. 证据画像

见 [交付证据规范](09-delivery-migrations-operations.md)：EP-DESIGN/DATA/SERVICE/RUNTIME/INTEGRATION/UI/VERIFY/OPERATE/RELEASE。画像是最低要求，不能用它替代该具体子任务新增代码的测试。

## 3. 逐父任务定位

| 原任务卡 | 阶段/负责人 | 最低证据画像 | 主工程契约 | 相关 ECASE |
|---|---|---|---|---|
| [FND-01](../stages/p0-foundation.md#fnd-01) | P0 / QA/BE | EP-VERIFY | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 39、40 |
| [FND-02](../stages/p0-foundation.md#fnd-02) | P0 / SEC/ARCH/PM | EP-DESIGN | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 设计/来源审批，不伪造运行测试 |
| [FND-03](../stages/p0-foundation.md#fnd-03) | P0 / BE/FE | EP-DESIGN | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 01、06、19、20 |
| [FND-04](../stages/p0-foundation.md#fnd-04) | P0 / PE/QA | EP-RUNTIME | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 21、23、24、25 |
| [FND-05](../stages/p0-foundation.md#fnd-05) | P0 / BE/PE | EP-SERVICE | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 39、40 |
| [FND-06](../stages/p0-foundation.md#fnd-06) | P0 / SEC/PE | EP-DESIGN | [01-decisions-and-invariants.md](01-decisions-and-invariants.md) | 设计/来源审批，不伪造运行测试 |
| [DAT-01](../stages/p1-identity-data.md#dat-01) | P1 / BE-A/PE | EP-DATA | [03-database-transactions.md](03-database-transactions.md) | 05、15、16 |
| [DAT-02](../stages/p1-identity-data.md#dat-02) | P1 / BE-A | EP-DATA | [03-database-transactions.md](03-database-transactions.md) | 15、16、18 |
| [DAT-03](../stages/p1-identity-data.md#dat-03) | P1 / BE-B | EP-DATA | [03-database-transactions.md](03-database-transactions.md) | 01、02、04、06、12、14 |
| [DAT-04](../stages/p1-identity-data.md#dat-04) | P1 / BE-A/PE | EP-DATA | [03-database-transactions.md](03-database-transactions.md) | 13、26、28 |
| [DAT-05](../stages/p1-identity-data.md#dat-05) | P1 / BE-A/QA | EP-DESIGN | [03-database-transactions.md](03-database-transactions.md) | 36 |
| [DAT-06](../stages/p1-identity-data.md#dat-06) | P1 / BE-A | EP-DATA | [03-database-transactions.md](03-database-transactions.md) | 05、15、16 |
| [IAM-01](../stages/p1-identity-data.md#iam-01) | P1 / BE-A/SEC | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 17、18 |
| [IAM-02](../stages/p1-identity-data.md#iam-02) | P1 / BE-A | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 17、18、38 |
| [IAM-03](../stages/p1-identity-data.md#iam-03) | P1 / BE-A | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 17、18、36 |
| [IAM-04](../stages/p1-identity-data.md#iam-04) | P1 / BE-A/SEC | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 18、22、28、30 |
| [IAM-05](../stages/p1-identity-data.md#iam-05) | P1 / BE-A | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 15、18、28 |
| [IAM-06](../stages/p1-identity-data.md#iam-06) | P1 / BE-A/QA | EP-DATA | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 15、16 |
| [IAM-07](../stages/p1-identity-data.md#iam-07) | P1 / BE-A/PE | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 22、32、33、40 |
| [IAM-08](../stages/p1-identity-data.md#iam-08) | P1 / BE-A/BE-B | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 17、18、29、32 |
| [IAM-09](../stages/p1-identity-data.md#iam-09) | P1 / BE-A/SEC | EP-SERVICE | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 06、33 |
| [IAM-10](../stages/p1-identity-data.md#iam-10) | P1 / QA/BE-A | EP-VERIFY | [02-identity-authorization-contracts.md](02-identity-authorization-contracts.md) | 15、16、17、18、33 |
| [UI-01](../stages/p1-identity-data.md#ui-01) | P1 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 19、38 |
| [UI-02](../stages/p1-identity-data.md#ui-02) | P1 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 17、18、38 |
| [RUN-01](../stages/p2-runtime-sandbox.md#run-01) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 04、08、12、37 |
| [RUN-02](../stages/p2-runtime-sandbox.md#run-02) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 01、02、03、18 |
| [RUN-03](../stages/p2-runtime-sandbox.md#run-03) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 04、05、11 |
| [RUN-04](../stages/p2-runtime-sandbox.md#run-04) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 02、14、19 |
| [RUN-05](../stages/p2-runtime-sandbox.md#run-05) | P2 / BE-B/FE | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 18、19、38 |
| [RUN-06](../stages/p2-runtime-sandbox.md#run-06) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 14、37 |
| [RUN-07](../stages/p2-runtime-sandbox.md#run-07) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 08、11、13、14、37 |
| [RUN-08](../stages/p2-runtime-sandbox.md#run-08) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 06、07、08、09 |
| [RUN-09](../stages/p2-runtime-sandbox.md#run-09) | P2 / BE-B/PE | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 09、10、11、12、25 |
| [RUN-10](../stages/p2-runtime-sandbox.md#run-10) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 03、35 |
| [RUN-11](../stages/p2-runtime-sandbox.md#run-11) | P2 / BE-B | EP-SERVICE | [04-run-approval-recovery.md](04-run-approval-recovery.md) | 07、14、27、35 |
| [RUN-12](../stages/p2-runtime-sandbox.md#run-12) | P2 / QA/BE-B | EP-VERIFY | [04-run-approval-recovery.md](04-run-approval-recovery.md) | ECASE-01 起，共 16 项，见 JSON |
| [SBX-01](../stages/p2-runtime-sandbox.md#sbx-01) | P2 / PE/SEC | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 16、23、24 |
| [SBX-02](../stages/p2-runtime-sandbox.md#sbx-02) | P2 / PE/BE-B | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 04、21、25 |
| [SBX-03](../stages/p2-runtime-sandbox.md#sbx-03) | P2 / PE | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 22、23、39 |
| [SBX-04](../stages/p2-runtime-sandbox.md#sbx-04) | P2 / PE/BE-B | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 20、23、25、26 |
| [SBX-05](../stages/p2-runtime-sandbox.md#sbx-05) | P2 / PE/BE-B | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 20、22、23、25 |
| [SBX-06](../stages/p2-runtime-sandbox.md#sbx-06) | P2 / PE | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 22、24、25、38 |
| [SBX-07](../stages/p2-runtime-sandbox.md#sbx-07) | P2 / PE/BE-B | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 23、25 |
| [SBX-08](../stages/p2-runtime-sandbox.md#sbx-08) | P2 / PE/SEC | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 22、24 |
| [SBX-09](../stages/p2-runtime-sandbox.md#sbx-09) | P2 / BE-A/PE | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 12、26、27 |
| [SBX-10](../stages/p2-runtime-sandbox.md#sbx-10) | P2 / BE-A/PE | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 13、26、27、28 |
| [SBX-11](../stages/p2-runtime-sandbox.md#sbx-11) | P2 / PE/BE-B | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 12、21、25 |
| [SBX-12](../stages/p2-runtime-sandbox.md#sbx-12) | P2 / PE/BE-A | EP-RUNTIME | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 17、22、32、33 |
| [SBX-13](../stages/p2-runtime-sandbox.md#sbx-13) | P2 / QA/SEC/PE | EP-VERIFY | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 20、21、22、23、24、25、26、27 |
| [SBX-14](../stages/p2-runtime-sandbox.md#sbx-14) | P2 / PE/SEC | EP-INTEGRATION | [05-execution-control-and-storage.md](05-execution-control-and-storage.md) | 20、22、23、24、25 |
| [CAP-01](../stages/p2-runtime-sandbox.md#cap-01) | P2 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、09、18、20、22、31、34 |
| [CAP-02](../stages/p2-runtime-sandbox.md#cap-02) | P2 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 18、31 |
| [CAP-07](../stages/p2-runtime-sandbox.md#cap-07) | P2 / BE-B/QA | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 20、22、39、40 |
| [GOV-01](../stages/p2-runtime-sandbox.md#gov-01) | P2 / SEC/BE-A | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 22、28、30 |
| [GOV-02](../stages/p2-runtime-sandbox.md#gov-02) | P2 / BE-A/SEC | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 33、34 |
| [GOV-04](../stages/p2-runtime-sandbox.md#gov-04) | P2 / BE-A/PE | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 04、12、17、18 |
| [GOV-07](../stages/p2-runtime-sandbox.md#gov-07) | P2 / BE-A/BE-B | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 32、33、35、40 |
| [OPS-01](../stages/p2-runtime-sandbox.md#ops-01) | P2 / PE | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 22、23、39 |
| [OPS-02](../stages/p2-runtime-sandbox.md#ops-02) | P2 / PE/BE | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 15、16、20、22、24、39、40 |
| [UI-04](../stages/p2-runtime-sandbox.md#ui-04) | P2 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 02、08、12、19、38 |
| [UI-06](../stages/p2-runtime-sandbox.md#ui-06) | P2 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 06、07、08、18 |
| [CAP-03](../stages/p3-capabilities-workbench.md#cap-03) | P3 / BE-A/PE | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 26 |
| [CAP-04](../stages/p3-capabilities-workbench.md#cap-04) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、18、26 |
| [CAP-05](../stages/p3-capabilities-workbench.md#cap-05) | P3 / BE-B/QA | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、26、31 |
| [CAP-06](../stages/p3-capabilities-workbench.md#cap-06) | P3 / BE-A/FE | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 18、28、31 |
| [MCP-01](../stages/p3-capabilities-workbench.md#mcp-01) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 20、24、31 |
| [MCP-02](../stages/p3-capabilities-workbench.md#mcp-02) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 22、32 |
| [MCP-03](../stages/p3-capabilities-workbench.md#mcp-03) | P3 / BE-A | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 24、32、33 |
| [MCP-04](../stages/p3-capabilities-workbench.md#mcp-04) | P3 / BE-B/SEC | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 24、31 |
| [MCP-05](../stages/p3-capabilities-workbench.md#mcp-05) | P3 / PE/BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 20、22、24、25 |
| [MCP-06](../stages/p3-capabilities-workbench.md#mcp-06) | P3 / BE-B/SEC | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、09、10、11、12、34 |
| [MCP-07](../stages/p3-capabilities-workbench.md#mcp-07) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 09、10、20、33 |
| [MCP-08](../stages/p3-capabilities-workbench.md#mcp-08) | P3 / QA | EP-VERIFY | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、09、10、22、24、31、32、34 |
| [KB-01](../stages/p3-capabilities-workbench.md#kb-01) | P3 / BE-A | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 18、28、29、30 |
| [KB-02](../stages/p3-capabilities-workbench.md#kb-02) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 04、29 |
| [KB-03](../stages/p3-capabilities-workbench.md#kb-03) | P3 / PE/BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 23、24、25、26 |
| [KB-04](../stages/p3-capabilities-workbench.md#kb-04) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 29、30、35 |
| [KB-05](../stages/p3-capabilities-workbench.md#kb-05) | P3 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 18、28、30 |
| [KB-06](../stages/p3-capabilities-workbench.md#kb-06) | P3 / BE-A/FE | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 18、30 |
| [KB-07](../stages/p3-capabilities-workbench.md#kb-07) | P3 / BE-A/BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 28、29、30、36 |
| [KB-08](../stages/p3-capabilities-workbench.md#kb-08) | P3 / QA/业务 | EP-VERIFY | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 26、28、29、30 |
| [UI-03](../stages/p3-capabilities-workbench.md#ui-03) | P3 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 18、28、38 |
| [UI-05](../stages/p3-capabilities-workbench.md#ui-05) | P3 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 13、18、26、28、38 |
| [UI-07](../stages/p3-capabilities-workbench.md#ui-07) | P3 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 18、29、31、32、38 |
| [GOV-03](../stages/p4-pilot-verification.md#gov-03) | P4 / BE-B | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 03、11、35 |
| [GOV-05](../stages/p4-pilot-verification.md#gov-05) | P4 / BE-A/FE | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 10、33 |
| [GOV-06](../stages/p4-pilot-verification.md#gov-06) | P4 / BE-A | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 18、28、29、36 |
| [GOV-08](../stages/p4-pilot-verification.md#gov-08) | P4 / PE/BE-B | EP-SERVICE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 19、25、33、34 |
| [GOV-09](../stages/p4-pilot-verification.md#gov-09) | P4 / QA/BE-B/业务 | EP-VERIFY | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 14、28、30、35 |
| [OPS-03](../stages/p4-pilot-verification.md#ops-03) | P4 / PE/BE-A | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 12、29、36、37 |
| [OPS-04](../stages/p4-pilot-verification.md#ops-04) | P4 / PE/QA | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 12、25、33、34、35 |
| [OPS-05](../stages/p4-pilot-verification.md#ops-05) | P4 / QA/PE | EP-VERIFY | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 03、04、19、23、25、27、35 |
| [UI-08](../stages/p4-pilot-verification.md#ui-08) | P4 / FE | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 28、33、35、38 |
| [UI-09](../stages/p4-pilot-verification.md#ui-09) | P4 / FE/QA | EP-UI | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 08、12、19、38 |
| [UI-10](../stages/p4-pilot-verification.md#ui-10) | P4 / QA/FE | EP-VERIFY | [07-api-frontend-contracts.md](07-api-frontend-contracts.md) | 06、07、08、12、18、19、28、33、38 |
| [REL-01](../stages/p4-pilot-verification.md#rel-01) | P4 / BE-A/QA | EP-RELEASE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 15、28、36 |
| [REL-02](../stages/p4-pilot-verification.md#rel-02) | P4 / SEC/QA | EP-VERIFY | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | ECASE-01 起，共 40 项，见 JSON |
| [REL-03](../stages/p4-pilot-verification.md#rel-03) | P4 / PM/业务/QA | EP-VERIFY | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 06、12、18、19、28、30、38 |
| [REL-04](../stages/p4-pilot-verification.md#rel-04) | P4 / PE/PM | EP-RELEASE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 12、25、34、35、36、39 |
| [REL-05](../stages/p4-pilot-verification.md#rel-05) | P4 / PE/BE/QA | EP-RELEASE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 04、10、12、27、36、37 |
| [OPS-06](../stages/p5-production.md#ops-06) | P5 / PE/ARCH | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 04、11、19、21、25、36、37 |
| [OPS-07](../stages/p5-production.md#ops-07) | P5 / PE/SEC | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 07、22、31、32、37、40 |
| [OPS-08](../stages/p5-production.md#ops-08) | P5 / PE/SEC/QA | EP-OPERATE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 10、12、22、23、28、33、34、36 |
| [REL-06](../stages/p5-production.md#rel-06) | P5 / PM/SEC/PE | EP-RELEASE | [09-delivery-migrations-operations.md](09-delivery-migrations-operations.md) | 10、12、22、25、28、34、35、36、37、39 |
| [KB-09](../stages/p6-extensions.md#kb-09) | P6 / BE-B | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 24、29、30、32、36 |
| [ENG-01](../stages/p6-extensions.md#eng-01) | P6 / ARCH/BE-B | EP-DESIGN | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 22、37、39 |
| [ENG-02](../stages/p6-extensions.md#eng-02) | P6 / BE-B/PE | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 04、20、21、22、25 |
| [ENG-03](../stages/p6-extensions.md#eng-03) | P6 / BE-B/SEC | EP-INTEGRATION | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 07、10、18、20、22、34、35、40 |
| [ENG-04](../stages/p6-extensions.md#eng-04) | P6 / QA/BE-B | EP-VERIFY | [06-capability-data-contracts.md](06-capability-data-contracts.md) | ECASE-04 起，共 11 项，见 JSON |
| [ENG-05](../stages/p6-extensions.md#eng-05) | P6 / ARCH/PM/PE | EP-RELEASE | [06-capability-data-contracts.md](06-capability-data-contracts.md) | 10、22、35、37、39 |

## 4. 特别细化的子任务

下列关键子任务在 JSON 中有独立 contract refinement，不仅继承领域画像：

| 子任务 | 补充重点 |
|---|---|
| [RUN-02.04](../stages/p2-runtime-sandbox.md#run-02) | Run、Job、消息、Snapshot、预算预留和事件必须原子提交；事务内禁止外部网络 IO。 |
| [RUN-03.04](../stages/p2-runtime-sandbox.md#run-03) | Fencing 拒绝旧代次的新动作，但无法撤销已在途的外部效果。 |
| [RUN-07.03](../stages/p2-runtime-sandbox.md#run-07) | 恢复使用已提交的逻辑调用；不得从最初 prompt 再生成一份可能不同的写操作。 |
| [RUN-08.01](../stages/p2-runtime-sandbox.md#run-08) | 规范化 ActionSpec 覆盖不可变代码、输入、工具、凭据 scope 与版本；摘要本身不是授权。 |
| [RUN-08.03](../stages/p2-runtime-sandbox.md#run-08) | 审批使用 CAS 和当前资格校验；approved 不代表已经派发。 |
| [RUN-09.04](../stages/p2-runtime-sandbox.md#run-09) | 未知效果保留持久业务 blocker，同时核对并释放或隔离计算资源。 |
| [IAM-06.01](../stages/p1-identity-data.md#iam-06) | 基于可信应用 GUC 的 RLS 不抵御持应用数据库凭据者自行设置上下文的任意 SQL。 |
| [IAM-07.04](../stages/p1-identity-data.md#iam-07) | 在进入旧 ModelRegistry 解析器之前拒绝命令式密钥配置。 |
| [SBX-02.03](../stages/p2-runtime-sandbox.md#sbx-02) | 租约唯一键包含 target_slot；不同权限 cell 独立绑定并分别计入资源配额。 |
| [SBX-04.04](../stages/p2-runtime-sandbox.md#sbx-04) | stdout 与控制帧分离不使同 UID runner 自动可信；资源事实必须由外部 manager 核实。 |
| [SBX-07.03](../stages/p2-runtime-sandbox.md#sbx-07) | 证明每个可写路径的字节与 inode 硬限制实际生效，而不是仅存在清理任务。 |
| [SBX-09.05](../stages/p2-runtime-sandbox.md#sbx-09) | 发布前核对当前 lease、generation、head 和来源权限。 |
| [SBX-12.03](../stages/p2-runtime-sandbox.md#sbx-12) | 持凭据 connector 默认独立权限 cell；任意 compute 不能读 Token 或绕过网关直连业务。 |
| [MCP-05.02](../stages/p3-capabilities-workbench.md#mcp-05) | 固定 connector target，不提供用户 exec，不共享 compute 可写文件系统或管理通道。 |
| [MCP-06.03](../stages/p3-capabilities-workbench.md#mcp-06) | 派发前可靠记录意图，网络重试/代次变化不改变下游业务幂等键。 |
| [KB-07.04](../stages/p3-capabilities-workbench.md#kb-07) | 来源撤权后重建或拒绝派生上下文，不继续悄悄复用旧摘要。 |
| [GOV-03.04](../stages/p4-pilot-verification.md#gov-03) | 迟到的真实费用用追加调整记录核对，即使超过准入预留也不能丢账。 |
| [GOV-06.06](../stages/p4-pilot-verification.md#gov-06) | 开放恢复数据前重放当前删除/撤权事实，无法确认时保持关闭。 |
| [UI-02.03](../stages/p1-identity-data.md#ui-02) | Logout 清理浏览器状态；持久 Run 委托和用户停用是不同的生命周期。 |
| [UI-04.03](../stages/p2-runtime-sandbox.md#ui-04) | 从权威事件游标恢复；迟到响应必须匹配当前身份和视图 epoch。 |
| [REL-04.02](../stages/p4-pilot-verification.md#rel-04) | 试点开放前必须有真实恢复/回滚/值班证据及批准的数据与用户范围。 |

## 5. 初始状态与后续维护

所有 `actual_evidence`、`implementation_pr`、`reviewer_acceptance` 为 null；所有新增 ECASE 的 execution_status 为 not_run。禁止在没有运行记录的情况下填 passed。

阶段 Markdown 与 work-items.json 仍是任务定义，工程文档是契约定义；这两个 JSON 是可重新生成的索引。任何设计变更应同步校验链接、ID、摘要、前置关系和证据范围，不手工维护互相矛盾的第二套状态。
