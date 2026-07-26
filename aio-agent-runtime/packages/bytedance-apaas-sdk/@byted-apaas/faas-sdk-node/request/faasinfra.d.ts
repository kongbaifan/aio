import { IFaaSInfraRequest } from './interface';
export declare class FaaSInfraRequest implements IFaaSInfraRequest {
    invokeMicroserviceSync(apiName: string, path: string, method: string, body: any): Promise<any>;
    invokeMicroserviceAsync(apiName: string, path: string, method: string, body: any): Promise<any>;
}
