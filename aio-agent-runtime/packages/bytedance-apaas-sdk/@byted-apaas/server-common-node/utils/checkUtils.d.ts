/**
 * 仅仅是Object，不是Array
 *
 * @param value
 * @returns {boolean}
 */
declare function isObject(value: unknown): boolean;
/**
 * 这里把数组认为也不是对象
 *
 * @param value
 */
declare function isNotObject(value: unknown): boolean;
/**
 * ctx不可以为空
 *
 * @param ctx
 */
declare function checkCtx(ctx: any): void;
/**
 * 校验headers
 * 1.不可以为空
 * 2.是一个对象
 *
 * @param ctx
 */
declare function checkHeaders(ctx: any): void;
/**
 * 校验tenant
 * 1.不可以为空
 * 2.有属性name，id, type
 *
 * @param ctx
 */
declare function checkTenant(ctx: any): void;
/**
 * 校验initiator
 * 1.不可以为空
 * 2.有属性id
 *
 * @param ctx
 */
declare function checkInitiator(ctx: any): void;
/**
 * 校验workflow
 * 1.不为空
 * 2.是对象
 * 3.instanceId不为空
 *
 * @param ctx
 */
declare function checkWorkflowAndFlow(ctx: any): void;
/**
 * 校验workflow.variables
 * 1.不为空
 * 2.是对象
 *
 * @param ctx
 * @param key
 */
declare function checkWorkflowAndFlowVariableTypes(ctx: any, key: string): void;
declare function checkFile(file: string): void;
declare function needCheckSign(ctx: any): boolean;
declare function checkTriggerSign(params: any, context: any): void;
export { isObject, isNotObject, checkCtx, checkHeaders, checkTenant, checkInitiator, checkWorkflowAndFlow, checkWorkflowAndFlowVariableTypes, checkFile, needCheckSign, checkTriggerSign, };
