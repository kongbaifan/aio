/// <reference types="node" />
import { IFaaSInfraRequest } from './interface';
export declare function requestGlobalVar(key: string): Promise<any>;
export declare function requestMongodb(param: Record<string, any>): Promise<any>;
export declare function requestFile(fileName: string, buffer: Buffer, contentType: string, option?: Object, addition?: object): Promise<any>;
export declare function requestRedis(params: {
    'cmd': string;
    args: any[];
}): Promise<any>;
export declare class FaaSInfraRequest implements IFaaSInfraRequest {
    createDistributeTaskV1(dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any): Promise<any>;
    createDistributeTaskV2(dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any): Promise<any>;
    createDistributeTaskV3(dataset: any, handlerFunc: string, progressCallbackFunc: string, completedCallbackFunc: string, options: any): Promise<any>;
}
