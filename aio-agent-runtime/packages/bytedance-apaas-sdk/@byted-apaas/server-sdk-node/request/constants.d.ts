import { GetHttpConfig, PostHttpConfig } from '@byted-apaas/server-common-node/http/config';
export declare const metricsMethodKeys: Record<string, string>;
export declare const openapiHttpPath: {
    getBatchAttachmentToken: PostHttpConfig;
    oql: PostHttpConfig;
    getExecutionUserTaskInfo: GetHttpConfig;
    executeFlow: PostHttpConfig;
    revokeExecution: PostHttpConfig;
    getExecutionInfo: GetHttpConfig;
    getApprovalInstanceList: GetHttpConfig;
    getApprovalInstance: GetHttpConfig;
};
