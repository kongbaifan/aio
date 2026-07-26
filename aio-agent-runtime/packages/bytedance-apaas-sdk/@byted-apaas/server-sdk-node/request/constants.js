"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.openapiHttpPath = exports.metricsMethodKeys = void 0;
const config_1 = require("@byted-apaas/server-common-node/http/config");
const constants_1 = require("@byted-apaas/server-common-node/http/constants");
exports.metricsMethodKeys = {
    // openapi
    // file upload & download
    getBatchAttachmentToken: 'openapi_getBatchAttachmentToken',
    oql: 'openapi_oql',
    // flow
    getExecutionUserTaskInfo: 'openapi_getExecutionUserTaskInfo',
    getExecutionInfo: 'openapi_getExecutionInfo',
    revokeExecution: 'openapi_revokeExecution',
    executeFlow: 'openapi_executeFlow',
    getApprovalInstanceList: 'openapi_getApprovalInstanceList',
    getApprovalInstance: 'openapi_getApprovalInstance',
};
exports.openapiHttpPath = {
    getBatchAttachmentToken: new config_1.PostHttpConfig(`/attachment/v1/getBatchAttachmentToken`, exports.metricsMethodKeys.getBatchAttachmentToken),
    oql: new config_1.PostHttpConfig(`/data/v5/namespaces/${constants_1.replaceKeys.namespace}/records/query`, exports.metricsMethodKeys.oql),
    // flow
    getExecutionUserTaskInfo: new config_1.GetHttpConfig(`/api/flow/v1/namespaces/${constants_1.replaceKeys.namespace}/executions/${constants_1.replaceKeys.id}/userTaskInfo`, exports.metricsMethodKeys.getExecutionUserTaskInfo),
    executeFlow: new config_1.PostHttpConfig(`/api/flow/v1/namespaces/${constants_1.replaceKeys.namespace}/flows/${constants_1.replaceKeys.apiName}/execute`, exports.metricsMethodKeys.executeFlow),
    revokeExecution: new config_1.PostHttpConfig(`/api/flow/v1/namespaces/${constants_1.replaceKeys.namespace}/executions/${constants_1.replaceKeys.id}/revoke`, exports.metricsMethodKeys.revokeExecution),
    getExecutionInfo: new config_1.GetHttpConfig(`/api/flow/v1/namespaces/${constants_1.replaceKeys.namespace}/executions/${constants_1.replaceKeys.id}/detail`, exports.metricsMethodKeys.getExecutionInfo),
    getApprovalInstanceList: new config_1.GetHttpConfig(`/api/approval/v1/approval_instances/listids`, exports.metricsMethodKeys.getApprovalInstanceList),
    getApprovalInstance: new config_1.GetHttpConfig(`/api/approval/v1/approval_instances/${constants_1.replaceKeys.id}`, exports.metricsMethodKeys.getApprovalInstance),
};
