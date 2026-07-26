"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Application = exports.metaData = exports.workflow = exports.microservice = exports.cloudfunction = exports.tasks = exports.msg = exports.resources = exports.db = exports.invokeMicroservice = exports.mockGetExecutionInfo = exports.mockRevokeExecution = exports.mockExecuteFlow = exports.mockGetExecutionUserTaskInfo = exports.mockFlowFeature = exports.terminateWorkflow = exports.mountWorkflowFeature = exports.mountMetadata = exports.method = exports.setRedirectLocation = exports.toString = exports.setRespHeader = exports.getFunctionSync = void 0;
const common = require("@byted-apaas/server-common-node");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const api = require("../hooks/api");
const metadataApi = require("../context/metadata/metadata");
const tasks_1 = require("../context/tasks/tasks");
const db_1 = require("../context/db/impl/db");
const resources_1 = require("../context/resources/impl/resources");
const msg_1 = require("../context/msg/msg");
const Request = require("../request/interface");
const constants = require("../constants/constants");
const metadata_1 = require("../context/metadata/metadata");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const nodeClsCtx = common.nodeClsCtx;
const exceptions = common.exceptions;
const utils = common.utils;
const checkUtils = common.checkUtils;
const functionSources = common.constants.functionSources;
// 同步调用云函数
function getFunctionSync(context, logger) {
    return (funcName) => {
        if (utils.isOnlineDev()) {
            let oldFuncName = funcName;
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
                        let func = utils.getGlobalFunc(null, funcName);
                        if (!func) {
                            // 改为远程调用
                            return await Request.GetInstance().invokeFuncSync(idOrName, params);
                        }
                        let loopMasks = [funcName];
                        const reqCtx = nodeCls.get('loopCtx');
                        if (reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks)) {
                            if (reqCtx.loopMasks.includes(funcName)) {
                                throw new exceptions.InvalidParamError(`Task execution forms a loop.`);
                            }
                            loopMasks.push(...reqCtx.loopMasks);
                        }
                        // 修改 source 全局函数
                        const ctx = nodeCls.create('loopCtx');
                        ctx.loopMasks = loopMasks;
                        return await ctx.run(async () => {
                            const dynCtx = nodeClsCtx.getDynCtx();
                            dynCtx.source = functionSources.globalFunction;
                            return await dynCtx.run(async () => {
                                return await common.hooks.invoke(func, params, context, logger);
                            });
                        });
                    }
                }
            };
        }
        return {
            invoke: async (params) => {
                // 非微服务场景
                if (!utils.isMicroservice()) {
                    let func = undefined;
                    let requireFunc = utils.getRequireFunc();
                    if (requireFunc) {
                        try {
                            func = requireFunc(funcName);
                        }
                        catch (e) {
                        }
                    }
                    if (func) {
                        // 本地调用
                        let loopMasks = [funcName];
                        const reqCtx = nodeCls.get('loopCtx');
                        if (reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks)) {
                            if (reqCtx.loopMasks.includes(funcName)) {
                                throw new exceptions.InvalidParamError(`Task execution forms a loop.`);
                            }
                            loopMasks.push(...reqCtx.loopMasks);
                        }
                        // 修改 source 全局函数
                        const ctx = nodeCls.create('loopCtx');
                        ctx.loopMasks = loopMasks;
                        return await ctx.run(async () => {
                            const dynCtx = nodeClsCtx.getDynCtx();
                            dynCtx.source = functionSources.globalFunction;
                            return await dynCtx.run(async () => {
                                return await common.hooks.invoke(func, params, context, logger);
                            });
                        });
                    }
                }
                // 远程调用 微服务 | 函数找不到
                return await Request.GetInstance().invokeFuncSync({
                    APIName: funcName,
                    isInvokeByAPIName: true
                }, params);
            }
        };
    };
}
exports.getFunctionSync = getFunctionSync;
// 设置请求头
function setRespHeader() {
    return function () {
        switch (arguments.length) {
            case 1:
                if (checkUtils.isObject(arguments[0])) {
                    try {
                        for (let k of Object.keys(arguments[0])) {
                            utils.setHttpHeaders(k, toString(arguments[0][k]));
                        }
                    }
                    catch (err) {
                        throw new exceptions.InternalError(err.message);
                    }
                }
                else {
                    throw new exceptions.InvalidParamError('setResponseHeaders param is not a object');
                }
                break;
            case 2:
                try {
                    utils.setHttpHeaders(arguments[0], toString(arguments[1]));
                }
                catch (err) {
                    throw new exceptions.InternalError(err.message);
                }
                break;
            default:
                throw new exceptions.InvalidParamError('the number of setResponseHeaders param is 1 or 2');
        }
    };
}
exports.setRespHeader = setRespHeader;
function toString(value) {
    if (value instanceof Array) {
        let arr = [];
        for (let v of value) {
            if (typeof v === 'string') {
                arr.push(v);
            }
            else {
                arr.push(utils.stringify(v));
            }
        }
        return arr.join(', ');
    }
    else if (typeof value === 'string') {
        return value;
    }
    return utils.stringify(value);
}
exports.toString = toString;
function setRedirectLocation(context) {
    return function (location) {
        context.setResponseHeader(constants.httpHeaderKeys.location, location);
        context.setResponseHeader(constants.httpHeaderKeys.statusCode, String(constants.httpStatusCodes.redirect));
    };
}
exports.setRedirectLocation = setRedirectLocation;
// 请求方法
function method() {
    return utils.getHttpMethod();
}
exports.method = method;
function mountMetadata(context) {
    // 1.挂载metadata
    context.metadata = metadataApi.metadata(context);
    // 2.挂载metaType
    if (!global.kunlun) {
        global.kunlun = {};
    }
    global.kunlun.metaType = metadataApi.metaType();
}
exports.mountMetadata = mountMetadata;
function mountWorkflowFeature(context) {
    if (context && context.workflow) {
        context.workflow.updateVariable = common.updateVariable(context, Request.GetInstance().updateWorkflowVariables);
    }
    else {
        context.workflow = {};
    }
    // 此处挂载保证了 terminate 存在
    context.workflow.terminate = terminateWorkflow();
}
exports.mountWorkflowFeature = mountWorkflowFeature;
function terminateWorkflow() {
    return async (workflowInstanceId, options) => {
        let operator = utils.getUser()._id, reason = null;
        if (options && options.reason) {
            // instanceof 改动5
            // if (options.reason instanceof common.fieldType.Multilingual) {
            if (common.fieldType.isKFieldTypeMultilingual(options.reason)) {
                reason = options.reason.toString();
            }
            else {
                reason = new common.fieldType.Multilingual(options.reason).toString();
            }
        }
        await Request.GetInstance().terminateWorkflowInstance(workflowInstanceId, operator, reason);
    };
}
exports.terminateWorkflow = terminateWorkflow;
function mockFlowFeature(context) {
    if (!context.flow) {
        context.flow = {};
    }
    context.flow.updateVariable = common.updateVariable(context, Request.GetInstance().updateWorkflowVariables);
    context.flow.getExecutionUserTaskInfo = mockGetExecutionUserTaskInfo();
    context.flow.execute = mockExecuteFlow();
    context.flow.revokeExecution = mockRevokeExecution();
    context.flow.getExecutionInfo = mockGetExecutionInfo();
    return context.flow;
}
exports.mockFlowFeature = mockFlowFeature;
function mockGetExecutionUserTaskInfo() {
    return async (executionId) => {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) need number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().getExecutionUserTaskInfo(executionId);
    };
}
exports.mockGetExecutionUserTaskInfo = mockGetExecutionUserTaskInfo;
function mockExecuteFlow() {
    return async (apiName, options) => {
        if (!apiName || typeof apiName !== 'string') {
            throw new exceptions_1.InvalidParamError(`param's type (${apiName}) need string, but is ${typeof apiName}`);
        }
        if (options && options.params && checkUtils.isNotObject(options.params)) {
            throw new exceptions_1.InvalidParamError(`options.params's type (${options}) need object, but is ${Array.isArray(options) ? 'array' : typeof options.params}`);
        }
        if (!options) {
            options = {};
        }
        return await Request.GetInstance().executeFlow(apiName, options, false);
    };
}
exports.mockExecuteFlow = mockExecuteFlow;
function mockRevokeExecution() {
    return async (executionId, options) => {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) is need number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().revokeExecution(executionId, options);
    };
}
exports.mockRevokeExecution = mockRevokeExecution;
function mockGetExecutionInfo() {
    return async (executionId) => {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) is not matched to number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().getExecutionInfo(executionId);
    };
}
exports.mockGetExecutionInfo = mockGetExecutionInfo;
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
exports.db = new db_1.DB();
exports.resources = new resources_1._Resources();
exports.msg = new msg_1.Message();
exports.tasks = new tasks_1.Tasks();
exports.cloudfunction = api.getFunctionSync();
exports.microservice = api.invokeMicroservice();
exports.workflow = {
    terminate: terminateWorkflow(),
};
exports.metaData = new metadata_1.MetaData(null);
var impl_1 = require("../application/impl/impl");
Object.defineProperty(exports, "Application", { enumerable: true, get: function () { return impl_1.Application; } });
