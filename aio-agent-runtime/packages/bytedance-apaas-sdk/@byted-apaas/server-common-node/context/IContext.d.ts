import { Tenant, App, Event } from './tenant';
import { IUserWithInitiator } from './user/IUser';
export interface IContext {
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
}
export type IGfCtx = IContext;
export type IWfCtx = IContext;
export type IRaCtx = IContext;
export type ISaCtx = IContext;
