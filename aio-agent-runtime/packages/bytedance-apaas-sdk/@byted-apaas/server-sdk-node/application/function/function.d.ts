import { AppCtx } from '../application';
export interface IFunction {
    /**
     * 调用函数
     * @param params 函数入参
     */
    invoke(params: Record<string, any>): Promise<any>;
}
export declare class Function implements IFunction {
    appCtx: AppCtx;
    apiName: string;
    constructor(appCtx: AppCtx, apiName: string);
    invoke(params: Record<string, any>): Promise<any>;
}
