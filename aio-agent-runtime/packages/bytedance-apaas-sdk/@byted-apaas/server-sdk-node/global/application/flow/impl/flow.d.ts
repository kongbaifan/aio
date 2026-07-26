import { Flow as IFlow, ExecuteOptions, ExecutionResult, ExecutionInfo, FlowTaskInfo, RevokeExecutionOptions, Execution } from '../flow';
import { IApprovalInstance, IApprovalInstanceList, IApprovalInstanceListOptions, IGetApprovalInstanceOptions } from "../../../../request/structs";
export declare class Flow implements IFlow {
    execution: Execution;
    /**
    * 工作流的 API name
    */
    apiName: string;
    /**
     * 工作流实例的 ID
     */
    instanceId: number;
    constructor(flowParams: any);
    execute(apiName: string, options: ExecuteOptions | undefined, async?: boolean | undefined): Promise<ExecutionResult>;
    getExecutionInfo(executionId: number): Promise<ExecutionInfo>;
    getExecutionUserTaskInfo(executionId: number): Promise<FlowTaskInfo[]>;
    revokeExecution(executionId: number, options: RevokeExecutionOptions): Promise<void>;
    getApprovalInstanceList(options?: IApprovalInstanceListOptions): Promise<IApprovalInstanceList>;
    getApprovalInstance(options: IGetApprovalInstanceOptions): Promise<IApprovalInstance>;
}
