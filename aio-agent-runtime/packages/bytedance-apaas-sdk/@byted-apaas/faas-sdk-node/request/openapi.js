"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.RequestHttp = void 0;
const common = require("@byted-apaas/server-common-node");
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const common_1 = require("./common");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const commonHttp = common.http;
const openapi = common.http.openapi;
const openapiHttpPath = common.http.openapiHttpPath;
const replaceKeys = common.http.replaceKeys;
const exceptions = common.exceptions;
const utils = common.utils;
const functionTriggerType = common.constants.functionTriggerType;
class RequestHttp {
    async invokeFuncSync(idOrName, params) {
        const options = commonHttp.getOptions(null, openapiHttpPath.invokeFuncSyncInnerAPI);
        const urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
        options.headers.User = utils.getUserIDFromCtx();
        options.json = {
            'params': JSON.stringify(params),
            'context': JSON.stringify(await getTriggerCtx(params, idOrName.APIName)),
            'triggerType': functionTriggerType.DefaultTrigger,
        };
        //  相等时，表示是新版本函数的场景
        if (idOrName.isInvokeByAPIName) {
            options.json.apiAlias = idOrName.APIName;
            options.json.function_name = '';
        }
        else {
            options.json.function_name = idOrName.APIId;
            options.json.apiAlias = '';
        }
        const res = await openapi.doRequest(null, urlPath, options);
        if (!res) {
            throw new exceptions.InternalError(`InvokeFuncSync result is empty`);
        }
        if (res.code === '0') {
            if (res.permission) {
                await permissionUtils.appendUnauthFieldToParams(idOrName.APIName, "output", res.data, res.permission._unauthFields);
            }
            return res.data;
        }
        throw new exceptions.BaseError(res.code, res.msg);
    }
    async invokeFuncWithAuth(idOrName, params) {
        const options = commonHttp.getOptions(null, openapiHttpPath.invokeFuncWithAuthInnerAPI);
        let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
        urlPath = urlPath.replace(replaceKeys.apiName, idOrName.APIName);
        options.headers.User = utils.getUserIDFromCtx();
        options.json = {
            params,
            'context': await getTriggerCtx(params, idOrName.APIName),
        };
        if (!idOrName.isInvokeByAPIName) {
            options.json.apiID = idOrName.APIId;
        }
        const res = await openapi.doRequest(null, urlPath, options);
        if (!res || !res.result) {
            throw new exceptions.InternalError('result is empty');
        }
        let result;
        try {
            result = JSON.parse(res.result);
        }
        catch (e) {
            throw new exceptions.InternalError(`JSON parse failed for ${res.result}`);
        }
        if (!result || result.code !== '0') {
            throw new exceptions.InvalidParamError(`result is invalid for code: ${result ? result.code : ''} msg: ${result ? result.msg : ''}`);
        }
        if (result.permission) {
            await permissionUtils.appendUnauthFieldToParams(idOrName.APIName, "output", result.data, result.permission._unauthFields);
        }
        return result.data;
    }
}
exports.RequestHttp = RequestHttp;
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
async function getTriggerCtx(params, funcAPIName) {
    const triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[constants_1.headers.triggerTaskId] = taskID;
    }
    const temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[constants_1.headers.distributedHandleMask] = temp;
    }
    const reqCtx = nodeCls.get(constants_1.headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[constants_1.headers.loopMasks] = reqCtx.loopMasks;
    }
    triggerCtx.permission = await permissionUtils.delParamsUnauthField(funcAPIName, 'input', params);
    return triggerCtx;
}
