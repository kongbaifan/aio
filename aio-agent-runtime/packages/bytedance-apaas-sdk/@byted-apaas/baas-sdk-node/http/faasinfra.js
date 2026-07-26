"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FaaSInfraRequest = exports.requestRedis = exports.requestFile = exports.requestMongodb = exports.requestGlobalVar = void 0;
const common = require("@byted-apaas/server-common-node");
const commonHttp = common.http;
const faasinfra = common.http.faasinfra;
const commonFaasinfraHttpPath = common.http.faasinfraHttpPath;
const replaceKeys = common.http.replaceKeys;
const utils = common.utils;
const checkUtils = common.checkUtils;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const BSON = require('bson'); //nolint:byted_s_ts_no_require_imports
const bson = new BSON();
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const headers = common.constants.headers;
const loopMasksKey = headers.loopMasksKey;
const loopCtxKey = headers.loopCtxKey;
const exceptions = common.exceptions;
const FormData = require("form-data");
const constants_1 = require("./constants");
const constants_2 = require("../constants/constants");
async function requestGlobalVar(key) {
    let options = commonHttp.getOptions(null, constants_1.faasinfraHttpPath.requestGlobalVar);
    let urlPath = options._reqPath.replace(replaceKeys.serviceID, utils.getServiceId());
    urlPath = urlPath.replace(replaceKeys.key, key);
    options.headers[constants_2.serviceIDKey] = utils.getServiceId();
    return await faasinfra.doRequest(null, urlPath, options);
}
exports.requestGlobalVar = requestGlobalVar;
async function requestMongodb(param) {
    let options = commonHttp.getOptions(null, constants_1.faasinfraHttpPath.requestMongodb);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
    options.body = bson.serialize(param, { serializeFunctions: true });
    options.headers[constants_2.serviceIDKey] = utils.getServiceId();
    options.headers['content-type'] = 'application/bson';
    options._dataType = 'bson';
    return await faasinfra.doRequest(null, urlPath, options);
}
exports.requestMongodb = requestMongodb;
async function requestFile(fileName, buffer, contentType, option = null, addition) {
    let options = commonHttp.getOptions(null, constants_1.faasinfraHttpPath.requestFile);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
    let formData = new FormData();
    formData.append(constants_2.fileFieldName, buffer, {
        filename: fileName,
        contentType: contentType,
    });
    if (checkUtils.isObject(option)) {
        formData.append(constants_2.fileOption, JSON.stringify(option));
    }
    if (checkUtils.isObject(addition)) {
        formData.append(constants_2.fileAddition, JSON.stringify(addition));
    }
    options.responseType = 'buffer';
    options.body = formData;
    let formHeaders = formData.getHeaders();
    for (const key of Object.keys(formHeaders)) {
        options.headers[key] = formHeaders[key];
    }
    options.headers[constants_2.serviceIDKey] = utils.getServiceId();
    options._dataType = 'bson';
    return await faasinfra.doRequest(null, urlPath, options);
}
exports.requestFile = requestFile;
async function requestRedis(params) {
    let options = commonHttp.getOptions(null, constants_1.faasinfraHttpPath.requestRedis);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
    options.json = params;
    options.headers[constants_2.serviceIDKey] = utils.getServiceId();
    return await faasinfra.doRequest(null, urlPath, options);
}
exports.requestRedis = requestRedis;
class FaaSInfraRequest {
    async createDistributeTaskV1(dataset, handlerFunc, progressCallbackFunc, completedCallbackFunc, options) {
        // 1.获取 options
        const config = commonHttp.getOptions(null, commonFaasinfraHttpPath.createDistributedTask);
        // 2.构造url
        const urlPath = config._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
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
        const task_id = utils.getTriggerTaskID();
        if (task_id) {
            config.json[headers.triggerTaskId] = task_id;
        }
        const loopCtx = nodeCls.get(loopCtxKey);
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
        const config = commonHttp.getOptions(null, commonFaasinfraHttpPath.createDistributedTaskV2);
        // 2.构造url
        const urlPath = config._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
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
        const task_id = utils.getTriggerTaskID();
        if (task_id) {
            config.json[headers.triggerTaskId] = task_id;
        }
        const loopCtx = nodeCls.get(loopCtxKey);
        if (checkLoopCtx(loopCtx)) {
            config.json[loopMasksKey] = loopCtx.loopMasks;
            if ((handlerFunc !== '' && config.json[loopMasksKey].includes(handlerFunc)) ||
                (progressCallbackFunc !== '' && config.json[loopMasksKey].includes(progressCallbackFunc)) ||
                (completedCallbackFunc !== '' && config.json[loopMasksKey].includes(completedCallbackFunc))) {
                throw new exceptions.InvalidParamError('Task execution forms a loop.');
            }
        }
        return await faasinfra.doRequest(null, urlPath, config);
    }
    async createDistributeTaskV3(dataset, handlerFunc, progressCallbackFunc, completedCallbackFunc, options) {
        // 1.获取 options
        const config = commonHttp.getOptions(null, commonFaasinfraHttpPath.createDistributedTaskV3);
        // 2.构造url
        const urlPath = config._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
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
        const taskIDStr = utils.getTriggerTaskIDStr();
        if (taskIDStr) {
            config.json[headers.triggerTaskIdStr] = taskIDStr;
        }
        const loopCtx = nodeCls.get(loopCtxKey);
        if (checkLoopCtx(loopCtx)) {
            config.json[loopMasksKey] = loopCtx.loopMasks;
            if ((handlerFunc !== '' && config.json[loopMasksKey].includes(handlerFunc)) ||
                (progressCallbackFunc !== '' && config.json[loopMasksKey].includes(progressCallbackFunc)) ||
                (completedCallbackFunc !== '' && config.json[loopMasksKey].includes(completedCallbackFunc))) {
                throw new exceptions.InvalidParamError('Task execution forms a loop.');
            }
        }
        return await faasinfra.doRequest(null, urlPath, config);
    }
}
exports.FaaSInfraRequest = FaaSInfraRequest;
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
function getDebugExtraInfo() {
    const extra = {
        'FunctionFrameVersion': 'FunctionFrameV2',
    };
    if (utils.isDebug()) {
        extra.DebugInfo = utils.getDebugCode();
    }
    return extra;
}
