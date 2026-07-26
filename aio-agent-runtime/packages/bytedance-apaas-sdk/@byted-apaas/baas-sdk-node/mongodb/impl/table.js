"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Table = void 0;
const server_common_node_1 = require("@byted-apaas/server-common-node");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const faasinfra = require("../../http/faasinfra");
const constants_1 = require("./constants");
const query_1 = require("./query");
const proxy_1 = require("./proxy");
const faasinfra_1 = require("../../http/faasinfra");
const ODMObject_1 = require("./ODMObject");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const bson = require('bson'); //nolint:byted_s_ts_no_require_imports
class Table {
    constructor(tableName) {
        if (!tableName) {
            throw new server_common_node_1.exceptions.InvalidParamError('tableName is empty');
        }
        if (typeof (tableName) !== 'string') {
            throw new server_common_node_1.exceptions.InvalidParamError(`The type of tableName should be string, but ${typeof (tableName)}`);
        }
        this.tableName = tableName;
    }
    create(record) {
        if (Array.isArray(record)) {
            return record.map(v => this.createFromObject(v));
        }
        else if (server_common_node_1.utils.isObject(record)) {
            return this.createFromObject(record);
        }
        else {
            throw new exceptions_1.InvalidParamError(`The type of record should be object or array, but ${typeof (record)}`);
        }
    }
    async save(record) {
        if (Array.isArray(record)) {
            return await this.saveMany(record.map(v => this.createFromObject(v)));
        }
        else if (server_common_node_1.utils.isObject(record)) {
            let [ret] = await this.saveMany([this.createFromObject(record)]);
            return ret;
        }
        throw new exceptions_1.InvalidParamError(`The type of record should be object or array, but ${typeof (record)}`);
    }
    /**
     * 删除记录
     * @param record 对象或数组，且必须包含 _id 字段
     */
    async delete(record) {
        if (!record) {
            throw new exceptions_1.InvalidParamError('record cannot be empty');
        }
        let reqParam;
        if (Array.isArray(record)) {
            let ids = record.map(r => {
                if (!server_common_node_1.utils.isObject(r)) {
                    throw new exceptions_1.InvalidParamError(`The type of record's element should be object, but ${typeof (r)}`);
                }
                if (!r._id) {
                    throw new exceptions_1.InvalidParamError("record's _id field cannot be empty");
                }
                return r._id;
            });
            reqParam = {
                'tableName': this.tableName,
                'args': { 'op': constants_1.OperatorType.DELETE, 'query': { _id: { '$in': ids } }, 'one': false },
            };
        }
        else if (server_common_node_1.utils.isObject(record)) {
            if (!record._id) {
                throw new exceptions_1.InvalidParamError("record's _id field cannot be empty");
            }
            reqParam = {
                'tableName': this.tableName,
                'args': { 'op': constants_1.OperatorType.DELETE, 'query': { _id: record._id }, 'one': true },
            };
        }
        else {
            throw new exceptions_1.InvalidParamError(`The type of record should be array or object, but ${typeof (record)}`);
        }
        return await (0, faasinfra_1.requestMongodb)(reqParam);
    }
    where(value) {
        return new query_1.Query(this.tableName).where(value);
    }
    createFromObject(record) {
        if (!server_common_node_1.utils.isObject(record)) {
            throw new exceptions_1.InvalidParamError(`The type of record should be object, but ${typeof (record)}`);
        }
        if (record[proxy_1.p.tableName] === this.tableName) {
            return record;
        }
        if (!record[proxy_1.p.query]) {
            record._id = record._id || bson.ObjectId();
        }
        return (0, ODMObject_1.buildODMObject)(this.tableName, record);
    }
    splitRecordsAndInitCreatedUpdatedAt(records) {
        let instructions = [], createRecords = [], updateRecords = [];
        for (let record of records) {
            if (record[proxy_1.p.isQuery] == this.tableName) {
                if (!record._id) {
                    throw new exceptions_1.InvalidParamError('The record._id cannot be empty');
                }
                record.updatedAt = record.updatedAt !== undefined ? record.updatedAt : new Date();
                instructions.push({
                    'op': constants_1.OperatorType.UPDATE,
                    'query': { _id: record._id },
                    one: true,
                    update: { '$set': record },
                });
                updateRecords.push(record);
            }
            else {
                record.createdAt = record.createdAt !== undefined ? record.createdAt : new Date();
                record.updatedAt = record.updatedAt !== undefined ? record.updatedAt : new Date();
                createRecords.push(record);
                instructions.push({
                    'op': constants_1.OperatorType.INSERT,
                    docs: record,
                });
            }
        }
        return [instructions, createRecords, updateRecords];
    }
    async saveMany(records) {
        if (!records || !Array.isArray(records) || records.length === 0) {
            throw new exceptions_1.InvalidParamError(`The value of records should be nonempty array`);
        }
        let [instructions, createRecords, updateRecords] = this.splitRecordsAndInitCreatedUpdatedAt(records);
        /**
         * 1.更新数量为 0 时，create
         * 2.更新数量为 1 时
         *   2.1 创建数量为 0 时，update
         *   2.2 创建数量大于 0 时，bulk write
         * 3.更新数量大于 1 时，bulk write
         */
        let reqParam;
        if (updateRecords.length === 0) {
            // 1.create
            reqParam = { 'tableName': this.tableName, 'args': { 'op': constants_1.OperatorType.INSERT, 'docs': createRecords } };
        }
        else if (updateRecords.length === 1) {
            if (createRecords.length === 0) {
                // 2.1 update
                reqParam = {
                    'tableName': this.tableName,
                    'args': {
                        'op': constants_1.OperatorType.UPDATE,
                        'query': { _id: updateRecords[0]._id },
                        'update': { '$set': updateRecords[0] },
                    }
                };
            }
            else {
                // 2.2 bulk write
                reqParam = {
                    'tableName': this.tableName,
                    'args': { 'op': constants_1.OperatorType.BULK_WRITE, instructions },
                };
            }
        }
        else if (updateRecords.length > 1) {
            // 3.bulk write
            reqParam = {
                'tableName': this.tableName,
                'args': { 'op': constants_1.OperatorType.BULK_WRITE, instructions },
            };
        }
        await faasinfra.requestMongodb(reqParam);
        // 清除创建的状态
        records.forEach(record => Object.defineProperty(record, proxy_1.p.isQuery, {
            value: this.tableName,
            enumerable: false,
            writable: true,
        }));
        return records;
    }
}
exports.Table = Table;
