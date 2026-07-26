import { IInnerAPIRequest } from './interface';
export declare class RequestHttp implements IInnerAPIRequest {
    invokeFuncSync(idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any): Promise<any>;
    invokeFuncWithAuth(idOrName: {
        APIId?: string;
        APIName?: string;
        isInvokeByAPIName: boolean;
    }, params: any): Promise<any>;
}
