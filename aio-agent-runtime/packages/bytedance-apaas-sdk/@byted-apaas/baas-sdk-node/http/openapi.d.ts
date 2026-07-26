import { IInnerAPIRequest } from './interface';
export declare class RequestHttp implements IInnerAPIRequest {
    createAsyncTaskV1(idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any): Promise<any>;
    createAsyncTaskV2(name: string, params: any): Promise<any>;
    invokeFuncSync(idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any): Promise<any>;
}
