"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.appendUnauthFieldToParams = exports.delParamsUnauthField = exports.batchDelUnauthField = exports.delUnauthField = exports.getUnauthFieldByRecordID = exports.getUnauthFieldByObject = exports.appendUnauthFieldRecordList = exports.appendUnauthFieldRecord = void 0;
const nodeClsCtx = require("./nodeClsCtx");
const utils = require("./utils");
const utils_1 = require("./utils");
function getOpenapi() {
    return require('../http/openapi');
}
/**
 * 存储记录类型的无权限字段
 *
 * @param objectAPIName
 * @param record
 * @param unauthFields
 * @param modifyRecord
 */
function appendUnauthFieldRecord(objectAPIName, record, unauthFields, modifyRecord = false) {
    if (!record || !utils.isObject(record) || Number(record._id) <= 0
        || !unauthFields || !Array.isArray(unauthFields) || unauthFields.length === 0) {
        return;
    }
    const unauthFieldMap = nodeClsCtx.getUnauthFieldMap();
    // 有对象的 objectAPIName 才存储（目前 OQL 无 objectAPIName，本期不存储，影响的是不支持透传）
    if (objectAPIName && objectAPIName.length > 0) {
        if (!unauthFieldMap[objectAPIName]) {
            unauthFieldMap[objectAPIName] = {};
        }
        unauthFieldMap[objectAPIName][Number(record._id)] = unauthFields;
        nodeClsCtx.setUnauthFieldMap(unauthFieldMap);
    }
    if (modifyRecord) {
        record._unauthFields = unauthFields;
    }
}
exports.appendUnauthFieldRecord = appendUnauthFieldRecord;
/**
 * 存储记录列表类型的无权限字段
 *
 * @param objectAPIName 对象的 objectAPIName，为空时表示不支持透传，但无权限字段正常返回
 * @param records
 * @param unauthFieldsList
 * @param modifyRecord
 */
function appendUnauthFieldRecordList(objectAPIName, records, unauthFieldsList, modifyRecord = false) {
    if (!records || !Array.isArray(records) || records.length === 0
        || !unauthFieldsList || !Array.isArray(unauthFieldsList) || unauthFieldsList.length === 0) {
        return;
    }
    if (records.length !== unauthFieldsList.length) {
        return;
    }
    for (let i = 0; i < records.length; i++) {
        appendUnauthFieldRecord(objectAPIName, records[i], unauthFieldsList[i], modifyRecord);
    }
}
exports.appendUnauthFieldRecordList = appendUnauthFieldRecordList;
/**
 * 根据对象获取所有的无权限字段
 *
 * @param objectAPIName
 */
function getUnauthFieldByObject(objectAPIName) {
    const unauthFieldMap = nodeClsCtx.getUnauthFieldMap();
    if (unauthFieldMap && unauthFieldMap[objectAPIName]) {
        return unauthFieldMap[objectAPIName];
    }
    return {};
}
exports.getUnauthFieldByObject = getUnauthFieldByObject;
/**
 * 根据记录 ID 获取无权限字段
 *
 * @param objectAPIName
 * @param recordID
 */
function getUnauthFieldByRecordID(objectAPIName, recordID) {
    const unauthFieldObject = getUnauthFieldByObject(objectAPIName);
    if (unauthFieldObject && unauthFieldObject[recordID]) {
        return unauthFieldObject[recordID];
    }
    return [];
}
exports.getUnauthFieldByRecordID = getUnauthFieldByRecordID;
/**
 * 删除无权限字段
 *
 * @param record
 * @param objectAPIName
 */
function delUnauthField(record, objectAPIName) {
    if (!record || !(0, utils_1.isObject)(record)) {
        return record;
    }
    const newRecord = { ...record };
    delete newRecord._unauthFields;
    const unauthFields = getUnauthFieldByRecordID(objectAPIName, record._id);
    return { newRecord, unauthFields };
}
exports.delUnauthField = delUnauthField;
/**
 * 批量删除无权限字段
 *
 * @param records
 * @param objectAPIName
 */
