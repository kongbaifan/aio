import { _LangType } from '../kunlun/type/type';
export declare enum TenantType {
    NORMAL = 1,
    FEISHU = 2,
    DEVORG = 3,
    SANDBOX = 4
}
export declare class Tenant {
    /**
     * 当前租户的名称
     */
    name: string;
    /**
     * 当前租户的 ID
     */
    id: number;
    /**
     * 当前租户的类型
     * 1: Normal
     * 2: Feishu
     * 3: Devorg
     * 4: Sandbox
     */
    type: TenantType;
    /**
     * 当前租户的个性化域名
     */
    domain: string;
    constructor(params: any);
}
export declare class App {
    /**
     * 当前应用的命名空间
     */
    namespace: string;
    /**
     * 当前应用的名称
     */
    label: _LangType;
    /**
     * 创建人
     */
    createdBy: {
        _id: number;
    };
    /**
     * 创建时间
     */
    createdAt: number;
}
export declare class Event {
    /**
     * 类型
     */
    type: string;
    /**
     * 名称
     */
    name: _LangType;
    /**
     * 唯一标识 APIName
     */
    apiName: string;
    /**
     * 实例 ID
     */
    instanceId: number;
}
