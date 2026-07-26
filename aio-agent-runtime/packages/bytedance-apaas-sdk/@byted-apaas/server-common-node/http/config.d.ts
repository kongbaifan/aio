declare class HttpConfig {
    method: string;
    path: string;
    reqTimeout: number;
    reqTimeoutTccKey: string;
    connTimeout: number;
    connTimeoutTccKey: string;
    secureConnTimeout: number;
    secureConnTimeoutTccKey: string;
    /**
     * @param method                请求方法
     * @param path                  请求path
     * @param reqTimeoutTccKey      请求超时时间的 tcc key
     * @param reqTimeout            请求超时时间，默认值12s
     * @param connTimeout           连接超时时间，默认值2s
     * @param secureConnTimeout     TLS 连接超时时间，默认值1s
     */
    constructor(method: string, path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number, secureConnTimeout?: number);
    /**
     * 获取请求超时时间
     *
     * @returns {number|*}
     */
    getReqTimeout(): any;
    /**
     * 获取连接超时时间
     *
     * @returns {number|*}
     */
    getConnTimeout(): any;
    /**
     * 获取TLS连接超时时间
     *
     * @returns {number|*}
     */
    getSecureConnTimeout(): any;
    /**
     * 获取请求的服务，如 openapi 或 faasinfra
     *
     * @returns {*}
     */
    getReqServer(): string;
    /**
     * 获取请求方法
     *
     * @returns {*}
     */
    getReqMethod(): string;
}
declare class GetHttpConfig extends HttpConfig {
    constructor(path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number);
}
declare class PostHttpConfig extends HttpConfig {
    constructor(path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number);
}
declare class PutHttpConfig extends HttpConfig {
    constructor(path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number);
}
declare class DeleteHttpConfig extends HttpConfig {
    constructor(path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number);
}
declare class PatchHttpConfig extends HttpConfig {
    constructor(path: string, reqTimeoutTccKey: string, reqTimeout?: number, connTimeout?: number);
}
export declare function setTempUseLGW(): void;
declare function concatHost(server: string, path: string): string;
declare function getBaseUrl(server: string): any;
export declare function getAuthorizationV2(server: string): Promise<any>;
/**
 * @deprecated
 * @param server
 */
declare function getAuthorization(server: string): string;
/**
 * @deprecated
 */
declare function setOpenapiHostAndToken(host: string, authorization: string): void;
/**
 * @deprecated
 */
declare function getOpenapiHostAndToken(): {
    host: string;
    authorization: any;
};
/**
 * @deprecated
 */
declare function setFaasinfraHostAndToken(host: string, authorization: string): void;
/**
 * @deprecated
 */
declare function getFaasinfraHostAndToken(): {
    host: string;
    authorization: any;
};
/**
 * @deprecated
 */
declare function initHttpConf(): void;
export { HttpConfig, GetHttpConfig, PutHttpConfig, PostHttpConfig, DeleteHttpConfig, PatchHttpConfig, initHttpConf, setOpenapiHostAndToken, getOpenapiHostAndToken, setFaasinfraHostAndToken, getFaasinfraHostAndToken, concatHost, getBaseUrl, getAuthorization, };
