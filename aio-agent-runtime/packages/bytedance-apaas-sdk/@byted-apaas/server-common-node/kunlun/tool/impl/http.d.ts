import { HttpRequest, HttpResponse } from '../Itool';
import { Options, Response } from 'got';
/**
 * Http 请求类
 */
export declare class Http {
    static httpTool(request: HttpRequest): Promise<HttpResponse>;
    static requestWithHttpConnRetry(options: Options, retryTimes?: number): Promise<Response>;
    static getHttpResponse(response: Response): Promise<HttpResponse>;
}
