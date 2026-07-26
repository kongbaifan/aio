"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FaaSInfraRequest = void 0;
const common = require("@byted-apaas/server-common-node");
const headers = common.constants.headers;
const commonHttp = common.http;
const faasinfra = common.http.faasinfra;
const faasinfraHttpPath = common.http.faasinfraHttpPath;
const replaceKeys = common.http.replaceKeys;
const exceptions = common.exceptions;
const utils = common.utils;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const loopMasksKey = headers.loopMasksKey;
const loopCtxKey = headers.loopCtxKey;
const url_1 = require("url");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
class FaaSInfraRequest {
    constructor() {
    }
    async createDistributeTaskV1(dataset, handlerFunc, progressCallbackFunc, completedCallbackFunc, options) {
        // 1.获取 options
        let config = commonHttp.getOptions(null, faasinfraHttpPath.createDistributedTask);
        // 2.构造url
        let urlPath = config._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        // 3.请求
        config.json = {
            'domainName': utils.getTenantNameFromCtx(),
            'namespace': utils.getNamespaceFromCtx(),
            'userId': utils.getUserIDFromCtx(),
            dataset,
            handlerFunc,
            progressCallbackFunc,
            completedCallbackFunc,
            options,
        };
        let task_id = utils.getTriggerTaskID();
        if (task_id) {
            config.json[headers.triggerTaskId] = task_id;
        }
        let loopCtx = nodeCls.get(loopCtxKey);
        if (checkLoopCtx(loopCtx)) {
            config.json[loopMasksKey] = loopCtx.loopMasks;
            if (!utils.isMicroservice() && (handlerFunc !== '' && config.json[loopMasksKey].includes(utils.handleFuncName({}, handlerFunc))) ||
                (progressCallbackFunc !== '' && config.json[loopMasksKey].includes(utils.handleFuncName({}, progressCallbackFunc))) ||
                (completedCallbackFunc !== '' && config.json[loopMasksKey].includes(utils.handleFuncName({}, completedCallbackFunc)))) {
                throw new exceptions.InvalidParamError('Task execution forms a loop.');
            }
        }
        return await faasinfra.doRequest(null, urlPath, config);
    }
    async createDistributeTaskV2(dataset, handlerFunc, progressCallbackFunc, completedCallbackFunc, options) {
        // 1.获取 options
        let config = commonHttp.getOptions(null, faasinfraHttpPath.createDistributedTaskV2);
        // 2.构造url
        let urlPath = config._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        // 3.请求
        config.json = {
            'domainName': utils.getTenantNameFromCtx(),
            'namespace': utils.getNamespaceFromCtx(),
            'userId': utils.getUserIDFromCtx(),
            dataset,
            handlerFunc,
            progressCallbackFunc,
            completedCallbackFunc,
            options,
            'extra': getDebugExtraInfo(),
        };
        let task_id = utils.getTriggerTaskID();
        if (task_id) {
            config.json[headers.triggerTaskId] = task_id;
        }
        let loopCtx = nodeCls.get(loopCtxKey);
        if (checkLoopCtx(loopCtx)) {
            config.json[loopMasksKey] = loopCtx.loopMasks;
            if ((handlerFunc !== '' && config.json[loopMasksKey].includes(handlerFunc)) ||
                (progressCallbackFunc !== '' && config.json[loopMasksKey].includes(progressCallbackFunc)) ||
                (completedCallbackFunc !== '' && config.json[loopMasksKey].includes(completedCallbackFunc))) {
                throw new exceptions.InvalidParamError(`Task execution forms a loop.`);
            }
        }
        return await faasinfra.doRequest(null, urlPath, config);
    }
    async invokeMicroserviceSync(apiName, path, method, body) {
        let reqPath = faasinfraHttpPath.invokeMicroserviceSync;
        let options = commonHttp.getOptions(null, reqPath);
        let urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        options.json = {
            'microserviceId': apiName,
            path,
            method,
            'query': parseQueryParams(path),
        };
        // 处理 body 参数
        if (method.toUpperCase() !== 'GET') {
            options.json.body = JSON.stringify(body);
        }
        return await faasinfra.doRequest(null, urlPath, options);
    }
    async invokeMicroserviceAsync(apiName, path, method, body) {
        let reqPath = faasinfraHttpPath.invokeMicroserviceAsync;
        let options = commonHttp.getOptions(null, reqPath);
        let urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        options.json = {
            'microserviceId': apiName,
            path,
            method,
            'query': parseQueryParams(path),
        };
        // 处理 body 参数
        if (method.toUpperCase() !== 'GET') {
            options.json.body = JSON.stringify(body);
        }
        return await faasinfra.doRequest(null, urlPath, options);
    }
}
exports.FaaSInfraRequest = FaaSInfraRequest;
function getDebugExtraInfo() {
    let extra = {
        'FunctionFrameVersion': 'FunctionFrameV2',
    };
    if (utils.isDebug()) {
        extra.DebugInfo = utils.getDebugCode();
    }
    return extra;
}
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
function parseQueryParams(path) {
    let params = {};
    const url = new url_1.URL(path, 'https://aa.bb.cc');
    for (let [k, v] of url.searchParams.entries()) {
        if (typeof (k) !== 'string') {
            throw new exceptions_1.InternalError(`The type of k should be string, but ${typeof (k)}`);
        }
        if (typeof (v) !== 'string') {
            throw new exceptions_1.InternalError(`The type of v should be string, but ${typeof (v)}`);
        }
        params[k] = v.split(',');
    }
    if (Object.keys(params).length === 0) {
        return undefined;
    }
    return params;
}
