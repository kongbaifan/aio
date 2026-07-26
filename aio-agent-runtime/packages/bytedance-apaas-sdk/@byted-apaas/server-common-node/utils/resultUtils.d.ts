declare class Result {
    code: string;
    msg: string;
    data: Record<string, any>;
    extraInfo: Record<string, any>;
    permission: Record<string, any>;
    constructor(code: string, msg: string, data: Record<string, any>, extraInfo: Record<string, any>, permission?: any);
}
declare function success(data: Record<string, any>, permission?: any): Result;
declare function failure(err: any): Result;
declare function unknown(err: Error): Result;
declare function developerError(err: Error): Result;
export { success, failure, unknown, developerError, };
