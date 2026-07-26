import { HttpConfig, PostHttpConfig } from './config';
export declare class HttpOptions {
    method: string;
    timeout: Record<string, number>;
    agent: Record<string, any>;
    headers: Record<string, any>;
    _reqPath: string;
    _reqServer: string;
    _reqMethod: string;
    json: Record<string, any>;
    responseType: string;
    body: any;
    retry: number | Record<string, any>;
    _dataType: string;
    _skipPreIntercept: boolean;
    constructor(method: string, timeout: Record<string, number>, agent: Record<string, any>, headers: Record<string, any>, reqPath: string, reqServer: string, reqMethod: string, retry?: number | Record<string, any>);
}
export declare function getOptions(ctx: any, httpConfig: HttpConfig): HttpOptions;
export declare function getTokenOptions(ctx: any, httpConfig: HttpConfig): HttpOptions;
export declare function dealOptionForENV(options: HttpOptions): void;
export declare function dealOptionForLane(options: HttpOptions): void;
export declare function doRequestWithConnRetry(path: string, options: HttpOptions, connRetryTimes?: number): Promise<any>;
export declare function getTokenWithCache(doRequestPromise: Function, tokenTypeKey: string, httpConfig: PostHttpConfig, bodyJson: object): Promise<string>;
