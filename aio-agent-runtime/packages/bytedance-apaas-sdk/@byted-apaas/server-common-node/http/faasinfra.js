"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sendLog = exports.doRequest = exports.getServiceToken = void 0;
const request_1 = require("./request");
const exceptions = require("../utils/exceptions");
const request = require("./request");
const constants_1 = require("../constants/constants");
const utils = require("../utils/utils");
function getConstant() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./constants');
}
// eslint-disable-next-line @typescript-eslint/no-require-imports
const BSON = require('bson'); //nolint:byted_s_ts_no_require_imports
const bson = new BSON();
/** @deprecated */
const faasinfraErrorCodes = {
    rateLimitError: 'k_fs_ec_000004',
};
/** @deprecated */
const internalErrorCodes = {
    k_ec_000001: 'internal error',
    k_ident_013000: 'tenant token expire',
    k_ident_013001: 'illegal token',
    k_fs_ec_100001: 'missing tenant token',
    k_fs_ec_000004: 'rate limit error',
};
async function doRequest(ctx, urlPath, options) {
    // 统一加上 orgID
    options.headers[constants_1.headers.orgIDKey] = utils.getOrgId();
    // FaaS 链路信息透传
    options.headers[constants_1.APaaSPersistKey.PersistFaaSKeySummarized] = JSON.stringify(utils.getAPaaSPersistFaaSMap());
    let resp = null, beginTime = 0;
    try {
        [resp, beginTime] = await (0, request_1.doRequestWithConnRetry)(urlPath, options);
    }
    catch (err) {
        // doRequestWithConnRetry 针对此种错误已经打点，这里不需要重复打点
        throw new exceptions.CallFaasinfraError(err);
    }
    let result = null;
    if (resp.status === 200) {
        result = resp.data;
    }
    else {
        utils.fail(options, beginTime);
        throw new exceptions.CallFaasinfraError(resp);
    }
    if (!result) {
        utils.fail(options, beginTime);
        throw new exceptions.CallFaasinfraError('result is empty');
    }
    if (result.code === '0') {
        utils.success(options, beginTime);
        if (options._dataType === 'bson' && result.data !== null && result.data !== undefined) {
            return bson.deserialize(Buffer.from(result.data, 'base64'), { promoteBuffers: true }).data;
        }
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
async function sendLog(param) {
    // 1.获取config
    const options = request.getOptions(null, getConstant().faasinfraHttpPath.sendLog);
    let urlPath = options._reqPath;
    urlPath = urlPath.replace(getConstant().replaceKeys.namespace, utils.getNamespaceFromCtx());
    // 2.请求
    options.json = param;
    return await doRequest(null, urlPath, options);
}
exports.sendLog = sendLog;
async function getServiceToken() {
    return await (0, request_1.getTokenWithCache)(doRequest, getConstant().serviceTokenType, getConstant().faasinfraHttpPath.getServiceToken, {
        'serviceId': utils.getServiceId(),
        'serviceSecret': utils.getServiceSecret(),
    });
}
exports.getServiceToken = getServiceToken;
