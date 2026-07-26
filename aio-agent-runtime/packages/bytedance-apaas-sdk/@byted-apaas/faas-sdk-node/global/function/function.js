"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.invokeMicroservice = exports.getFunctionSync = void 0;
const common = require("@byted-apaas/server-common-node");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const Request = require("../../request/interface");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const nodeClsCtx = common.nodeClsCtx;
const exceptions = common.exceptions;
const utils = common.utils;
const functionSources = common.constants.functionSources;
// 同步调用云函数
function getFunctionSync(context, logger) {
    return (funcName) => {
        if (utils.isOnlineDev()) {
            const oldFuncName = funcName;
            if (!utils.isMicroservice()) {
                funcName = utils.handleFuncName(null, funcName);
                if (!funcName) {
                    throw new exceptions.InvalidParamError(`The function (${oldFuncName}) does not exist, please confirm ${oldFuncName} exists and has been deployed.`);
                }
            }
            else {
                funcName = undefined;
            }
            let idOrName = {};
            // 2.0 通过 apiAlias 触发
            if (funcName === oldFuncName) {
                idOrName = {
                    APIName: funcName,
                    isInvokeByAPIName: true,
                };
            }
            else if (utils.isMicroservice()) {
                // 微服务
                idOrName = {
                    APIName: oldFuncName,
                    isInvokeByAPIName: true,
                };
            }
            else { // 1.0 通过 apiID 触发
                idOrName = {
                    APIId: funcName,
                    isInvokeByAPIName: false,
                };
            }
            return {
                invoke: async (params) => {
                    // 微服务的场景
                    if (utils.isMicroservice()) {
                        return await Request.GetInstance().invokeFuncSync(idOrName, params);
                    }
                    else {
                        const func = utils.getGlobalFunc(null, funcName);
                        if (!func) {
                            // 改为远程调用
                            return await Request.GetInstance().invokeFuncSync(idOrName, params);
                        }
                        const loopMasks = [funcName];
                        const reqCtx = nodeCls.get('loopCtx');
                        if (reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks)) {
                            if (reqCtx.loopMasks.includes(funcName)) {
                                throw new exceptions.InvalidParamError('Task execution forms a loop.');
                            }
                            loopMasks.push(...reqCtx.loopMasks);
                        }
                        // 修改 source 全局函数
                        const ctx = nodeCls.create('loopCtx');
                        ctx.loopMasks = loopMasks;
                        return await ctx.run(async () => {
                            const dynCtx = nodeClsCtx.getDynCtx();
                            dynCtx.source = functionSources.globalFunction;
                            return await dynCtx.run(async () => await common.hooks.invoke(func, params, context, logger));
                        });
                    }
                },
            };
        }
        return {
            invoke: async (params) => {
                // 非微服务场景
                if (!utils.isMicroservice()) {
                    let func = undefined;
                    const requireFunc = utils.getRequireFunc();
                    if (requireFunc) {
                        try {
                            func = requireFunc(funcName);
                        }
                        catch (e) {
                            console.log(e);
                        }
                    }
                    if (func) {
                        // 本地调用
                        const loopMasks = [funcName];
                        const reqCtx = nodeCls.get('loopCtx');
                        if (reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks)) {
                            if (reqCtx.loopMasks.includes(funcName)) {
                                throw new exceptions.InvalidParamError('Task execution forms a loop.');
                            }
                            loopMasks.push(...reqCtx.loopMasks);
                        }
                        // 修改 source 全局函数
                        const ctx = nodeCls.create('loopCtx');
                        ctx.loopMasks = loopMasks;
                        return await ctx.run(async () => {
                            const dynCtx = nodeClsCtx.getDynCtx();
                            dynCtx.source = functionSources.globalFunction;
                            return await dynCtx.run(async () => common.hooks.invoke(func, params, context, logger));
                        });
                    }
                }
                // 远程调用 微服务 | 函数找不到
                return await Request.GetInstance().invokeFuncSync({
                    APIName: funcName,
                    isInvokeByAPIName: true,
                }, params);
            },
        };
    };
}
exports.getFunctionSync = getFunctionSync;
function invokeMicroservice() {
    /**
     * 微服务
     * @param apiName 微服务的名称
     */
    return function (apiName) {
        if (!apiName || typeof (apiName) !== 'string') {
            throw new exceptions_1.InvalidParamError(`The apiName (${apiName}) is invalid and should be a non-empty field string.`);
        }
        return {
            /**
             * 同步调用微服务
             * @param path 请求路径，如：/ping
             * @param method 请求方法，默认为 GET
             * @param params 请求参数，默认为 undefined
             */
            invoke: async (path, method = 'GET', params = undefined) => {
                if (!path || typeof (path) !== 'string') {
                    throw new exceptions_1.InvalidParamError(`The path (${path}) is invalid and should be a non-empty field string.`);
                }
                if (!method || typeof (method) !== 'string') {
                    throw new exceptions_1.InvalidParamError(`The method (${method}) is invalid and should be a non-empty field string.`);
                }
                return await Request.GetFaaSInfraInstance().invokeMicroserviceSync(apiName, path, method, params);
            },
            /**
             * 异步调用微服务
             * @param path 请求路径，如：/ping
             * @param method 请求方法，默认为 GET
             * @param params 请求参数，默认为 undefined
             */
            invokeAsync: async (path, method = 'GET', params = undefined) => {
                if (!path || typeof (path) !== 'string') {
                    throw new exceptions_1.InvalidParamError(`The path (${path}) is invalid and should be a non-empty field string.`);
                }
                if (!method || typeof (method) !== 'string') {
                    throw new exceptions_1.InvalidParamError(`The method (${method}) is invalid and should be a non-empty field string.`);
                }
                return await Request.GetFaaSInfraInstance().invokeMicroserviceAsync(apiName, path, method, params);
            },
        };
    };
}
exports.invokeMicroservice = invokeMicroservice;
