import { workflowVariables, currentObjApiName, metadataMap } from '../../data';
import { Multilingual } from '../../kunlun/type/type';
export type _WorkflowVariablesMap = {
    [K in keyof workflowVariables]?: workflowVariables[K];
};
export type _WorkflowVariablesHasTriggerRecord = {
    _triggerRecord: any;
    _triggerRecordBefore: any;
};
/**
 * target record 被使用于 workflow 场景下
 */
export interface TargetRecord {
    /**
     * workflow 被触发时，原始的记录信息
     */
    original: metadataMap[currentObjApiName];
    /**
     * workflow 运行到当前位置的记录信息
     */
    proposed: metadataMap[currentObjApiName];
}
/**
 * 高级配置参数，可选
 */
export declare interface TerminateOptions {
    /**
     * 终止流程的原因
     */
    reason: Multilingual;
}
export interface WorkflowCommon {
    /**
     * 工作流实例的 ID
     */
    instanceId: number;
    /**
     * @deprecated 已废弃，在流程 2.0 中不传该参数了，流程 1.0 通过 invokeContext 传到 cloudfunction
     * workflow 变量
     */
    variables: object;
    /**
     * @deprecated 已废弃
     * 更新 workflow 变量的值
     * @param variablesMap 多个待更新 workflow 变量的 ApiName 及对应变量类型的值
     * @paramExample {_initialRecord: {gender: 'male'}, textVar: '文本'}
     * @example
     * ```
     * context.workflow.updateVariable({
     *     _initialRecord: {gender: 'male'},
     *     textVar: '文本'
     * })
     * ```
     */
    updateVariable(variablesMap: object): Promise<void>;
    /**
     * @deprecated 已废弃
     * 更新 workflow 变量的值
     * @param key 待更新 workflow 变量的 ApiName
     * @param value 与变量类型相对应的值
     * @example
     * ```
     * context.workflow.updateVariable('textVar', '文本')
     * ```
     */
    updateVariable(key: string, value: any): Promise<void>;
}
export interface WorkflowExtra {
    /**
     * 流程实例详情 (仅函数被流程调用时有值) TODO, lowcode1.0 NO
     */
    execution: Execution;
}
export interface WorkflowCommon {
    /**
     * 获取流程实例人工任务详情列表
     * @param executionId
     */
    getExecutionUserTaskInfo(executionId: number): Promise<FlowTaskInfo[]>;
    /**
     * 执行流程
     * @param APIName 流程的 APIName
     * @param options 流程执行选项
     *      - params 流程入参
     * @constructor
     */
    execute(APIName: string, options?: ExecuteOptions): Promise<ExecutionResult>;
    /**
     * 撤销流程实例 (仅支持撤销包含人工任务的流程实例)
     * @param executionId 流程实例 Id
     * @param options 撤销选项 reason: 多语原因
     * @constructor
     */
    revokeExecution(executionId: number, options: RevokeExecutionOptions): Promise<void>;
    /**
     * 获取流程实例信息
     * @param executionId 流程实例 Id
     * @constructor
     */
    getExecutionInfo(executionId: number): Promise<ExecutionInfo>;
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
