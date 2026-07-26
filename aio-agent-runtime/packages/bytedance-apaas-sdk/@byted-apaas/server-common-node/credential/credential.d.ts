export declare class AppCredential implements ICredential {
    id: string;
    secret: string;
    tenantInfo?: TenantInfo;
    token?: string;
    expireTime?: number;
    isSystem: boolean;
    constructor(id: string, secret: string, isSystem?: boolean);
    setSystemFlag(isSystem: boolean): void;
    getToken(): Promise<string>;
    getTenantInfo(): Promise<TenantInfo>;
    refresh(): Promise<RefreshRes>;
    fetchToken(): Promise<FetchRes>;
}
export type RefreshRes = {
    token?: string;
    tenantInfo?: TenantInfo;
};
export type FetchRes = {
    accessToken: string;
    expireTime?: number;
    namespace?: string;
    tenantInfo?: TenantInfoInner;
};
export interface TenantInfoInner {
    id: number;
    domainName: string;
    tenantName: string;
    tenantType: number;
    outsideTenantInfo: {
        outsideDomainName: string;
    };
}
export interface TenantInfo {
    id: number;
    name: string;
    type: number;
    namespace: string;
    domain: string;
}
export interface ICredential {
    getToken(): Promise<string>;
    setSystemFlag(isSystem: boolean): void;
}
export declare function getFaaSCredential(): AppCredential;
export declare function getCredential(): AppCredential;
