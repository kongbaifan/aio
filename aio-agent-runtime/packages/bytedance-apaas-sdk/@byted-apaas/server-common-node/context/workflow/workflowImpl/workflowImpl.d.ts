import { workflowVariables } from '../../../data/index';
import * as workflow from '../workflow';
import { ExecuteOptions, Execution, ExecutionInfo, ExecutionResult, FlowTaskInfo, RevokeExecutionOptions, WorkflowCommon } from '../workflow';
export declare class WorkflowImpl implements workflow.WorkflowCommon {
    /**
     * 工作流的 API name
     */
    apiName: string;
    /**
     * 工作流实例的 ID
     */
    instanceId: number;
    /**
     * workflow 变量
     */
    variables: workflow._WorkflowVariablesMap;
    /**
     * workflow 变量类型
     */
    private variableTypes;
    /**
     * 1.0 传递的是 workflow
     * 2.0 传递的是 flow
     * 3.0 传递的是 flow 下面带有 variables 等结构
     *
     * 预期，同时兼容 flow & workflow 的 context
     * 优先以 flow 为准，且校验 flow 下的 variables 为 object
     * 否则降级解析 workflow 进行挂载
     */
    constructor(flowParams: any, workflowParams: any);
    /**
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
    updateVariable(variablesMap: workflow._WorkflowVariablesMap): Promise<void>;
    /**
     * 更新 workflow 变量的值
     * @param key 待更新 workflow 变量的 ApiName
     * @param value 与变量类型相对应的值
     * @example
     * ```
     * context.workflow.updateVariable('textVar', '文本')
     * ```
     */
    updateVariable<K extends keyof workflowVariables>(key: K, value: workflowVariables[K]): Promise<void>;
    /**
     * 终止进行中的工作流实例
     * @param workflowInstanceId 工作流实例 ID
     * @param options 高级配置参数，可选
     * @example
     * ```
     * context.workflow.terminate(123456, {reason: new kunlun.type.Multilingual({zh: '取消', en: 'cancel'})});
     * ```
     */
    terminate(workflowInstanceId: number, options?: workflow.TerminateOptions): Promise<void>;
    getExecutionUserTaskInfo(executionId: number): Promise<FlowTaskInfo[]>;
    execute(APIName: string, options: ExecuteOptions): Promise<ExecutionResult>;
    getExecutionInfo(executionId: number): Promise<ExecutionInfo>;
    revokeExecution(executionId: number, options: RevokeExecutionOptions): Promise<void>;
}
export declare class Flow extends WorkflowImpl implements WorkflowCommon {
    execution: Execution;
    constructor(flowParams: any, workflowParams: any);
    getExecutionUserTaskInfo(executionId: number): Promise<FlowTaskInfo[]>;
    execute(APIName: string, options?: ExecuteOptions): Promise<ExecutionResult>;
    getExecutionInfo(executionId: number): Promise<ExecutionInfo>;
    revokeExecution(executionId: number, options: RevokeExecutionOptions): Promise<void>;
}
