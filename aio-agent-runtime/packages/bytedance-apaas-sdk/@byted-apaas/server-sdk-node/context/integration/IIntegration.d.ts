export type AppAccessToken = {
    expire: number;
    appAccessToken: string;
    appId: string;
};
export type TenantAccessToken = {
    expire: number;
    tenantAccessToken: string;
    appId: string;
};
export interface _IIntegration {
    /**
     * 获取飞书集成 app access token
     * @param apiName 飞书集成的 API Name
     */
    getAppAccessToken(apiName: string): Promise<AppAccessToken>;
    /**
     * 获取飞书集成 tenant access token
     * @param apiName 飞书集成的 API Name
     */
    getTenantAccessToken(apiName: string): Promise<TenantAccessToken>;
    /**
     * 获取默认飞书集成 app access token
     */
    getDefaultAppAccessToken(): Promise<AppAccessToken>;
    /**
     * 获取默认飞书集成 tenant access token
     */
    getDefaultTenantAccessToken(): Promise<TenantAccessToken>;
}
