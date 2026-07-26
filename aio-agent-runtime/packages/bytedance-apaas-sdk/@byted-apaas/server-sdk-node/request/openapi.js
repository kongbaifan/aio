"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.getExecutionInfo = exports.revokeExecution = exports.executeFlow = exports.getExecutionUserTaskInfo = exports.RequestHttp = exports.updateWorkflowVariables = void 0;
const FormData = require("form-data");
const constants_1 = require("../constants/constants");
const common = require("@byted-apaas/server-common-node");
const constants_2 = require("./constants");
const constants_3 = require("@byted-apaas/server-common-node/constants/constants");
const common_1 = require("./common");
const utils_1 = require("@byted-apaas/server-common-node/utils/utils");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { URLSearchParams } = require('url'); //nolint:byted_s_ts_no_require_imports
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const fs = require('fs');
const path = require('path');
const commonHttp = common.http;
const openapi = common.http.openapi;
const openapiHttpPath = common.http.openapiHttpPath;
const replaceKeys = common.http.replaceKeys;
const exceptions = common.exceptions;
const fieldType = common.fieldType;
const utils = common.utils;
const checkUtils = common.checkUtils;
async function updateWorkflowVariables(ctx, instanceId, variables, variableTypes) {
    let options = commonHttp.getOptions(null, openapiHttpPath.workflowUpdateVariablesV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 2.请求
    options.json = {
        'operator': -1,
        'workflowInstanceID': instanceId,
        'variables': JSON.parse(variables),
        'variableTypes': JSON.parse(variableTypes),
    };
    await openapi.doRequest(null, urlPath, options);
}
exports.updateWorkflowVariables = updateWorkflowVariables;
async function createRecordBySync(objectApiName, record, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.createRecordBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 3.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'data': record,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    let data = await openapi.doRequest(null, urlPath, options);
    if (data && data.record_id) {
        return { _id: data.record_id };
    }
    if (data && data.recordID) {
        return { _id: data.recordID };
    }
    return data;
}
async function createRecordBySyncV3(objectApiName, record, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.createRecordBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 3.请求
    options.json = {
        'data_version': 'v3',
        record,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    const data = await openapi.doRequest(null, urlPath, options);
    if (data && data.record_id) {
        return { _id: data.record_id };
    }
    if (data && data.recordID) {
        return { _id: data.recordID };
    }
    return data;
}
async function updateRecordBySync(objectApiName, recordID, record, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.updateRecordBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 3.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'record_id': recordID,
        'data': record,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function updateRecordBySyncV3(objectApiName, recordID, record, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.updateRecordBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    urlPath = urlPath.replace(replaceKeys.recordID, recordID);
    // 3.请求
    options.json = {
        'record': record,
        "data_version": 'v3',
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function deleteRecordBySync(objectApiName, recordID, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.deleteRecordBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 3.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'record_id': recordID,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function deleteRecordBySyncV3(objectApiName, recordID, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.deleteRecordBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    urlPath = urlPath.replace(replaceKeys.recordID, recordID);
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function createRecordsByAsync(objectApiName, records, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.createRecordsByAsyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'data': records,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function updateRecordsByAsync(objectApiName, recordMap, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.updateRecordsByAsyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'data': recordMap,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function deleteRecordsByAsync(objectApiName, recordIDs, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.deleteRecordsByAsyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'record_id_list': recordIDs,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function createRecordsBySync(objectApiName, records, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.mCreateRecordsBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'set_system_mod': 2,
        'data': records,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function createRecordsBySyncV3(objectApiName, records, authType) {
    // 1.获取 options
    const options = commonHttp.getOptions(null, openapiHttpPath.createRecordsBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        records,
        'data_version': 'v3',
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    return openapi.doRequest(null, urlPath, options);
}
async function updateRecordsBySync(objectApiName, recordMap, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.mUpdateRecordsBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'set_system_mod': 2,
        'data': recordMap,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    const resp = await openapi.doRequest(null, urlPath, options);
    if (!resp || !resp.err_map) {
        return undefined;
    }
    const errMap = {};
    for (let recordID of Object.keys(resp.err_map)) {
        errMap[Number(recordID)] = resp.err_map[recordID];
    }
    return errMap;
}
async function updateRecordsBySyncV3(objectApiName, records, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.updateRecordsBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        records,
        'data_version': 'v3',
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    const resp = await openapi.doRequest(null, urlPath, options);
    if (!resp || !resp.err_map) {
        return undefined;
    }
    const errMap = {};
    for (let recordID of Object.keys(resp.err_map)) {
        errMap[String(recordID)] = resp.err_map[recordID];
    }
    return errMap;
}
async function deleteRecordsBySync(objectApiName, recordIDs, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.mDeleteRecordsBySyncV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'set_system_mod': 2,
        'record_id_list': recordIDs,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    const resp = await openapi.doRequest(null, urlPath, options);
    if (!resp || !resp.err_map) {
        return undefined;
    }
    const errMap = {};
    for (let recordID of Object.keys(resp.err_map)) {
        errMap[Number(recordID)] = resp.err_map[recordID];
    }
    return errMap;
}
async function deleteRecordsBySyncV3(objectApiName, recordIDs, authType) {
    // 1.获取 options
    const options = commonHttp.getOptions(null, openapiHttpPath.deleteRecordsBySyncV3);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = {
        'ids': recordIDs,
        'data_version': 'v3',
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const task_id = utils.getTriggerTaskID();
    if (task_id) {
        options.json.automation_task_id = task_id;
    }
    const resp = await openapi.doRequest(null, urlPath, options);
    if (!resp || !resp.err_map) {
        return undefined;
    }
    const errMap = {};
    for (let recordID of Object.keys(resp.err_map)) {
        errMap[Number(recordID)] = resp.err_map[recordID];
    }
    return errMap;
}
function handleResponse(objectAPIName, data, needCount) {
    // 返回数据的特殊处理
    if (needCount) {
        if (checkUtils.isObject(data) && data.total) {
            return data.total;
        }
        return 0;
    }
    else {
        if (checkUtils.isObject(data) && (data.data_list || data.items)) {
            let records = data.data_list;
            if (data.items) {
                records = data.items;
            }
            if (data.unauthPermissionInfo && data.unauthPermissionInfo.UnauthFieldSlice) {
                permissionUtils.appendUnauthFieldRecordList(objectAPIName, records, data.unauthPermissionInfo.UnauthFieldSlice, true);
            }
            if (data.unauth_permission_info && data.unauth_permission_info.unauth_field_slice) {
                permissionUtils.appendUnauthFieldRecordList(objectAPIName, records, data.unauth_permission_info.unauth_field_slice, true);
            }
            return records;
        }
        return [];
    }
}
async function getRecordsOrCountByCriterion(objectApiName, criterion, fuzzySearch, order, ignoreBackLookupField, fieldApiNames, offset, limit, needCount, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InternalError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, needCount ? openapiHttpPath.mGetCountByCriterionV2 : openapiHttpPath.mGetRecordByCriterionV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    if (needCount) {
        fieldApiNames = ['_id'];
    }
    if (typeof criterion === 'string') {
        criterion = JSON.parse(criterion);
    }
    // 3.请求
    options.json = {
        criterion,
        order,
        'ignore_back_lookup_field': ignoreBackLookupField,
        'field_api_names': fieldApiNames,
        offset,
        limit,
        'need_filter_user_permission': false,
        'need_total_count': needCount,
        fuzzySearch,
        // 只返回 slice 结果，使用 SliceResult
        // 只返回 map 结果，使用 MapResult
        // 分不清场景可以用 BothResult，性能较差，建议区分场景
        // 0 表示不返回 unauth field 任何数据; 1 表示两者都返回；2 表示仅返回 slice；3 表示仅返回 map
        'process_auth_field_type': 2,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const data = await openapi.doRequest(null, urlPath, options);
    return handleResponse(objectApiName, data, needCount);
}
async function getRecordsV3OrCountByCriterion(objectApiName, criterion, quickQuery, quickQueryFields, order, fieldApiNames, offset, limit, needCount, authType) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InternalError('objectApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.mGetRecordsV3OrCounByCriterion);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    if (needCount) {
        fieldApiNames = ['_id'];
    }
    if (typeof criterion === 'string') {
        criterion = JSON.parse(criterion);
    }
    // 3.请求
    options.json = {
        'page_size': limit,
        'offset': offset,
        'select': fieldApiNames,
        'order_by': order,
        'need_total_count': needCount,
        'filter': criterion,
        'quick_query': quickQuery,
        'quick_query_fields': quickQueryFields,
        // 只返回 slice 结果，使用 SliceResult
        // 只返回 map 结果，使用 MapResult
        // 分不清场景可以用 BothResult，性能较差，建议区分场景
        // 0 表示不返回 unauth field 任何数据; 1 表示两者都返回；2 表示仅返回 slice；3 表示仅返回 map
        'process_auth_field_type': 2,
        'data_version': 'v3',
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    const data = await openapi.doRequest(null, urlPath, options);
    return handleResponse(objectApiName, data, needCount);
}
/**
 * 上传文件
 *
 * @param datas：filePath；Stream
 * @param expire：过期时间，单位秒
 * @param fileName：文件名
 * @returns {Promise<*|string>}
 */
async function uploadFile(datas, expire = 0, fileName) {
    let formData = new FormData();
    if (fileName) {
        formData.append('file', datas, fileName);
    }
    else {
        formData.append('file', datas);
    }
    formData.append('expireSeconds', expire.toString());
    formData.append('ignoreUserId', 'true');
    let formHeaders = formData.getHeaders();
    // 1.获取config
    let options = commonHttp.getOptions(null, openapiHttpPath.uploadAttachment);
    let urlPath = options._reqPath;
    options.responseType = 'buffer';
    for (let key of Object.keys(formHeaders)) {
        options.headers[key] = formHeaders[key];
    }
    options.body = formData;
    // 2.请求
    return await openapi.doRequest(null, urlPath, options);
}
async function downloadFileByID(id, filePath) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.downloadFile);
    let urlPath = options._reqPath.replace(replaceKeys.fileID, id);
    options.responseType = 'buffer';
    // 2.请求
    let data = await openapi.doRequest(null, urlPath, options);
    // 3.写入文件
    data = Buffer.from(data, 'binary');
    if (filePath) {
        checkUtils.checkFile(filePath);
        utils.mkdirs(path.dirname(filePath));
        fs.writeFileSync(filePath, data);
        return undefined;
    }
    return data;
}
async function downloadFileByToken(fileToken, filePath) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.downloadAttachment);
    let urlPath = options._reqPath + `?token=${fileToken}`;
    options.responseType = 'buffer';
    // 2.请求
    let data = await openapi.doRequest(null, urlPath, options);
    // 3.写入文件
    data = Buffer.from(data, 'binary');
    if (filePath) {
        checkUtils.checkFile(filePath);
        utils.mkdirs(path.dirname(filePath));
        fs.writeFileSync(filePath, data);
        return undefined;
    }
    return data;
}
async function mGetFileToken(ids) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.getBatchAttachmentToken);
    let urlPath = options._reqPath;
    // 2.请求
    options.json = {
        attachmentIds: ids
    };
    let res = await openapi.doRequest(null, urlPath, options);
    if (!res || !res.tokens) {
        throw new exceptions.InternalError(`mGetFileToken result is empty`);
    }
    return res.tokens;
}
async function createMessage(msg) {
    // 1.解析参数 icon/receiverIds/percent
    if (!msg.icon) {
        throw new exceptions.InvalidParamError(`parameter icon is required!`);
    }
    if (typeof (msg.icon) != 'string') {
        throw new exceptions.InvalidParamError(`Invalid format of parameter icon, icon should be string.`);
    }
    let params = {};
    const modelKeySearchData = { 'icon_type': msg.icon };
    const receiverIds = msg.target_users || [];
    if (!(receiverIds instanceof Array)) {
        throw new exceptions.InvalidParamError(`Invalid format of parameter target_users, target_users should be array.`);
    }
    if (receiverIds.length === 0) {
        throw new exceptions.InvalidParamError(`parameter target_users is required!`);
    }
    const percent = msg.percent;
    if (percent !== undefined && percent !== null) {
        if (typeof (percent) !== 'number') {
            throw new exceptions.InvalidParamError('Invalid format of parameter percent, percent should be number.');
        }
        if (percent < 0 || percent > 100) {
            throw new exceptions.InvalidParamError('Invalid value of parameter percent, the value should be in range [0, 100].');
        }
        else {
            modelKeySearchData.percent = JSON.stringify(percent);
        }
    }
    // kunlun类型
    if (checkUtils.isObject(msg)) {
        for (let key of Object.keys(msg)) {
            if (fieldType.isKFieldType(msg[key])) {
                // instanceof 改动6
                // if (msg[key] instanceof fieldType.Multilingual) {
                if (fieldType.isKFieldTypeMultilingual((msg[key]))) {
                    let value = JSON.stringify(msg[key].toJSON());
                    params[key] = JSON.stringify({ value });
                }
                else {
                    params[key] = JSON.stringify(msg[key].toJSON());
                }
            }
            else {
                params[key] = JSON.stringify(msg[key]);
            }
        }
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.createMessage);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 3.请求
    options.json = {
        'NotifyModelKey': constants_1.notifyModel.key,
        'ReceiverIDs': receiverIds,
        'ParamsRawData': params,
        'Percent': percent,
        'ModelKeySearchData': modelKeySearchData,
    };
    let res = await openapi.doRequest(null, urlPath, options);
    return Number(res.taskID);
}
async function updateMessage(msgId, msg) {
    // 1.解析参数 msgId/icon/percent
    if (!msgId) {
        throw new exceptions.InvalidParamError(`parameter msgId is required!`);
    }
    if (typeof (msgId) != 'number') {
        throw new exceptions.InvalidParamError(`Invalid format of parameter msgId, msgId should be number.`);
    }
    if (!msg.icon) {
        throw new exceptions.InvalidParamError(`parameter icon is required!`);
    }
    if (typeof (msg.icon) != 'string') {
        throw new exceptions.InvalidParamError(`Invalid format of parameter icon, icon should be string.`);
    }
    let params = {};
    const modelKeySearchData = { 'icon_type': msg.icon };
    const percent = msg.percent;
    if (percent !== undefined && percent !== null) {
        if (typeof (percent) !== 'number') {
            throw new exceptions.InvalidParamError('Invalid format of parameter percent, percent should be number.');
        }
        if (percent < 0 || percent > 100) {
            throw new exceptions.InvalidParamError('Invalid value of parameter percent in message ${msgId}, the value should be in range [0, 100].');
        }
        else {
            modelKeySearchData.percent = JSON.stringify(percent);
        }
    }
    // kunlun类型
    if (checkUtils.isObject(msg)) {
        for (let key of Object.keys(msg)) {
            if (fieldType.isKFieldType(msg[key])) {
                // instanceof 改动7
                // if (msg[key] instanceof fieldType.Multilingual) {
                if (fieldType.isKFieldTypeMultilingual(msg[key])) {
                    let value = JSON.stringify(msg[key].toJSON());
                    params[key] = JSON.stringify({ value });
                }
                else {
                    params[key] = JSON.stringify(msg[key].toJSON());
                }
            }
            else {
                params[key] = JSON.stringify(msg[key]);
            }
        }
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.updateMessage);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 3.请求
    options.json = {
        'TaskID': msgId,
        'Percent': percent,
        'NotifyModelKey': constants_1.notifyModel.key,
        'ParamsRawData': params,
        'IsBackground': true,
        'ModelKeySearchData': modelKeySearchData,
    };
    return await openapi.doRequest(null, urlPath, options);
}
async function getFields(objectApiName) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InvalidParamError('objectApiName is empty');
    }
    // 2.获取config
    let options = commonHttp.getOptions(null, openapiHttpPath.getFieldsV5);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    let obj = await openapi.doRequest(null, urlPath, options);
    if (!obj || !obj.fields) {
        return [];
    }
    return obj.fields;
}
async function getField(objectApiName, fieldApiName) {
    // 1.check
    if (!objectApiName) {
        throw new exceptions.InternalError('objectApiName is empty');
    }
    if (!fieldApiName) {
        throw new exceptions.InternalError('fieldApiName is empty');
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.getFieldV5);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    urlPath = urlPath.replace(replaceKeys.fieldApiName, fieldApiName);
    // 3.请求
    return await openapi.doRequest(null, urlPath, options);
}
async function terminateWorkflowInstance(workflowInstanceId, operator, reason) {
    // 1.check
    if (typeof (workflowInstanceId) !== 'number') {
        throw new exceptions.InvalidParamError(`The type of workflowInstanceId should be number, but ${typeof (workflowInstanceId)}.`);
    }
    // 2.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.terminateWorkflowInstance);
    let urlPath = options._reqPath;
    // 3.请求
    options.json = {
        'workflowInstanceID': workflowInstanceId,
        operator,
        reason,
    };
    await openapi.doRequest(null, urlPath, options);
}
async function modifyRecordsWithTransaction(placeholders, operations, authType, version) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.modifyRecordsWithTransaction);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 2.请求
    options.json = {
        placeholders,
        operations,
        'operatorId': utils.getUserIDFromCtx(),
        'setSystemField': 1,
    };
    if (version === 'v3') {
        options.json['dataVersion'] = version;
    }
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    let taskId = utils.getTriggerTaskID();
    if (taskId) {
        options.json.taskId = taskId;
    }
    let result = await openapi.doRequest(null, urlPath, options);
    let retPlaceholders = new Map();
    if (result && result.placeholders) {
        for (let key of Object.keys(result.placeholders)) {
            retPlaceholders.set(key, result.placeholders[key]);
        }
    }
    return retPlaceholders;
}
async function getGlobalConfigByKey(key) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.getAllGlobalConfigs);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 2.请求
    let pageSize = 100, offset = 0;
    for (let i = 0;; i++) {
        options.json = {
            'biz_type': 'GlobalVariables',
            'used_by': 'UsedBySystem',
            'filter': {
                'offset': pageSize * i,
                'limit': pageSize,
            },
        };
        let data = await openapi.doRequest(null, urlPath, options);
        for (let config of data.configs) {
            if (config.key === key) {
                return config.value;
            }
        }
        if (data.configs.length < pageSize) {
            break;
        }
    }
    throw new exceptions.InvalidParamError(`undefined global variable (${key})`);
}
async function oql(oql, args, namedArgs, authType) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.oql);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    // 2.请求
    options.json = {
        'query': oql,
        args,
        namedArgs,
        'compat': true,
        'unauthFields': true,
    };
    authType = (0, utils_1.formatAuthType)(authType);
    options.headers.User = String(utils.getUserIDFromCtx());
    if (authType) {
        if (authType === constants_3.AuthTypeUser || authType === constants_3.AuthTypeMixUserSystem) {
            // select 鉴权，where、groupBy、orderBy 不鉴权
            authType = constants_3.AuthTypeMixUserSystem;
        }
        options.headers[constants_3.AuthTypeHttpHeader] = authType;
    }
    try {
        let result = await openapi.doRequest(null, urlPath, options);
        if (result && result.rows) {
            permissionUtils.appendUnauthFieldRecordList("", result.rows, result.unauth_field_slice, true);
            return result.rows;
        }
    }
    catch (e) {
        if (e.message.includes("TimeoutError")) {
            throw new exceptions.CallOpenapiError(`OQL timeout, please check the query statement and the execution time of the query statement.`);
        }
        throw e;
    }
    return [];
}
async function openSDKCreateRecordBySync(objectApiName, record) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKCreateRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = record;
    return await openapi.doRequest(null, urlPath, options);
}
async function openSDKUpdateRecordBySync(objectApiName, recordID, record) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKUpdateRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    urlPath = urlPath.replace(replaceKeys.recordID, recordID.toString());
    // 2.请求
    options.json = record;
    return await openapi.doRequest(null, urlPath, options);
}
;
async function openSDKDeleteRecordBySync(objectApiName, recordID) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKDeleteRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    urlPath = urlPath.replace(replaceKeys.recordID, recordID.toString());
    // 2.请求
    return await openapi.doRequest(null, urlPath, options);
}
;
async function openSDKCreateRecordsBySync(objectApiName, records) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKBatchCreateRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = { records: records };
    return await openapi.doRequest(null, urlPath, options);
}
;
async function openSDKUpdateRecordsBySync(objectApiName, records) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKBatchUpdateRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = { records: records };
    return await openapi.doRequest(null, urlPath, options);
}
;
async function openSDKDeleteRecordsBySync(objectApiName, recordIDs) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKBatchDeleteRecord);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    // 2.请求
    options.json = { _ids: recordIDs };
    return await openapi.doRequest(null, urlPath, options);
}
;
async function openSDKGetRecords(objectApiName, param) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKGetRecords);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.objectApiName, objectApiName);
    if (param.limit <= 0 || param.limit > 10000) {
        param.limit = 10000;
    }
    // 2.请求
    options.json = param;
    const data = await openapi.doRequest(null, urlPath, options);
    if (param.count) {
        return data.total;
    }
    else {
        return data.records;
    }
}
async function openSDKUploadFile(fileName, data) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKUploadFile);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    let formData = new FormData();
    formData.append('file', data);
    formData.append('ignoreUserId', 'true');
    let formHeaders = formData.getHeaders();
    options.responseType = 'buffer';
    for (let key of Object.keys(formHeaders)) {
        options.headers[key] = formHeaders[key];
    }
    options.body = formData;
    // 2.请求
    return await openapi.doRequest(null, urlPath, options);
}
async function openSDKUploadAvatar(fileName, data) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKUploadAvatar);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    let formData = new FormData();
    formData.append('file', data);
    formData.append('ignoreUserId', 'true');
    let formHeaders = formData.getHeaders();
    options.responseType = 'buffer';
    for (let key of Object.keys(formHeaders)) {
        options.headers[key] = formHeaders[key];
    }
    options.body = formData;
    // 2.请求
    return await openapi.doRequest(null, urlPath, options);
}
async function openSDKDownloadAvatar(imageID) {
    // 1.获取 options
    let options = commonHttp.getOptions(null, openapiHttpPath.openSDKDownloadAvatar);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.fileID, imageID);
    options.responseType = 'buffer';
    // 2.请求
    let data = await openapi.doRequest(null, urlPath, options);
    // 3.写入文件
    data = Buffer.from(data, 'binary');
    return data;
}
class RequestHttp {
    constructor() {
        this.updateWorkflowVariables = updateWorkflowVariables;
        this.createRecordBySync = createRecordBySync;
        this.createRecordBySyncV3 = createRecordBySyncV3;
        this.updateRecordBySync = updateRecordBySync;
        this.updateRecordBySyncV3 = updateRecordBySyncV3;
        this.deleteRecordBySync = deleteRecordBySync;
        this.deleteRecordBySyncV3 = deleteRecordBySyncV3;
        this.createRecordsByAsync = createRecordsByAsync;
        this.updateRecordsByAsync = updateRecordsByAsync;
        this.deleteRecordsByAsync = deleteRecordsByAsync;
        this.createRecordsBySync = createRecordsBySync;
        this.createRecordsBySyncV3 = createRecordsBySyncV3;
        this.updateRecordsBySync = updateRecordsBySync;
        this.updateRecordsBySyncV3 = updateRecordsBySyncV3;
        this.deleteRecordsBySync = deleteRecordsBySync;
        this.deleteRecordsBySyncV3 = deleteRecordsBySyncV3;
        this.getRecordsOrCountByCriterion = getRecordsOrCountByCriterion;
        this.getRecordsV3OrCounByCriterion = getRecordsV3OrCountByCriterion;
        this.uploadFile = uploadFile;
        this.downloadFileByID = downloadFileByID;
        this.downloadFileByToken = downloadFileByToken;
        this.mGetFileToken = mGetFileToken;
        this.createMessage = createMessage;
        this.updateMessage = updateMessage;
        this.getFields = getFields;
        this.getField = getField;
        this.terminateWorkflowInstance = terminateWorkflowInstance;
        this.modifyRecordsWithTransaction = modifyRecordsWithTransaction;
        this.getGlobalConfigByKey = getGlobalConfigByKey;
        this.oql = oql;
        this.getIntegrationAppAccessToken = getIntegrationAppAccessToken;
        this.getIntegrationTenantAccessToken = getIntegrationTenantAccessToken;
        this.getDefaultIntegrationAppAccessToken = getDefaultIntegrationAppAccessToken;
        this.getDefaultIntegrationTenantAccessToken = getDefaultIntegrationTenantAccessToken;
        // TODO: open sdk api test
        this.openSDKCreateRecordBySync = openSDKCreateRecordBySync;
        this.openSDKUpdateRecordBySync = openSDKUpdateRecordBySync;
        this.openSDKDeleteRecordBySync = openSDKDeleteRecordBySync;
        this.openSDKCreateRecordsBySync = openSDKCreateRecordsBySync;
        this.openSDKUpdateRecordsBySync = openSDKUpdateRecordsBySync;
        this.openSDKDeleteRecordsBySync = openSDKDeleteRecordsBySync;
        this.openSDKGetRecords = openSDKGetRecords;
        this.openSDKUploadFile = openSDKUploadFile;
        this.openSDKUploadAvatar = openSDKUploadAvatar;
        this.openSDKDownloadAvatar = openSDKDownloadAvatar;
    }
    updateWorkflowVariables(ctx, instanceId, variables, variableTypes) {
    }
    createRecordBySync(objectApiName, record, authType) {
    }
    createRecordBySyncV3(objectApiName, record, authType) {
    }
    updateRecordBySync(objectApiName, recordID, record, authType) {
    }
    updateRecordBySyncV3(objectApiName, recordID, record, authType) {
    }
    deleteRecordBySync(objectApiName, recordID, authType) {
    }
    deleteRecordBySyncV3(objectApiName, recordID, authType) {
    }
    createRecordsByAsync(objectApiName, records, authType) {
    }
    updateRecordsByAsync(objectApiName, recordMap, authType) {
    }
    deleteRecordsByAsync(objectApiName, recordIDs, authType) {
    }
    createRecordsBySync(objectApiName, records, authType) {
    }
    createRecordsBySyncV3(objectApiName, records, authType) {
    }
    updateRecordsBySync(objectApiName, recordMap, authType) {
        return new Promise(undefined);
    }
    updateRecordsBySyncV3(objectApiName, records, authType) {
        return new Promise(undefined);
    }
    deleteRecordsBySync(objectApiName, recordIDs, authType) {
        return new Promise(undefined);
    }
    deleteRecordsBySyncV3(objectApiName, recordIDs, authType) {
        return new Promise(undefined);
    }
    getRecordsOrCountByCriterion(objectApiName, criterion, order, fuzzySearch, ignoreBackLookupField, fieldApiNames, offset, limit, needCount, authType) {
    }
    getRecordsV3OrCounByCriterion(objectApiName, criterion, quickQuery, quickQueryFields, order, fieldApiNames, offset, limit, needCount, authType) {
    }
    uploadFile(data, expire, fileName) {
        return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    downloadFileByID(fileID, filePath) {
        return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    downloadFileByToken(fileToken, filePath) {
        return null;
    }
    createMessage(msg) {
        return null;
    }
    updateMessage(msgId, msg) {
        return null;
    }
    getFields(objectApiName) {
    }
    getField(objectApiName, fieldApiName) {
    }
    terminateWorkflowInstance(workflowInstanceId, operator, reason) {
    }
    async modifyRecordsWithTransaction(placeholders, operations, authType, version) {
        return new Promise(undefined);
    }
    getGlobalConfigByKey(key) {
        return null;
    }
    oql(oql, args, namedArgs, authType) {
    }
    async invokeFuncSync(idOrName, params) {
        return await invokeFuncSync(idOrName, params);
    }
    async invokeFuncWithAuth(idOrName, params) {
        return await invokeFuncWithAuth(idOrName, params);
    }
    async createAsyncTaskV1(idOrName, params) {
        return await createAsyncTaskV1(idOrName, params);
    }
    async createAsyncTaskV2(name, params) {
        return await createAsyncTaskV2(name, params);
    }
    async getExecutionUserTaskInfo(executionId) {
        return await getExecutionUserTaskInfo(executionId);
    }
    async executeFlow(apiName, options, async) {
        return await executeFlow(apiName, options, async);
    }
    async revokeExecution(executionId, revokeOptions) {
        return await revokeExecution(executionId, revokeOptions);
    }
    async getExecutionInfo(executionId) {
        return await getExecutionInfo(executionId);
    }
    async getTenantInfo(appCtx) {
        return await appCtx.credential.getTenantInfo();
    }
    mGetFileToken(ids) {
        return null;
    }
    async getIntegrationAppAccessToken(apiName) {
        return null;
    }
    async getIntegrationTenantAccessToken(apiName) {
        return null;
    }
    async getDefaultIntegrationAppAccessToken() {
        return null;
    }
    async getDefaultIntegrationTenantAccessToken() {
        return null;
    }
    // open sdk empty implement
    openSDKCreateRecordBySync(objectApiName, record) {
    }
    ;
    openSDKUpdateRecordBySync(objectApiName, recordID, record) {
    }
    ;
    openSDKDeleteRecordBySync(objectApiName, recordID) {
    }
    ;
    openSDKCreateRecordsBySync(objectApiName, records) {
    }
    ;
    openSDKUpdateRecordsBySync(objectApiName, recordMap) {
    }
    ;
    openSDKDeleteRecordsBySync(objectApiName, recordIDs) {
    }
    ;
    openSDKGetRecords(objectApiName, param) {
        return null;
    }
    ;
    openSDKUploadFile(fileName, data) {
    }
    ;
    openSDKUploadAvatar(fileName, data) {
    }
    ;
    openSDKDownloadAvatar(imageID) {
        return null;
    }
    ;
    async getApprovalInstanceList(params) {
        let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.getApprovalInstanceList);
        let urlPath = options._reqPath;
        // 设置参数
        const searchParams = {};
        if (params && params.startTime && params.startTime > 0) {
            searchParams.start_time = params.startTime;
        }
        if (params && params.endTime && params.endTime > 0) {
            searchParams.end_time = params.endTime;
        }
        if (params && params.pageSize && params.pageSize > 0) {
            searchParams.page_size = params.pageSize;
        }
        if (params && params.pageToken) {
            searchParams.page_token = params.pageToken;
        }
        options.searchParams = searchParams;
        // 发起请求
        let resp = await openapi.doRequest(null, urlPath, options);
        // 应答
        return {
            approvalInstanceIds: resp.approval_instance_ids,
            pageToken: resp.page_token,
            count: resp.count,
            hasMore: resp.has_more,
        };
    }
    async getApprovalInstance(params) {
        let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.getApprovalInstance);
        let urlPath = options._reqPath.replace(replaceKeys.id, String(params.approvalInstanceId));
        // 设置参数
        const searchParams = new URLSearchParams();
        if (params && params.includeContent) {
            searchParams.append('includes', 'ApprovalComment_Content');
        }
        if (params && params.includeFormData) {
            searchParams.append('includes', 'ApprovalTask_FormData');
        }
        urlPath = urlPath + '?' + searchParams.toString();
        // 发起请求
        let resp = await openapi.doRequest(null, urlPath, options);
        if (!resp || !resp.approval_instance) {
            return undefined;
        }
        // 处理应答
        const approvalInstance = resp.approval_instance;
        const result = {
            id: approvalInstance.id,
            label: approvalInstance.label,
            initiator: approvalInstance.initiator,
            instanceStartTime: approvalInstance.instance_start_time,
            status: approvalInstance.status,
            tasks: [],
            comments: [],
        };
        if (approvalInstance.tasks && Array.isArray(approvalInstance.tasks)) {
            for (let task of approvalInstance.tasks) {
                result.tasks.push({
                    id: task.id,
                    taskType: task.task_type,
                    taskStatus: task.task_status,
                    taskStartTime: task.task_start_time,
                    taskEndTime: task.task_end_time,
                    formData: task.form_data,
                    approvalLogic: task.approval_logic,
                    approvers: task.approvers,
                    assigners: task.assigners,
                    taskURL: task.task_url,
                });
            }
        }
        if (approvalInstance.comments && Array.isArray(approvalInstance.comments)) {
            for (let comment of approvalInstance.comments) {
                result.comments.push({
                    id: comment.id,
                    commenter: comment.commenter,
                    content: comment.content,
                    createAt: comment.create_at,
                    updateAt: comment.update_at,
                });
            }
        }
        return result;
    }
}
exports.RequestHttp = RequestHttp;
async function invokeFuncWithAuth(idOrName, params) {
    let options = commonHttp.getOptions(null, openapiHttpPath.invokeFuncWithAuthInnerAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    urlPath = urlPath.replace(replaceKeys.apiName, idOrName.APIName);
    options.headers.User = utils.getUserIDFromCtx();
    options.json = {
        params,
        'context': getTriggerCtx(),
    };
    if (!idOrName.isInvokeByAPIName) {
        options.json.apiID = idOrName.APIId;
    }
    let res = await openapi.doRequest(null, urlPath, options);
    if (!res || !res.result) {
        throw new exceptions.InternalError(`result is empty`);
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
    return result.data;
}
async function invokeFuncSync(idOrName, params) {
    let options = commonHttp.getOptions(null, openapiHttpPath.invokeFuncSyncInnerAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    options.headers.User = utils.getUserIDFromCtx();
    options.json = {
        'params': JSON.stringify(params),
        'context': JSON.stringify(getTriggerCtx()),
        'triggerType': utils.getTriggerType(),
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
    if (!res) {
        throw new exceptions.InternalError(`InvokeFuncSync result is empty`);
    }
    if (res && res.code === '0') {
        return res.data;
    }
    throw new exceptions.BaseError(res.code, res.msg);
}
async function createAsyncTaskV1(idOrName, params) {
    // attention: 异步任务接口存在先后区别，接口版本号不一致需 check，v1->v2
    let options = commonHttp.getOptions(null, openapiHttpPath.createAsyncTaskInnerAPIV2);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    options.headers.User = utils.getUserIDFromCtx();
    options.json = {
        'params': JSON.stringify(params),
        'context': JSON.stringify(getTriggerCtx()),
        'triggerType': utils.getTriggerType(),
    };
    //  相等时，表示是新版本函数的场景
    if (idOrName.isInvokeByAPIName) {
        options.json.apiAlias = idOrName.APIName;
        options.json.function_name = ''; // required
    }
    else {
        options.json.function_name = idOrName.APIId;
    }
    let res = await openapi.doRequest(null, urlPath, options);
    if (res && res.task_id) {
        return res.task_id;
    }
    throw new exceptions.InternalError(`createAsyncTaskV1 result is empty`);
}
async function createAsyncTaskV2(APIName, params) {
    // attention: 异步任务接口存在先后区别，接口版本号不一致需 check，v2->v1
    let options = commonHttp.getOptions(null, openapiHttpPath.createAsyncTaskInnerAPIV1);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    let triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[constants_3.headers.triggerTaskId] = taskID;
    }
    let temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[constants_3.headers.distributedHandleMask] = temp;
    }
    let reqCtx = nodeCls.get(constants_3.headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[constants_3.headers.loopMasks] = reqCtx.loopMasks;
    }
    options.headers.User = utils.getUserIDFromCtx();
    options.json = {
        'apiAlias': APIName,
        'params': JSON.stringify(params),
        'context': JSON.stringify(getTriggerCtx()),
        'triggerType': utils.getTriggerType(),
        'extra': (0, common_1.getDebugExtraInfo)(),
    };
    let res = await openapi.doRequest(null, urlPath, options);
    if (res && res.task_id) {
        return res.task_id;
    }
    throw new exceptions.InternalError(`createAsyncTaskV2 result is empty`);
}
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
function getTriggerCtx() {
    let triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[constants_3.headers.triggerTaskId] = taskID;
    }
    let temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[constants_3.headers.distributedHandleMask] = temp;
    }
    let reqCtx = nodeCls.get(constants_3.headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[constants_3.headers.loopMasks] = reqCtx.loopMasks;
    }
    return triggerCtx;
}
async function getExecutionUserTaskInfo(executionId) {
    if (!executionId) {
        throw new exceptions.InvalidParamError('executionId is empty');
    }
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.getExecutionUserTaskInfo);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.id, `${executionId}`);
    urlPath += `?operator=${utils.getUserIDFromCtx()}`;
    let res = await openapi.doRequest(null, urlPath, options);
    if (!res) {
        throw new exceptions.InternalError('getExecutionUserTaskInfo result is empty');
    }
    return res.taskList;
}
exports.getExecutionUserTaskInfo = getExecutionUserTaskInfo;
async function executeFlow(apiName, option, async) {
    if (!apiName) {
        throw new exceptions.InvalidParamError(`flow apiName is empty`);
    }
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.executeFlow);
    const urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.apiName, apiName);
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        'variables': (0, common_1.transMapToFlowVariable)(option.params),
        'loopMasks': utils.getLoopMasks(),
    };
    if (async !== undefined) {
        options.json['async'] = async;
    }
    let res = await openapi.doRequest(null, urlPath, options);
    return {
        executionId: res.executionId,
        status: res.status,
        data: (0, common_1.transFlowVariableToMap)(res.outParams),
        errCode: res.errCode ? res.errCode : undefined,
        errMsg: res.errMsg ? res.errMsg : undefined,
    };
}
exports.executeFlow = executeFlow;
async function revokeExecution(executionId, revokeOptions) {
    if (!executionId) {
        throw new exceptions.InvalidParamError(`executionId is empty`);
    }
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.revokeExecution);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.id, `${executionId}`);
    let reason = undefined;
    if (revokeOptions && revokeOptions.reason) {
        reason = {
            en_US: revokeOptions.reason.en_US,
            zh_CN: revokeOptions.reason.zh_CN
        };
    }
    options.json = {
        'operator': utils.getUserIDFromCtx(),
        reason,
    };
    return await openapi.doRequest(null, urlPath, options);
}
exports.revokeExecution = revokeExecution;
async function getExecutionInfo(executionId) {
    if (!executionId) {
        throw new exceptions.InvalidParamError(`executionId is empty`);
    }
    let options = commonHttp.getOptions(null, constants_2.openapiHttpPath.getExecutionInfo);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.id, `${executionId}`);
    urlPath += `?operator=${utils.getUserIDFromCtx()}`;
    let res = await openapi.doRequest(null, urlPath, options);
    if (!res || !res.executionInfo) {
        throw new exceptions.InternalError(`getExecutionInfo result is empty`);
    }
    return {
        status: res.executionInfo.status,
        data: (0, common_1.transFlowVariableToMap)(res.executionInfo.outParams),
        errCode: res.executionInfo.errCode ? res.executionInfo.errCode : undefined,
        errMsg: res.executionInfo.errMsg ? res.executionInfo.errMsg : undefined,
    };
}
exports.getExecutionInfo = getExecutionInfo;
async function getIntegrationAppAccessToken(apiName) {
    // 1.check
    if (!apiName) {
        throw new exceptions.InvalidParamError('apiName is empty');
    }
    let options = commonHttp.getOptions(null, openapiHttpPath.getIntegrationAppAccessTokenAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.apiName, `${apiName}`);
    let res = await openapi.doRequest(null, urlPath, options);
    return {
        expire: res.expire,
        appAccessToken: res.appAccessToken,
        appId: res.appId,
    };
}
async function getIntegrationTenantAccessToken(apiName) {
    // 1.check
    if (!apiName) {
        throw new exceptions.InvalidParamError('apiName is empty');
    }
    let options = commonHttp.getOptions(null, openapiHttpPath.getIntegrationTenantAccessTokenAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)()).replace(replaceKeys.apiName, `${apiName}`);
    let res = await openapi.doRequest(null, urlPath, options);
    return {
        expire: res.expire,
        tenantAccessToken: res.tenantAccessToken,
        appId: res.appId,
    };
}
async function getDefaultIntegrationAppAccessToken() {
    let options = commonHttp.getOptions(null, openapiHttpPath.getDefaultIntegrationAppAccessTokenAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    let res = await openapi.doRequest(null, urlPath, options);
    return {
        expire: res.expire,
        appAccessToken: res.appAccessToken,
        appId: res.appId,
    };
}
async function getDefaultIntegrationTenantAccessToken() {
    let options = commonHttp.getOptions(null, openapiHttpPath.getDefaultIntegrationTenantAccessTokenAPI);
    let urlPath = options._reqPath.replace(replaceKeys.namespace, await (0, common_1.getNamespaceForOpenAndFaaSSDK)());
    let res = await openapi.doRequest(null, urlPath, options);
    return {
        expire: res.expire,
        tenantAccessToken: res.tenantAccessToken,
        appId: res.appId,
    };
}
