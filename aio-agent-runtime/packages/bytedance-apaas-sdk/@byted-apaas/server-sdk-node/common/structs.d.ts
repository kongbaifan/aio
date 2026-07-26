export interface BatchResult {
    code: string;
    msg: string;
    data?: BatchResultData[];
    hasError?: () => boolean;
}
export interface BatchResultData {
    success: boolean;
    _id: number | string;
    errors?: BatchResultDataError[];
}
export interface BatchResultDataError {
    code: string;
}
export declare function NewBatchResult(recordIDs: number[] | string[], errMap: Record<number | string, string>): BatchResult;
