/// <reference types="node" />
/// <reference types="node" />
/// <reference types="node" />
import { URL, URLSearchParams } from 'url';
import { Readable } from 'stream';
export interface ITool {
    /**
     * 重试方法。需注意幂等问题，该方法不保证幂等
     *
     * @param promiseFunc 重试执行的函数，为没有入参的异步函数
     * @param options 配置参数，可选
     * @example
     * ```
     * let employee = await kunlun.tool.retry(async() => {
     *     return await context.db.object('employee').findOne();
     * },{
     *    retryCount: 3,
     *    retryDelay: 500
     * });
     * ```
     */
    retry: <T>(promiseFunc: () => Promise<T>, options?: RetryOptions) => Promise<T>;
    /**
     * 发送 http 请求
     * @param request
     * @example
     * ```
     * let postRes = await kunlun.tool.http({
     *     url: 'http://www.example.com',
     *     method: 'POST',
     *     headers: {
     *         'Content-Type': 'application/json',
     *     },
     *     body: {'hello':'world'},
     * })
     * ```
     */
    http: (request: HttpRequest) => Promise<HttpResponse>;
    /**
     * 设置泳道 (仅调试生效)
     * @param laneName 泳道名
     */
    setLaneName: (laneName: string) => void;
    /**
     * Mock 用户 ID
     * @param userID
     */
    mockUserID: (userID: number) => void;
    /**
     * 获取日志 ID
     */
    getLogID: () => string;
}
export interface RetryOptions {
    /**
     * 重试次数，最大可设置值为 10，默认值为 3
     */
    retryCount: number;
    /**
     * 重试延时，单位毫秒（ms），默认为 0ms
     */
    retryDelay: number;
}
export declare type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'HEAD' | 'DELETE' | 'OPTIONS' | 'TRACE';
export declare type ResponseType = 'json' | 'buffer' | 'text';
/**
 * HTTP 请求参数
 */
export interface HttpRequest {
    /**
     * 请求地址
     * 必填
     */
    url: string | URL;
    /**
     * 请求方法
     * (非必填)，默认为 GET（不区分大小写）
     */
    method?: Method;
    /**
     * 请求头
     * (非必填)
     */
    headers?: object;
    /**
     * 请求参数
     * (非必填)
     */
    query?: string | object | URLSearchParams;
    /**
     * 请求体
     * (非必填)
     */
    body?: string | object | Buffer | Readable;
    /**
     * 响应体类型
     * (非必填)，默认 text，支持 text,json,buffer
     */
    responseType?: ResponseType;
    /**
     * 响应编码格式
     * (非必填)，默认 utf8
     */
    encoding?: BufferEncoding;
    /**
     * 请求超时配置
     * (非必填)
     */
    timeout?: number;
}
/**
 * HTTP 响应结果
 */
export interface HttpResponse {
    /**
     * 响应状态码
     */
    statusCode?: number;
    /**
     * 响应头
     */
    headers?: object;
    /**
     * 响应体，类型依赖于 responseType
     */
    body?: string | object | Buffer;
}
