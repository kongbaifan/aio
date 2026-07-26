import { AppCtx } from '../application/application';
export declare function getDebugExtraInfo(): Record<string, string>;
export declare function getTriggerCtx(): any;
export declare function transMapToFlowVariable(params: Record<string, any>): {
    api_name: string;
    value: any;
}[];
export declare function transFlowVariableToMap(variables: {
    api_name: string;
    value: any;
}[]): Record<string, any>;
export declare function getTenantInfo(appCtx: AppCtx): Promise<any>;
export declare function getNamespaceForOpenAndFaaSSDK(): Promise<string>;
