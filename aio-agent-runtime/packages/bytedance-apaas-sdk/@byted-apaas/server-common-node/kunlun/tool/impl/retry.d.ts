import { RetryOptions } from '../Itool';
/**
 * 重试工具类
 */
export declare class Retry {
    static retryTool<T>(promiseFunc: () => Promise<T>, retryConfig?: RetryOptions): Promise<T>;
    static retryFunc(promiseFunc: () => Promise<any>, retryConfig?: RetryOptions): Promise<any>;
}
