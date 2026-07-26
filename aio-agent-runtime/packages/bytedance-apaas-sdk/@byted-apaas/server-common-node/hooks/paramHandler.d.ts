import { App, Tenant, Event } from '../context/tenant';
import { User } from '../context/user';
/**
 * params: {
 *     params: 用户参数，需要替换外层的params
 *     context: 上下文参数，需要把值添加到context下
 * }
 *
 * @param params
 * @param context
 * @returns {Promise<*[]>}
 */
export declare function handle(params: any, context: any): any[];
export declare function parseServiceIDByContext(context: any): any;
export declare function parseTenantByContext(context: any): Tenant;
export declare function parseUserByContext(context: any): User;
export declare function parseAppByContext(context: any): App;
export declare function getEventByContext(context: any): Event;
export declare function parseBoeByContext(context: any): any;
export declare function parseSource(context: any): any;
export declare function parseEnv(): string;
