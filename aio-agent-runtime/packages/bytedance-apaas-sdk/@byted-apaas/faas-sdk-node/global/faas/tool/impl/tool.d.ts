import { HttpRequest, HttpResponse, ITool, RetryOptions } from '../itool';
export declare class Tool implements ITool {
    retry<T>(promiseFunc: () => Promise<T>, options?: RetryOptions): Promise<T>;
    http(request: HttpRequest): Promise<HttpResponse>;
    setLaneName(laneName: string): void;
    mockUserID(userID: number): void;
    getLogID(): string;
}
/**
 * 工具方法
 */
export declare const tool: ITool;
