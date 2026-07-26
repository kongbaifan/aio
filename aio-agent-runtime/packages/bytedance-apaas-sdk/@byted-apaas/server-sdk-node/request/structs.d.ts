export interface IApprovalInstanceListReq {
    start_time?: number;
    end_time?: number;
    page_size?: number;
    page_token?: string;
}
export interface IGetApprovalInstanceListResp {
    approval_instance_ids: number[];
    page_token: string;
    count: number;
    has_more: boolean;
}
export interface IGetApprovalInstanceResp {
    approval_instance: {
        id: number;
        label: Record<string, string>;
        initiator: number;
        instance_start_time: number;
        status: string;
        tasks: {
            id: number;
            task_type: string;
            task_status: string;
            task_start_time: number;
            task_end_time: number;
            form_data: string;
            approval_logic: string;
            approvers: number[];
            assigners: number[];
            task_url: string;
        }[];
        comments: {
            id: number;
            commenter: number;
            content: string;
            create_at: number;
            update_at: number;
        }[];
    };
}
export interface IApprovalInstanceReq {
    includes: string;
}
export interface IApprovalInstanceListOptions {
    startTime?: number;
    endTime?: number;
    pageSize?: number;
    pageToken?: string;
}
export interface IApprovalInstanceList {
    approvalInstanceIds: number[];
    pageToken: string;
    count: number;
    hasMore: boolean;
}
export declare enum ApprovalInstanceStatus {
    IN_PROCESS = "in_process",
    AGREED = "agreed",
    INPROCESS = "rejected",
    CANCELED = "canceled",
    FAILED = "failed",
    COMPLETED = "completed",
    UNSTARTED = "unstarted",
    AUTO_END = "auto_end",
    TERMINATED = "terminated"
}
export interface IApprovalInstance {
    id: number;
    label: Record<string, string>;
    initiator: number;
    instanceStartTime: number;
    status: string;
    tasks: IApprovalTask[];
    comments: IApprovalComment[];
}
export interface IApprovalComment {
    id: number;
    commenter: number;
    content: string;
    createAt: number;
    updateAt: number;
}
export interface IApprovalTask {
    id: number;
    taskType: string;
    taskStatus: string;
    taskStartTime: number;
    taskEndTime: number;
    formData: string;
    approvalLogic: string;
    approvers: number[];
    assigners: number[];
    taskURL: string;
}
export interface IGetApprovalInstanceOptions {
    approvalInstanceId: number;
    includeFormData?: boolean;
    includeContent?: boolean;
}
