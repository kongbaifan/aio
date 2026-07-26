import * as common from '@byted-apaas/server-common-node';
type invokeGlobalFuncT = (funcNames: string) => {
    invoke: (params?: any) => Promise<any>;
};
export declare function getFunctionSync(context?: any, logger?: common.Logger): invokeGlobalFuncT;
export declare function invokeMicroservice(): (apiName: string) => {
    /**
     * 同步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invoke: (path: string, method?: string, params?: any) => Promise<any>;
    /**
     * 异步调用微服务
     * @param path 请求路径，如：/ping
     * @param method 请求方法，默认为 GET
     * @param params 请求参数，默认为 undefined
     */
    invokeAsync: (path: string, method?: string, params?: any) => Promise<any>;
};
export {};
