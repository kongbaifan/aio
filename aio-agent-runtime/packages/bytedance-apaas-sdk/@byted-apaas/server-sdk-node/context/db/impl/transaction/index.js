"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Transaction = void 0;
const server_common_node_1 = require("@byted-apaas/server-common-node");
const Request = require("../../../../request/interface");
const operation_1 = require("./operation");
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
const assert = require('assert');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { v4: uuidv4 } = require('uuid'); //nolint:byted_s_ts_no_require_imports
class Transaction {
    constructor(objectApiName, appCtx) {
        this.appCtx = null;
        this.objectApiName = objectApiName;
        this.placeholders = {};
        this.operations = [];
        this.uuid2result = {};
        this.isCommit = false;
        this.batchResults = [];
        this.appCtx = appCtx;
    }
    // @ts-ignore
    currentObject() {
        if (!this.objectApiName) {
            throw new server_common_node_1.exceptions.InternalError(`objectApiName is empty`);
        }
        return this.object(this.objectApiName);
    }
    object(objectApiName) {
        if (!objectApiName) {
            throw new server_common_node_1.exceptions.InvalidParamError(`objectApiName is empty`);
        }
        return {
            // 注册创建的逻辑:
            // 事务中进行创建和不使用事务其实是一样的，特别之处在于返回的 ID 是由 SDK 生成的 uuid。
            // SDK 生成的 uuid 只是为了 Mock 住 ID 这个字段，在事务执行后并不会落库。
            registerCreate: (oldRecord) => {
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (!oldRecord) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record is empty');
                }
                if (server_common_node_1.checkUtils.isNotObject(oldRecord)) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record is not object');
                }
                let record = permissionUtils.delUnauthField(oldRecord).newRecord;
                let uuid = uuidv4();
                let result = { _id: uuid };
                record._id = uuid;
                this.placeholders[uuid] = 0;
                this.operations.push(new operation_1.CreateOperation(objectApiName, record));
                this.uuid2result[uuid] = result;
                return result;
            },
            // 注册更新的逻辑：
            // 由于事务中创建的 Record 的 ID 是 uuid，而已经创建的 Record 的 ID 是 number 类型，因此在传入 ID 的情况下类型为 string | number
            registerUpdate: (idOrRecord, record) => {
                let recordMap;
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (typeof idOrRecord === 'number' || typeof idOrRecord === 'string') {
                    recordMap = record;
                    recordMap._id = idOrRecord;
                }
                else {
                    recordMap = idOrRecord;
                }
                if (!recordMap) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record is empty');
                }
                recordMap = permissionUtils.delUnauthField(recordMap).newRecord;
                // const recordID: number = recordMap._id;
                let recordID;
                if (typeof recordMap._id === 'number') {
                    recordID = recordMap._id;
                }
                else if (typeof recordMap._id === 'string') {
                    recordID = parseInt(recordMap._id);
                }
                if (!recordID) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
                }
                this.operations.push(new operation_1.UpdateOperation(objectApiName, recordMap));
            },
            // 注册删除的逻辑:
            // 注册删除和注册更新一样，ID 有可能是事务中创建的 Record，也有可能是现存的 Record，因此 ID 的类型是 string | number
            registerDelete: (idOrRecord) => {
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (!idOrRecord) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record is empty');
                }
                let recordId = null;
                if (typeof idOrRecord === 'number' || typeof idOrRecord === 'string') {
                    recordId = idOrRecord;
                }
                else {
                    if (server_common_node_1.checkUtils.isObject(idOrRecord)) {
                        if (!idOrRecord._id) {
                            throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
                        }
                        recordId = idOrRecord._id;
                    }
                    else {
                        throw new server_common_node_1.exceptions.InvalidParamError('param type should be number | string | Object. ');
                    }
                }
                this.operations.push(new operation_1.DeleteOperation(objectApiName, { _id: recordId }));
            },
            // 注册批量创建
            registerBatchCreate: (recordMaps) => {
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (!recordMaps) {
                    throw new server_common_node_1.exceptions.InvalidParamError('recordMaps is empty');
                }
                if (!Array.isArray(recordMaps)) {
                    throw new server_common_node_1.exceptions.InvalidParamError('recordMaps is not Array');
                }
                if (recordMaps.length < 1) {
                    return [];
                }
                recordMaps = permissionUtils.batchDelUnauthField(recordMaps).newRecords;
                let result = [];
                let records = [];
                for (let oldRecord of recordMaps) {
                    let record = { ...oldRecord };
                    let uuid = uuidv4();
                    this.placeholders[uuid] = 0;
                    record._id = uuid;
                    result.push(uuid);
                    records.push(record);
                }
                this.operations.push(new operation_1.BatchCreateOperation(objectApiName, records));
                this.batchResults.push(result);
                return result;
            },
            registerBatchUpdate: (recordMaps) => {
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (!recordMaps) {
                    throw new server_common_node_1.exceptions.InvalidParamError('recordMaps is empty');
                }
                if (!Array.isArray(recordMaps)) {
                    throw new server_common_node_1.exceptions.InvalidParamError('recordMaps is not Array');
                }
                if (recordMaps.length < 1) {
                    return;
                }
                recordMaps = permissionUtils.batchDelUnauthField(recordMaps).newRecords;
                // 判断同字段同值更新标志
                let isSameValue = true;
                let ids = [];
                let flag = recordMaps[0];
                for (let record of recordMaps) {
                    if (server_common_node_1.checkUtils.isNotObject(record)) {
                        throw new server_common_node_1.exceptions.InvalidParamError('one record of recordMaps is not object');
                    }
                    if (!record._id) {
                        throw new server_common_node_1.exceptions.InvalidParamError(`one record of recordMaps has no _id ${JSON.stringify(record)}`);
                    }
                    ids.push(record._id);
                    if (!deepEqualExceptID(flag, record)) {
                        isSameValue = false;
                        break;
                    }
                }
                if (isSameValue) {
                    this.operations.push(new operation_1.BatchUpdateSameValueOperation(objectApiName, {
                        'ids': ids,
                        'value': flag,
                    }));
                }
                else {
                    for (const i in ids) {
                        recordMaps[i]._id = ids[i];
                    }
                    this.operations.push(new operation_1.BatchUpdateOperation(objectApiName, recordMaps));
                }
            },
            // 注册批量删除
            registerBatchDelete: (idOrRecords) => {
                if (this.isCommit) {
                    throw new server_common_node_1.exceptions.InvalidParamError('Committed transaction cannot register operations');
                }
                if (!idOrRecords) {
                    throw new server_common_node_1.exceptions.InvalidParamError('idOrRecords is empty');
                }
                if (!Array.isArray(idOrRecords)) {
                    throw new server_common_node_1.exceptions.InvalidParamError('idOrRecords is not Array');
                }
                if (idOrRecords.length < 1) {
                    return;
                }
                let ids = [];
                for (const idOrRecord of idOrRecords) {
                    switch (typeof idOrRecord) {
                        case 'string':
                        case 'number':
                            ids.push(idOrRecord);
                            break;
                        case 'object':
                            if (!idOrRecord._id) {
                                throw new server_common_node_1.exceptions.InvalidParamError('_id of one record is empty');
                            }
                            else {
                                ids.push(idOrRecord._id);
                            }
                            break;
                        default:
                            throw new server_common_node_1.exceptions.InvalidParamError('type of one param is not string | number | object');
                    }
                }
                this.operations.push(new operation_1.BatchDeleteOperation(objectApiName, { 'ids': ids }));
            },
        };
    }
    async commit() {
        if (this.isCommit) {
            throw new server_common_node_1.exceptions.InvalidParamError('The transaction cannot be committed repeatedly');
        }
        this.isCommit = true;
        if (!this.operations || this.operations.length === 0) {
            return;
        }
        let uuid2recordId = await Request.GetInstance().modifyRecordsWithTransaction(this.placeholders, this.operations, this.authType, this.appCtx.dataVersion);
        if (!uuid2recordId) {
            throw new server_common_node_1.exceptions.InternalError('uuid2recordId is empty');
        }
        // 单个注册结果映射
        for (let uuid of Object.keys(this.uuid2result)) {
            let preResult = this.uuid2result[uuid];
            let recordId = uuid2recordId.get(uuid);
            if (!recordId) {
                throw new server_common_node_1.exceptions.InternalError(`uuid (${uuid}) is not in uuid2recordId (${JSON.stringify(uuid2recordId)})`);
            }
            if (typeof (recordId) !== 'number') {
                throw new server_common_node_1.exceptions.InternalError(`the type (${typeof (recordId)}) of recordId (${recordId}) must be number`);
            }
            preResult._id = recordId;
        }
        if (!this.batchResults) {
            return;
        }
        // 批量注册结果映射
        for (let i = 0; i < this.batchResults.length; i++) {
            if (!this.batchResults[i]) {
                continue;
            }
            for (let j = 0; j < this.batchResults[i].length; j++) {
                if (!this.batchResults[i][j]) {
                    continue;
                }
                let recordId = uuid2recordId.get(this.batchResults[i][j]);
                if (!recordId) {
                    throw new server_common_node_1.exceptions.InternalError(`uuid (${this.batchResults[i][j]}) is not in uuid2recordId (${JSON.stringify(uuid2recordId)})`);
                }
                if (typeof (recordId) !== 'number') {
                    throw new server_common_node_1.exceptions.InternalError(`the type (${typeof (recordId)}) of recordId (${recordId}) must be number`);
                }
                this.batchResults[i][j] = recordId;
            }
        }
    }
    useSystemAuth() {
        this.authType = constants_1.AuthTypeSystem;
        return this;
    }
    useUserAuth() {
        this.authType = constants_1.AuthTypeUser;
        return this;
    }
}
exports.Transaction = Transaction;
function deepEqualExceptID(left, right) {
    const leftID = left._id, rightID = right._id;
    delete left._id;
    delete right._id;
    let result = deepEqual(left, right);
    left._id = leftID;
    right._id = rightID;
    return result;
}
function deepEqual(left, right) {
    try {
        assert.deepStrictEqual(left, right);
    }
    catch (e) {
        return false;
    }
    return true;
}
