import { _IIntegration, AppAccessToken, TenantAccessToken } from '../IIntegration';
import { AppCtx } from '../../../application/application';
export declare class _OpenSDKIntegration implements _IIntegration {
    appCtx: AppCtx;
    constructor(appCtx: AppCtx);
    getAppAccessToken(apiName: string): Promise<AppAccessToken>;
    getDefaultAppAccessToken(): Promise<AppAccessToken>;
    getDefaultTenantAccessToken(): Promise<TenantAccessToken>;
    getTenantAccessToken(apiName: string): Promise<TenantAccessToken>;
}
export declare class _Integration implements _IIntegration {
    getAppAccessToken(apiName: string): Promise<AppAccessToken>;
    getDefaultAppAccessToken(): Promise<AppAccessToken>;
    getDefaultTenantAccessToken(): Promise<TenantAccessToken>;
    getTenantAccessToken(apiName: string): Promise<TenantAccessToken>;
}
