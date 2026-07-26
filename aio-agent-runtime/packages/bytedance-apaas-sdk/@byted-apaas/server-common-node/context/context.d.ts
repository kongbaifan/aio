import { App, Event, Tenant } from './tenant';
import { IContext } from './IContext';
import { IUserWithInitiator } from './user/IUser';
export declare class Context implements IContext {
    /**
     * 租户信息
     */
    tenant: Tenant;
    /**
     * 应用信息
     */
    app: App;
    /**
     * 用户信息
     */
    user: IUserWithInitiator;
    /**
     * 事件信息
     */
    event: Event;
    constructor(ctx: any, tenant: Tenant, app: App, user: IUserWithInitiator, event: Event, method: string | null);
}