function batchDelUnauthField(records, objectAPIName) {
    if (!Array.isArray(records)) {
        return records;
    }
    const newRecords = [];
    let unauthFieldsList = [], hasUnauthFields = false;
    for (const record of records) {
        const { newRecord, unauthFields } = delUnauthField(record, objectAPIName);
        newRecords.push(newRecord);
        unauthFieldsList.push(unauthFields);
        if (unauthFields && unauthFields.length > 0) {
            hasUnauthFields = true;
        }
    }
    if (!hasUnauthFields) {
        unauthFieldsList = undefined;
    }
    return { newRecords, unauthFieldsList };
}
exports.batchDelUnauthField = batchDelUnauthField;
/**
 * 删除参数中的无权限字段
 * 1.去除参数中 _unauthFields
 * 2.构造 permission: {_unauthFields: {}}
 *
 * @param funcAPIName 函数的 apiName
 * @param inputOrOutput 入参或出参，取值为 input 或 output
 * @param params 参数
 */
async function delParamsUnauthField(funcAPIName, inputOrOutput, params) {
    if (!params || !funcAPIName) {
        return undefined;
    }
    try {
        let metaConf = (0, utils_1.getFuncMetaConf)(funcAPIName);
        if (!metaConf) {
            metaConf = await getOpenapi().getFunctionMetaWithCache(funcAPIName);
        }
        if (!metaConf || !metaConf[inputOrOutput] || !Array.isArray(metaConf[inputOrOutput]) || metaConf[inputOrOutput].length === 0) {
            return undefined;
        }
        const permission = {
            _unauthFields: {}
        };
        for (let p of metaConf[inputOrOutput]) {
            let values = params[p.key];
            if (!values) {
                continue;
            }
            if (p.type === "Record" && (0, utils_1.isObject)(values)) {
                const { newRecord, unauthFields } = delUnauthField(values, p.objectApiName);
                params[p.key] = newRecord;
                if (unauthFields && unauthFields.length > 0) {
                    permission._unauthFields[p.key] = unauthFields;
                }
            }
            else if (p.type === "RecordList" && Array.isArray(values)) {
                const { newRecords, unauthFieldsList } = batchDelUnauthField(values, p.objectApiName);
                params[p.key] = newRecords;
                if (unauthFieldsList && unauthFieldsList.length > 0) {
                    permission._unauthFields[p.key] = unauthFieldsList;
                }
            }
        }
        return permission;
    }
    catch (err) {
        console.log('result err: ', err);
        return undefined;
    }
}
exports.delParamsUnauthField = delParamsUnauthField;
/**
 * 向参数中追加无权限字段
 * 1.无权限字段信息存储到上下文中
 * 2.无权限字段信息写入到 params 的参数中
 *
 * @param funcAPIName 函数的 apiName
 * @param inputOrOutput 入参或出参，值为 input | output
 * @param params 参数
 * @param unauthFieldsMap 无权限字段
 */
async function appendUnauthFieldToParams(funcAPIName, inputOrOutput, params, unauthFieldsMap) {
    if (!params || !funcAPIName) {
        return;
    }
    try {
        let metaConf = (0, utils_1.getFuncMetaConf)(funcAPIName);
        if (!metaConf) {
            metaConf = await getOpenapi().getFunctionMetaWithCache(funcAPIName);
        }
        if (!metaConf || !metaConf[inputOrOutput] || !Array.isArray(metaConf[inputOrOutput]) || metaConf[inputOrOutput].length === 0) {
            return;
        }
        for (let p of metaConf[inputOrOutput]) {
            const values = params[p.key];
            const unauthFields = unauthFieldsMap[p.key];
            if (!values || !unauthFields) {
                continue;
            }
            if (p.type === "Record" && (0, utils_1.isObject)(values)) {
                appendUnauthFieldRecord(p.objectApiName, values, unauthFields, true);
            }
            else if (p.type === "RecordList" && Array.isArray(values)) {
                appendUnauthFieldRecordList(p.objectApiName, values, unauthFields, true);
            }
        }
    }
    catch (err) {
        console.log('result err: ', err);
        return;
    }
}
exports.appendUnauthFieldToParams = appendUnauthFieldToParams;
