import { HttpRequest, HttpResponse, ITool, IToolsExtra, RetryOptions } from '../Itool';
import { TenantInfo } from '../../../credential/credential';
export declare class Tool implements ITool, IToolsExtra {
    retry<T>(promiseFunc: () => Promise<T>, options?: RetryOptions): Promise<T>;
    http(request: HttpRequest): Promise<HttpResponse>;
    setLaneName(laneName: string): void;
    getTenantInfo(): Promise<TenantInfo>;
}
/**
 * 工具方法
 */
export declare const tool: ITool & IToolsExtra;
