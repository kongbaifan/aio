import { IApprovalInstance, IApprovalInstanceListOptions, IApprovalInstanceList, IGetApprovalInstanceOptions } from '../../../request/structs';
export declare function newFlow(context: any): Flow;
export interface Flow {
    /**
     * 获取流程实例人工任务详情列表
     * @param executionId
     */
    getExecutionUserTaskInfo: (executionId: number) => Promise<FlowTaskInfo[]>;
    /**
     * 执行流程
     * @param apiName 流程的 APIName
     * @param options 流程执行选项
     * @param async 是否异步执行
     *      - params 流程入参
     * @constructor
     */
    execute: (apiName: string, options?: ExecuteOptions, async?: boolean) => Promise<ExecutionResult>;
    /**
     * 撤销流程实例 (仅支持撤销包含人工任务的流程实例)
     * @param executionId 流程实例 Id
     * @param options 撤销选项 reason: 多语原因
     * @constructor
     */
    revokeExecution: (executionId: number, options: RevokeExecutionOptions) => Promise<void>;
    /**
     * 获取流程实例信息
     * @param executionId 流程实例 Id
     * @constructor
     */
    getExecutionInfo: (executionId: number) => Promise<ExecutionInfo>;
    /**
     * 获取审批实例列表
     * @param options 请求参数，可选
     */
    getApprovalInstanceList: (options?: IApprovalInstanceListOptions) => Promise<IApprovalInstanceList>;
    /**
     * 获取审批实例详情
     * @param approvalInstanceId 实例ID
     * @param option 请求参数，可选
     */
    getApprovalInstance: (options: IGetApprovalInstanceOptions) => Promise<IApprovalInstance>;
}
export interface Execution {
    /**
     * 流程实例 id (函数被流程调用时有值)
     */
    id: number;
}
export interface ExecuteOptions {
    params: Record<string, any>;
}
export interface ExecutionResult {
    executionId: number;
    status: ExecutionStatusType;
    data: Record<string, any>;
    errCode?: string;
    errMsg?: string;
}
export type ExecutionStatusType = 'wait' | 'in_process' | 'end' | 'rejected' | 'canceled' | 'failed' | 'agreed';
export interface RevokeExecutionOptions {
    reason?: NewMultilingual;
}
export interface ExecutionInfo {
    status: ExecutionStatusType;
    data: Record<string, any>;
    errCode?: string;
    errMsg?: string;
}
export interface FlowTaskInfo {
    taskId: number;
    label: NewMultilingual;
    taskType: TaskType;
    taskStatus: TaskStatus;
    opinionList: TaskOpinion[];
    assigneeList: FlowUser[];
    startedTime: number;
    completedTime?: number;
}
export type TaskType = 'form' | 'approval' | 'CC';
export type TaskStatus = 'in_process' | 'completed' | 'canceled' | 'failed' | 'auto_end' | 'agreed' | 'rejected';
export interface NewMultilingual {
    en_US?: string;
    zh_CN?: string;
}
export interface FlowUserAvatar {
    url: string;
}
export interface FlowUser {
    userId: number;
    feishuOpenId: string;
    userName: NewMultilingual;
}
export interface TaskOpinion {
    user: FlowUser;
    feishuOpenId: number;
    opinionResult?: string;
    submitTime: number;
    opinionContent?: string;
}
