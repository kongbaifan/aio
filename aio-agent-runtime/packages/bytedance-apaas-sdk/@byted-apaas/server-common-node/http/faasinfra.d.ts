import { HttpOptions } from './request';
declare function doRequest(ctx: any, urlPath: string, options: HttpOptions): Promise<any>;
declare function sendLog(param: Record<string, any>): Promise<any>;
export declare function getServiceToken(): Promise<string>;
export { doRequest, sendLog, };
