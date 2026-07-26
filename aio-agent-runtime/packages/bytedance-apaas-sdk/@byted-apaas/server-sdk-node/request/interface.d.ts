/// <reference types="node" />
/// <reference types="node" />
import { Criterion, CriterionV3 } from '../kunlun/operator/impl/logic';
import { Stream } from 'stream';
import { ExecutionInfo, ExecutionResult, RevokeExecutionOptions } from '@byted-apaas/server-common-node/context/workflow/workflow';
import { AppCtx } from '../application/application';
import { Order } from '../context/db/impl/order';
import { IApprovalInstance, IApprovalInstanceList, IApprovalInstanceListOptions, IGetApprovalInstanceOptions } from "./structs";
export declare function GetHttpInstance(): IInnerAPIRequest;
export declare function GetInstance(): IInnerAPIRequest;
export declare function GetFaaSInfraInstance(): IFaaSInfraRequest;
export type UploadFileResp = {
    id: string;
    token: string;
    size: bigint;
    mime_type: string;
    name: string;
};
export type OrderV2 = {
    field: string;
    direction: string;
    type: string;
};
export type OpenSDKGetRecordsReq = {
    limit: number;
    offset: number;
    fields: string[];
    quickSearch?: string;
    filter: any[];
    sort: OrderV2[];
    count: boolean;
};
export type AppAccessToken = {
    expire: number;
    appAccessToken: string;
    appId: string;
};
export type TenantAccessToken = {
    expire: number;
    tenantAccessToken: string;
    appId: string;
};
export interface IInnerAPIRequest extends IInnerAPIBaseRequest, IInnerAPIOpenSDKRequest {
}
export interface IInnerAPIBaseRequest {
    createRecordBySync: (objectApiName: string, record: object, authType: string) => any;
    createRecordBySyncV3: (objectApiName: string, record: object, authType: string) => any;
    updateRecordBySync: (objectApiName: string, recordID: number, record: object, authType: string) => any;
    updateRecordBySyncV3: (objectApiName: string, recordID: string, record: object, authType: string) => any;
    deleteRecordBySync: (objectApiName: string, recordID: number, authType: string) => any;
    deleteRecordBySyncV3: (objectApiName: string, recordID: string, authType: string) => any;
    createRecordsByAsync: (objectApiName: string, records: object[], authType: string) => any;
    updateRecordsByAsync: (objectApiName: string, recordMap: Record<number, object>, authType: string) => any;
    deleteRecordsByAsync: (objectApiName: string, recordIDs: number[], authType: string) => any;
    createRecordsBySync: (objectApiName: string, records: object[], authType: string) => any;
    createRecordsBySyncV3: (objectApiName: string, records: object[], authType: string) => any;
    updateRecordsBySync: (objectApiName: string, recordMap: Record<number, object>, authType: string) => Promise<Record<number, string>>;
    updateRecordsBySyncV3: (objectApiName: string, recordMap: object[], authType: string) => Promise<Record<string, string>>;
    deleteRecordsBySync: (objectApiName: string, recordIDs: number[], authType: string) => Promise<Record<number, string>>;
    deleteRecordsBySyncV3: (objectApiName: string, recordIDs: string[], authType: string) => Promise<Record<string, string>>;
    getRecordsOrCountByCriterion: (objectApiName: string, criterion: string | Criterion, fuzzySearch: any, order: Order[], ignoreBackLookupField: boolean, fieldApiNames: string[], offset: number, limit: number, needCount: boolean, authType: string) => any;
    getRecordsV3OrCounByCriterion: (objectApiName: string, criterion: string | CriterionV3, quickQuery: string, quickQueryFields: string[], order: Order[], fieldApiNames: string[], offset: number, limit: number, needCount: boolean, authType: string) => any;
    updateWorkflowVariables: (ctx: any, instanceId: number, variables: object, variableTypes: object) => Promise<void>;
    uploadFile: (data: Stream, expire: number, fileName?: string) => Promise<UploadFileResp>;
    downloadFileByID: (fileID: string, filePath?: string) => Promise<Buffer | undefined>;
    downloadFileByToken: (fileToken: string, filePath?: string) => Promise<Buffer | undefined>;
    createMessage: (msg: any) => Promise<number>;
    updateMessage: (msgId: number, msg: any) => Promise<void>;
    getFields: (objectApiName: string) => Promise<any>;
    getField: (objectApiName: string, fieldApiName: string) => Promise<any>;
    terminateWorkflowInstance: (workflowInstanceId: number, operator: number, reason: string) => Promise<void>;
    modifyRecordsWithTransaction: (placeholders: Record<string, number>, operations: object[], authType: string, version: string) => Promise<Map<string, number>>;
    getGlobalConfigByKey: <valueT>(key: string) => Promise<valueT>;
    oql: (oql: string, args: any[], namedArgs: Record<string, any>, authType: string) => Promise<string | any[]>;
    invokeFuncSync: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
    createAsyncTaskV1: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
    createAsyncTaskV2: (name: string, params: any) => Promise<any>;
    getExecutionUserTaskInfo: (executionId: bigint) => Promise<any>;
    executeFlow: (APIName: string, options: any, async: any) => Promise<ExecutionResult>;
    revokeExecution: (executionId: number, revokeOptions: RevokeExecutionOptions) => Promise<void>;
    getExecutionInfo: (executionId: number) => Promise<ExecutionInfo>;
    getTenantInfo: (appCtx: AppCtx) => Promise<any>;
    mGetFileToken: (ids: string[]) => Promise<string>;
    getIntegrationAppAccessToken: (apiName: string) => Promise<AppAccessToken>;
    getIntegrationTenantAccessToken: (apiName: string) => Promise<TenantAccessToken>;
    getDefaultIntegrationAppAccessToken: () => Promise<AppAccessToken>;
    getDefaultIntegrationTenantAccessToken: () => Promise<TenantAccessToken>;
    getApprovalInstanceList: (options?: IApprovalInstanceListOptions) => Promise<IApprovalInstanceList>;
    getApprovalInstance: (options: IGetApprovalInstanceOptions) => Promise<IApprovalInstance>;
}
export interface IInnerAPIOpenSDKRequest {
    openSDKCreateRecordBySync: (objectApiName: string, record: object) => any;
    openSDKUpdateRecordBySync: (objectApiName: string, recordID: number, record: object) => any;
    openSDKDeleteRecordBySync: (objectApiName: string, recordID: number) => any;
    openSDKCreateRecordsBySync: (objectApiName: string, records: object[]) => any;
    openSDKUpdateRecordsBySync: (objectApiName: string, recordMap: Record<number, object>) => any;
    openSDKDeleteRecordsBySync: (objectApiName: string, recordIDs: number[]) => any;
    openSDKGetRecords: (objectApiName: string, param: OpenSDKGetRecordsReq) => any;
    openSDKUploadFile: (fileName: string, data: Buffer) => any;
    openSDKUploadAvatar: (fileName: string, data: Buffer) => any;
    openSDKDownloadAvatar: (imageID: string) => any;
    invokeFuncWithAuth: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
}
export interface IFaaSInfraRequest {
    createDistributeTaskV1: (dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any) => Promise<any>;
    createDistributeTaskV2: (dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any) => Promise<any>;
    invokeMicroserviceSync: (apiName: string, path: string, method: string, body: any) => Promise<any>;
    invokeMicroserviceAsync: (apiName: string, path: string, method: string, body: any) => Promise<any>;
}
