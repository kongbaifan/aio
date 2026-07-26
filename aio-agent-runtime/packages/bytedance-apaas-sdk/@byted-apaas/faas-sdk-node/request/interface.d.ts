export declare function GetHttpInstance(): IInnerAPIRequest;
export declare function GetInstance(): IInnerAPIRequest;
export declare function GetFaaSInfraInstance(): IFaaSInfraRequest;
export interface IInnerAPIRequest {
    invokeFuncSync: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
    invokeFuncWithAuth: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
}
export interface IFaaSInfraRequest {
    invokeMicroserviceSync: (apiName: string, path: string, method: string, body: any) => Promise<any>;
    invokeMicroserviceAsync: (apiName: string, path: string, method: string, body: any) => Promise<any>;
}
