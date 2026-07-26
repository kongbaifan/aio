import { Logger } from '../utils/logger';
import { Context } from '../context/context';
/**
 * 系统代理函数首先调用 common.pre 来初始化 kunlun 和 context 的部分实现
 * @param params      用户参数结构
 * @param context     common 的公共 context 结构
 * @param requireFunc
 */
declare function pre(params: object, context: Context, requireFunc: Function): Promise<any>;
declare function invoke(userFunc: Function, params: any, context: Context, logger: Logger): Promise<any>;
declare function post(response: any, params: any, context: Context, logger: Logger): Promise<any>;
declare function error(err: Error, params: any, context: Context, logger: Logger): Promise<any>;
export { pre, invoke, post, error, };
