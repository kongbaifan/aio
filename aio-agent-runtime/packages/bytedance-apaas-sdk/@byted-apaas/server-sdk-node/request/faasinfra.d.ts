import { IFaaSInfraRequest } from './interface';
export declare class FaaSInfraRequest implements IFaaSInfraRequest {
    constructor();
    createDistributeTaskV1(dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any): Promise<any>;
    createDistributeTaskV2(dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any): Promise<any>;
    invokeMicroserviceSync(apiName: string, path: string, method: string, body: any): Promise<any>;
    invokeMicroserviceAsync(apiName: string, path: string, method: string, body: any): Promise<any>;
}
