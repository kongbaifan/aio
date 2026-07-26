"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFunctionMetaWithCache = exports.getFunctionMeta = exports.getAppTokenHttp = exports.getAppToken = exports.mGetUserLocaleInfo = exports.doRequest = void 0;
const request_1 = require("./request");
const tool_1 = require("../kunlun/tool/impl/tool");
const utils = require("../utils/utils");
const exceptions = require("../utils/exceptions");
const constants_1 = require("../constants/constants");
const exceptions_1 = require("../utils/exceptions");
const constants = require("./constants");
const constants_2 = require("./constants");
const NodeCache = require('node-cache');
const localCache = new NodeCache();
/** @deprecated */
const openapiErrorCodes = {
    rateLimitError: 'k_op_ec_20003',
};
/** @deprecated */
const internalErrorCodes = {
    k_ec_000001: 'internal error',
    k_ec_000002: 'can not find tenant ID',
    k_ec_000003: 'can not find user ID',
    k_ec_000004: 'unknown error',
    k_op_ec_00001: 'unknown error',
    k_op_ec_20001: 'system busy',
    k_op_ec_20002: 'system error',
    k_op_ec_20003: 'rate limit error',
    k_ident_013000: 'tenant token expire',
    k_ident_013001: 'illegal token',
    k_op_ec_10205: 'missing tenant token',
};
async function doRequest(ctx, urlPath, options) {
    let resp = null, beginTime = 0;
    // open-api 侧透传下游所需函数信息
    addHeadersOfFuncMsg(options);
    // FaaS 链路信息透传
    addPersistFaaSValueToHeader(options);
    let retryConfig = {
        retryCount: 0,
        retryDelay: 0,
    };
    // 判断是否为需要重试的方法
    if (constants.retryMethods.includes(options._reqMethod)) {
        retryConfig.retryCount = utils.getRetryTimesFromTcc();
    }
    let count = 1;
    [resp, beginTime] = await tool_1.tool.retry(async () => {
        try {
            return await (0, request_1.doRequestWithConnRetry)(urlPath, options);
        }
        catch (err) {
            // doRequestWithConnRetry 针对此种错误已经打点，这里不需要重复打点
            if (retryConfig.retryCount > 0) {
                utils.printInfoLog(`doRequestWithConnRetry retry curTimes: ${count++} retryCount: ${retryConfig.retryCount} method: ${options._reqMethod} err: ${err}`);
            }
            throw new exceptions.CallOpenapiError(err);
        }
    }, retryConfig);
    let result = null;
    if (resp.status === 200) {
        if (resp.headers && resp.headers['content-type'].includes('application/json') && !urlPath.includes('/attachment/v1/download') && !urlPath.includes('/api/attachment/v1/files/')) {
            result = resp.data;
        }
        else {
            if (resp.headers['content-disposition']) {
                result = { code: '0', data: resp.data };
            }
            else {
                // 文件下载失败
                try {
                    result = JSON.parse(resp.data);
                }
                catch (e) {
                    throw new exceptions_1.UnmarshalError(e);
                }
            }
        }
    }
    else {
        utils.fail(options, beginTime);
        throw new exceptions.CallOpenapiError(resp);
    }
    if (!result) {
        utils.fail(options, beginTime);
        throw new exceptions.CallOpenapiError('result is empty');
    }
    if (result.code === '0') {
        utils.success(options, beginTime);
        return result.data;
    }
    if (internalErrorCodes.hasOwnProperty(result.code)) {
        utils.fail(options, beginTime);
    }
    else {
        utils.success(options, beginTime);
    }
    throw new exceptions.BaseError(result.code, result.msg);
}
exports.doRequest = doRequest;
function addHeadersOfFuncMsg(options) {
    if (!options.headers) {
        options.headers = {};
    }
    let fSdkFuncMsg = {};
    // 函数别名
    if (utils.isMicroservice()) {
        fSdkFuncMsg[constants_1.FuncMsgKey.funcApiName] = 'microservice';
    }
    else if (utils.isOpenSDKMode()) {
        fSdkFuncMsg[constants_1.FuncMsgKey.funcApiName] = 'openSDK';
    }
    else {
        fSdkFuncMsg[constants_1.FuncMsgKey.funcApiName] = utils.getInvokeFuncApiAlias();
    }
    options.headers[constants_1.headers.faasSdkFuncMsgKey] = JSON.stringify(fSdkFuncMsg);
}
function addPersistFaaSValueToHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    options.headers[constants_1.APaaSPersistKey.PersistFaaSKeySummarized] = JSON.stringify(utils.getAPaaSPersistFaaSMap());
}
async function mGetUserLocaleInfo(reqUserIDList) {
    // 1. 获取 options
    const options = (0, request_1.getOptions)(null, constants.openapiHttpPath.mGetUserSettings);
    let urlPath = options._reqPath;
    // 2. 请求
    options.json = {
        'userIDs': reqUserIDList,
    };
    return await doRequest(null, urlPath, options);
}
exports.mGetUserLocaleInfo = mGetUserLocaleInfo;
async function getAppToken() {
    return (0, request_1.getTokenWithCache)(doRequest, constants.appTokenType, constants.openapiHttpPath.getAppToken, {
        'clientId': utils.getClientId(),
        'clientSecret': utils.getClientSecret(),
    });
}
exports.getAppToken = getAppToken;
async function getAppTokenHttp(clientID, clientSecret) {
    clientID = clientID ? clientID : utils.getClientId();
    clientSecret = clientSecret ? clientSecret : utils.getClientSecret();
    const options = (0, request_1.getTokenOptions)(null, constants.openapiHttpPath.getAppToken);
    let urlPath = options._reqPath;
    options.json = {
        'clientId': clientID,
        clientSecret,
        'withTenantInfo': true,
    };
    return await doRequest(null, urlPath, options);
}
exports.getAppTokenHttp = getAppTokenHttp;
async function getFunctionMeta(functionAPIName) {
    // 1. 获取 options
    const options = (0, request_1.getOptions)(null, constants.openapiHttpPath.getFunctionDetail);
    let urlPath = options._reqPath.replace(constants_2.replaceKeys.namespace, utils.getNamespaceFromCtx());
    // 2. 请求
    options.json = {
        'apiName': functionAPIName,
    };
    const func = await doRequest(null, urlPath, options);
    if (!func || !func.detail) {
        return undefined;
    }
    return {
        apiName: func.detail.apiName,
        input: func.detail.input,
        output: func.detail.output,
    };
}
exports.getFunctionMeta = getFunctionMeta;
async function getFunctionMetaWithCache(functionAPIName) {
    // from cache
    let functionMetaConf = localCache.get(functionAPIName);
    if (functionMetaConf) {
        return functionMetaConf;
    }
    // from remote
    functionMetaConf = await getFunctionMeta(functionAPIName);
    // save cache
    if (functionMetaConf) {
        localCache.set(functionAPIName, functionMetaConf, 60);
    }
    return functionMetaConf;
}
exports.getFunctionMetaWithCache = getFunctionMetaWithCache;
