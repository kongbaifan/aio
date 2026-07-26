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
    async createAsyncTaskV1(idOrName, params) {
        // attention: 异步任务接口存在先后区别，接口版本号不一致需 check，v1->v2
        const options = commonHttp.getOptions(null, openapiHttpPath.createAsyncTaskInnerAPIV2);
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
            options.json.function_name = ''; // required
        }
        else {
            options.json.function_name = idOrName.APIId;
        }
        const res = await openapi.doRequest(null, urlPath, options);
        if (res && res.task_id) {
            return res.task_id;
        }
        throw new exceptions.InternalError('createAsyncTaskV1 result is empty');
    }
    async createAsyncTaskV2(name, params) {
        // attention: 异步任务接口存在先后区别，接口版本号不一致需 check，v2->v1
        const options = commonHttp.getOptions(null, openapiHttpPath.createAsyncTaskInnerAPIV1);
        const urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
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
        options.headers.User = utils.getUserIDFromCtx();
        options.json = {
            'apiAlias': name,
            'params': JSON.stringify(params),
            'context': JSON.stringify(await getTriggerCtx(params, name)),
            'triggerType': functionTriggerType.DefaultTrigger,
            'extra': (0, common_1.getDebugExtraInfo)(),
        };
        const res = await openapi.doRequest(null, urlPath, options);
        if (res && res.task_id) {
            return res.task_id;
        }
        throw new exceptions.InternalError('createAsyncTaskV2 result is empty');
    }
    async invokeFuncSync(idOrName, params) {
        return await invokeFuncSync(idOrName, params);
    }
}
exports.RequestHttp = RequestHttp;
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
async function getTriggerCtx(params, functinAPIName) {
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
    triggerCtx.permission = await permissionUtils.delParamsUnauthField(functinAPIName, 'input', params);
    return triggerCtx;
}
async function invokeFuncSync(idOrName, params) {
    let options = commonHttp.getOptions(null, openapiHttpPath.invokeFuncSyncInnerAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
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
    let res = await openapi.doRequest(null, urlPath, options);
    if (res && res.code === '0') {
        return res.data;
    }
    throw new exceptions.InternalError(`invokeFuncSync result.code(${res.code}) is invalid`);
}
