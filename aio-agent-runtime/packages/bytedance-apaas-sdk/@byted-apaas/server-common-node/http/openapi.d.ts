import { HttpOptions } from './request';
import { LocaleWithUID } from '../context/user/types';
export declare function doRequest(ctx: any, urlPath: string, options: HttpOptions): Promise<any>;
export declare function mGetUserLocaleInfo(reqUserIDList: number[]): Promise<LocaleWithUID[]>;
export declare function getAppToken(): Promise<string>;
export declare function getAppTokenHttp(clientID?: string, clientSecret?: string): Promise<any>;
export declare function getFunctionMeta(functionAPIName: string): Promise<{
    apiName: any;
    input: any;
    output: any;
}>;
export declare function getFunctionMetaWithCache(functionAPIName: string): Promise<any>;
