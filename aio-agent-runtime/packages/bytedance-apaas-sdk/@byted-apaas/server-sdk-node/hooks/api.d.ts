import * as common from '@byted-apaas/server-common-node';
import { Tasks } from '../context/tasks/tasks';
import { DB } from '../context/db/impl/db';
import { _Resources } from '../context/resources/impl/resources';
import { Message } from '../context/msg/msg';
import { IMetaData } from '../context/metadata/metadata';
import { ExecuteOptions, ExecutionInfo, ExecutionResult, FlowTaskInfo, RevokeExecutionOptions } from '@byted-apaas/server-common-node/context/workflow/workflow';
type invokeGlobalFuncT = (funcNames: string) => {
    invoke: (params?: any) => Promise<any>;
};
export declare function getFunctionSync(context?: any, logger?: common.Logger): invokeGlobalFuncT;
export declare function setRespHeader(): () => void;
export declare function toString(value: any): string;
export declare function setRedirectLocation(context: any): (location: string) => void;
export declare function method(): string;
export declare function mountMetadata(context: any): void;
export declare function mountWorkflowFeature(context: any): void;
export declare function terminateWorkflow(): (workflowInstanceId: number, options: any) => Promise<void>;
export declare function mockFlowFeature(context: any): any;
export declare function mockGetExecutionUserTaskInfo(): (executionId: bigint) => Promise<FlowTaskInfo[]>;
export declare function mockExecuteFlow(): (apiName: string, options?: ExecuteOptions) => Promise<ExecutionResult>;
export declare function mockRevokeExecution(): (executionId: number, options: RevokeExecutionOptions) => Promise<void>;
export declare function mockGetExecutionInfo(): (executionId: number) => Promise<ExecutionInfo>;
export declare function invokeMicroservice(): (apiName: string) => {
    /**
     * 同步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invoke: (path: string, method?: string, params?: any) => Promise<any>;
    /**
     * 异步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invokeAsync: (path: string, method?: string, params?: any) => Promise<any>;
};
export declare const db: DB<import("@byted-apaas/server-common-node/context/IContext").IContext, import("../data").metadataMap>;
export declare const resources: _Resources;
export declare const msg: Message;
export declare const tasks: Tasks<unknown>;
export declare const cloudfunction: invokeGlobalFuncT;
export declare const microservice: (apiName: string) => {
    /**
     * 同步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invoke: (path: string, method?: string, params?: any) => Promise<any>;
    /**
     * 异步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invokeAsync: (path: string, method?: string, params?: any) => Promise<any>;
};
export declare const workflow: {
    terminate: (workflowInstanceId: number, options: any) => Promise<void>;
};
export declare const metaData: IMetaData<{}>;
export { Application } from '../application/impl/impl';
