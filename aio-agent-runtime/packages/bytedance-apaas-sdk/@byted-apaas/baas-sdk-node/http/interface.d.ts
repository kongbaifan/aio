export declare function GetHttpInstance(): IInnerAPIRequest;
export declare function GetInstance(): IInnerAPIRequest;
export declare function GetFaaSInfraInstance(): IFaaSInfraRequest;
export interface IInnerAPIRequest {
    createAsyncTaskV1: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
    createAsyncTaskV2: (name: string, params: any) => Promise<any>;
    invokeFuncSync: (idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any) => Promise<any>;
}
export interface IFaaSInfraRequest {
    createDistributeTaskV1: (dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any) => Promise<any>;
    createDistributeTaskV2: (dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any) => Promise<any>;
    createDistributeTaskV3: (dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any) => Promise<any>;
}
