"use strict";
// nolint: cognitive_complexity
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports._KApplicationObject = exports._KObject = void 0;
const queryBuilder_1 = require("./queryBuilder");
const order_1 = require("./order");
const Request = require("../../../request/interface");
const logic_1 = require("../../../kunlun/operator/impl/logic");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const propertiesStore_1 = require("./propertiesStore");
const common_1 = require("../../../application/impl/common");
const logicV2_1 = require("../../../kunlun/operator/impl/logicV2");
const operator_1 = require("../../../kunlun/operator/impl/operator");
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
const structs_1 = require("../../../common/structs");
const queryPropertiesStore = new propertiesStore_1.default();
// _KObject will be Mixin with [_KObjectSync, _KObjectAsync, _KObjectQuery]
class _KObject {
    constructor(objectApiName, appCtx) {
        this.apiName = '';
        if (!objectApiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        this.apiName = objectApiName;
        this.appCtx = appCtx;
    }
}
exports._KObject = _KObject;
class _KApplicationObject {
    constructor(objectApiName, appCtx) {
        this.apiName = '';
        this.appCtx = null;
        this.apiName = objectApiName;
        this.appCtx = appCtx;
    }
}
exports._KApplicationObject = _KApplicationObject;
class _KObjectSync {
    constructor() {
        this.apiName = '';
        this.appCtx = null;
    }
    // create, update, delete
    async create(recordMap) {
        if (!recordMap) {
            throw new server_common_node_1.exceptions.InvalidParamError('record is empty');
        }
        if (server_common_node_1.checkUtils.isNotObject(recordMap)) {
            throw new server_common_node_1.exceptions.InvalidParamError('record is not object');
        }
        recordMap = permissionUtils.delUnauthField(recordMap).newRecord;
        if (this.appCtx && this.appCtx.mode == 'openSDK') {
            // request from OpenSDK
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKCreateRecordBySync(this.apiName, recordMap);
            });
        }
        else if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return await Request.GetInstance().createRecordBySyncV3(this.apiName, recordMap, this.authType);
        }
        return await Request.GetInstance().createRecordBySync(this.apiName, recordMap, this.authType);
    }
    ;
    async delete(recordOrRecordID) {
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return this.deleteV3(recordOrRecordID);
        }
        // v1 v2 接口只支持 number 类型
        if (typeof recordOrRecordID === 'string') {
            throw new server_common_node_1.exceptions.InvalidParamError('_id must be number');
        }
        let recordID;
        // 用户直接传入 record id 来进行删除的情况
        if (typeof recordOrRecordID === 'number') {
            recordID = recordOrRecordID;
        }
        else {
            // 用户传入 object 结构来进行删除的情况
            let record = recordOrRecordID;
            if (server_common_node_1.checkUtils.isObject(record)) {
                // 如果用户没有传入包含 id 的 record，则报错
                if (!record._id) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
                }
                if (typeof record._id === 'number') {
                    recordID = record._id;
                }
                else if (typeof record._id === 'string') {
                    recordID = parseInt(record._id);
                }
            }
        }
        if (recordID > 0) {
            if (this.appCtx && this.appCtx.mode == 'openSDK') {
                // request from OpenSDK
                return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                    return await Request.GetInstance().openSDKDeleteRecordBySync(this.apiName, recordID);
                });
            }
            return await Request.GetInstance().deleteRecordBySync(this.apiName, recordID, this.authType);
        }
        throw new server_common_node_1.exceptions.InvalidParamError('record must be number or object');
    }
    ;
    async deleteV3(recordOrRecordID) {
        let recordIDStr;
        if (typeof recordOrRecordID === 'number') {
            recordIDStr = recordOrRecordID.toString();
        }
        else if (typeof recordOrRecordID === 'string') {
            recordIDStr = recordOrRecordID;
        }
        else {
            let record = recordOrRecordID;
            if (server_common_node_1.checkUtils.isObject(record)) {
                // 如果用户没有传入包含 id 的 record，则报错
                if (!record._id) {
                    throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
                }
                if (typeof record._id === 'number') {
                    recordIDStr = record._id.toString();
                }
                else if (typeof record._id === 'string') {
                    recordIDStr = record._id;
                }
            }
        }
        if (recordIDStr.length <= 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('record._id must greater than 0');
        }
        return await Request.GetInstance().deleteRecordBySyncV3(this.apiName, recordIDStr, this.authType);
    }
    async update(_idOrRecordMap, recordMap) {
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return this.updateV3(_idOrRecordMap, recordMap);
        }
        // v1 v2 接口只支持 number 类型
        if (typeof _idOrRecordMap === 'string') {
            throw new server_common_node_1.exceptions.InvalidParamError('_id must be number');
        }
        // record 必须包含 _id
        let record;
        // 用户显式传入 id 的情况
        if (recordMap && typeof _idOrRecordMap === 'number') {
            record = recordMap;
            record['_id'] = _idOrRecordMap;
        }
        else {
            // 用户隐式传入 id 的情况
            record = _idOrRecordMap;
            if (!record._id) {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
            }
            if (typeof record._id !== 'number') {
                throw new server_common_node_1.exceptions.InvalidParamError('the type of record._id is not number');
            }
        }
        if (!record) {
            throw new server_common_node_1.exceptions.InvalidParamError('param is empty');
        }
        record = permissionUtils.delUnauthField(record).newRecord;
        let recordID = record['_id'];
        if (recordID <= 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('record._id must greater than 0');
        }
        if (this.appCtx && this.appCtx.mode == 'openSDK') {
            // request from OpenSDK
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKUpdateRecordBySync(this.apiName, recordID, record);
            });
        }
        return await Request.GetInstance().updateRecordBySync(this.apiName, recordID, record, this.authType);
    }
    ;
    async updateV3(_idOrRecordMap, recordMap) {
        // record 必须包含 _id
        let record;
        // 用户显式传入 id 的情况
        if (recordMap && (typeof _idOrRecordMap === 'string' || typeof _idOrRecordMap === 'number')) {
            record = recordMap;
            if (typeof _idOrRecordMap === 'number')
                record._id = _idOrRecordMap.toString();
            else if (typeof _idOrRecordMap === 'string')
                record._id = _idOrRecordMap;
        }
        else {
            // 用户隐式传入 id 的情况
            record = _idOrRecordMap;
            if (!record._id) {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
            }
            if (typeof record._id === 'number') {
                record._id = record._id.toString();
            }
        }
        if (!record) {
            throw new server_common_node_1.exceptions.InvalidParamError('param is empty');
        }
        record = permissionUtils.delUnauthField(record).newRecord;
        let recordIDStr = record._id;
        if (recordIDStr.length <= 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('record._id must greater than 0');
        }
        return await Request.GetInstance().updateRecordBySyncV3(this.apiName, recordIDStr, record, this.authType);
    }
    // batch sync
    async batchCreate(recordMapList) {
        // 参数校验
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(recordMapList instanceof Array) || recordMapList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        for (let record of recordMapList) {
            if (server_common_node_1.checkUtils.isNotObject(record)) {
                throw new server_common_node_1.exceptions.InvalidParamError('record is not object');
            }
        }
        recordMapList = permissionUtils.batchDelUnauthField(recordMapList).newRecords;
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return await this.batchCreateV3(recordMapList);
        }
        let data = (this.appCtx && this.appCtx.mode == 'openSDK') ?
            await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => await Request.GetInstance().openSDKCreateRecordsBySync(this.apiName, recordMapList))
            : await Request.GetInstance().createRecordsBySync(this.apiName, recordMapList, this.authType);
        // todo: 确定函数返回值
        if (!(data instanceof Array) && data.record_ids) {
            return data.record_ids;
        }
        return data;
    }
    ;
    async batchCreateV3(recordMapList) {
        const dataV3 = await Request.GetInstance().createRecordsBySyncV3(this.apiName, recordMapList, this.authType);
        const ids = (dataV3.items || []).map((item) => item?._id);
        return ids;
    }
    async batchDelete(idOrRecordList) {
        // 参数校验、组装
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(idOrRecordList instanceof Array) || idOrRecordList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return this.batchDeleteV3(idOrRecordList);
        }
        let recordIDs = [];
        for (let record of idOrRecordList) {
            if (typeof (record) === 'number') {
                recordIDs.push(record);
            }
            else if (server_common_node_1.checkUtils.isObject(record) && record._id && typeof (record._id) === 'number') {
                recordIDs.push(record._id);
            }
            else {
                throw new server_common_node_1.exceptions.InvalidParamError('record must be number or object');
            }
        }
        if (this.appCtx && this.appCtx.mode == 'openSDK') {
            // request from OpenSDK
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKDeleteRecordsBySync(this.apiName, recordIDs);
            });
        }
        const errMap = await Request.GetInstance().deleteRecordsBySync(this.apiName, recordIDs, this.authType);
        return (0, structs_1.NewBatchResult)(recordIDs, errMap);
    }
    async batchDeleteV3(idOrRecordList) {
        let recordIDs = [];
        for (let record of idOrRecordList) {
            if (typeof (record) === 'string') {
                recordIDs.push(record);
            }
            else if (typeof (record) === 'number') {
                recordIDs.push(record.toString());
            }
            else if (server_common_node_1.checkUtils.isObject(record) && record._id && typeof (record._id) === 'string') {
                recordIDs.push(record._id);
            }
            else {
                throw new server_common_node_1.exceptions.InvalidParamError('record must be string or number or object');
            }
        }
        const errMap = await Request.GetInstance().deleteRecordsBySyncV3(this.apiName, recordIDs, this.authType);
        return (0, structs_1.NewBatchResult)(recordIDs, errMap);
    }
    async batchUpdate(recordMapList) {
        // 参数校验、组装
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(recordMapList instanceof Array) || recordMapList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        recordMapList = permissionUtils.batchDelUnauthField(recordMapList).newRecords;
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return await this.batchUpdateV3(recordMapList);
        }
        const recordIDs = [];
        let recordMap = {};
        for (let record of recordMapList) {
            let recordID;
            if (typeof record._id === 'number') {
                recordID = record._id;
            }
            else if (typeof record._id === 'string') {
                recordID = parseInt(record._id);
            }
            if ((typeof recordID !== 'number') || recordID <= 0) {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
            }
            recordMap[recordID] = record;
            recordIDs.push(recordID);
        }
        if (this.appCtx && this.appCtx.mode == 'openSDK') {
            // request from OpenSDK
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKUpdateRecordsBySync(this.apiName, recordMapList);
            });
        }
        const errMap = await Request.GetInstance().updateRecordsBySync(this.apiName, recordMap, this.authType);
        return (0, structs_1.NewBatchResult)(recordIDs, errMap);
    }
    ;
    async batchUpdateV3(recordMapList) {
        const recordIDs = [];
        let recordMap = {};
        for (let record of recordMapList) {
            let recordID;
            if (typeof record._id === 'number') {
                recordID = record._id.toString();
            }
            else if (typeof record._id === 'string') {
                recordID = record._id;
            }
            if ((typeof recordID !== 'string') || recordID === '') {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
            }
            recordIDs.push(recordID);
        }
        const errMap = await Request.GetInstance().updateRecordsBySyncV3(this.apiName, recordMapList, this.authType);
        return (0, structs_1.NewBatchResult)(recordIDs, errMap);
    }
    useUserAuth() {
        this.authType = constants_1.AuthTypeUser;
        return this;
    }
    useSystemAuth() {
        this.authType = constants_1.AuthTypeSystem;
        return this;
    }
}
class _KObjectAsync {
    constructor() {
        this.apiName = '';
    }
    // batch async
    async batchCreateAsync(recordMapList) {
        // 参数校验
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(recordMapList instanceof Array) || recordMapList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        if (recordMapList.length > 1000) {
            throw new server_common_node_1.exceptions.InvalidParamError('more than 1000 records in one operation');
        }
        for (let record of recordMapList) {
            if (server_common_node_1.checkUtils.isNotObject(record)) {
                throw new server_common_node_1.exceptions.InvalidParamError('record is not object');
            }
        }
        if (server_common_node_1.utils.stringify(recordMapList).length > 50 * 1024 * 1024) {
            throw new server_common_node_1.exceptions.InvalidParamError('parameter records size exceeds 50MB');
        }
        recordMapList = permissionUtils.batchDelUnauthField(recordMapList).newRecords;
        return await Request.GetInstance().createRecordsByAsync(this.apiName, recordMapList, this.authType);
    }
    ;
    async batchDeleteAsync(recordOrIDList) {
        // 参数校验、组装
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(recordOrIDList instanceof Array) || recordOrIDList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        if (recordOrIDList.length > 1000) {
            throw new server_common_node_1.exceptions.InvalidParamError('more than 1000 records in one operation');
        }
        let recordIDs = [];
        for (let record of recordOrIDList) {
            if (typeof (record) === 'number') {
                recordIDs.push(record);
            }
            else if (server_common_node_1.checkUtils.isObject(record) && record._id && typeof (record._id) === 'number') {
                recordIDs.push(record._id);
            }
            else {
                throw new server_common_node_1.exceptions.InvalidParamError('record must be number or object');
            }
        }
        if (server_common_node_1.utils.stringify(recordIDs).length > 50 * 1024 * 1024) {
            throw new server_common_node_1.exceptions.InvalidParamError('parameter records size exceeds 50MB');
        }
        return await Request.GetInstance().deleteRecordsByAsync(this.apiName, recordIDs, this.authType);
    }
    async batchUpdateAsync(recordMapList) {
        // 参数校验、组装
        if (!this.apiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        if (!(recordMapList instanceof Array) || recordMapList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('param records is not an array or an empty array');
        }
        if (recordMapList.length > 1000) {
            throw new server_common_node_1.exceptions.InvalidParamError('more than 1000 records in one operation');
        }
        recordMapList = permissionUtils.batchDelUnauthField(recordMapList).newRecords;
        let recordMap = {};
        for (let record of recordMapList) {
            let recordID;
            if (typeof record._id === 'number') {
                recordID = record._id;
            }
            else if (typeof record._id === 'string') {
                recordID = parseInt(record._id);
            }
            if (recordID === undefined || recordID === null) {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id is empty');
            }
            if (typeof recordID !== 'number') {
                throw new server_common_node_1.exceptions.InvalidParamError('the type of record._id is not number');
            }
            if (recordID <= 0) {
                throw new server_common_node_1.exceptions.InvalidParamError('record._id must greater than 0');
            }
            recordMap[recordID] = record;
        }
        if (server_common_node_1.utils.stringify(recordMap).length > 50 * 1024 * 1024) {
            throw new server_common_node_1.exceptions.InvalidParamError('parameter records size exceeds 50MB');
        }
        return await Request.GetInstance().updateRecordsByAsync(this.apiName, recordMap, this.authType);
    }
    ;
    useUserAuth() {
        this.authType = constants_1.AuthTypeUser;
        return this;
    }
    useSystemAuth() {
        this.authType = constants_1.AuthTypeSystem;
        return this;
    }
}
class _KObjectQuery {
    constructor() {
        this.appCtx = null;
    }
    // find, findOne
    async find() {
        return new _KQuery(this.apiName, this.appCtx, this.authType).find();
    }
    ;
    async findOne() {
        return new _KQuery(this.apiName, this.appCtx, this.authType).findOne();
    }
    ;
    async findAll() {
        return new _KQuery(this.apiName, this.appCtx, this.authType).findAll();
    }
    ;
    async findStream(handler) {
        return new _KQuery(this.apiName, this.appCtx, this.authType).findStream(handler);
    }
    orderBy(fieldApiNames, ...restFieldApiNames) {
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        return new _KQuery(this.apiName, this.appCtx, this.authType).orderBy(server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames));
    }
    orderByDesc(fieldApiNames, ...restFieldApiNames) {
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        return new _KQuery(this.apiName, this.appCtx, this.authType).orderByDesc(server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames));
    }
    select(fieldApiNames, ...restFieldApiNames) {
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        return new _KQuery(this.apiName, this.appCtx, this.authType).select(server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames));
    }
    where(conditionMap) {
        if (!conditionMap) {
            return new _KQuery(this.apiName, this.appCtx, this.authType).where();
        }
        return new _KQuery(this.apiName, this.appCtx, this.authType).where(conditionMap);
    }
    fuzzySearch(keyword, fieldAPINames) {
        return new _KQuery(this.apiName, this.appCtx, this.authType).fuzzySearch(keyword, fieldAPINames);
    }
    // limit, offset, count
    limit(limit) {
        return new _KQuery(this.apiName, this.appCtx, this.authType).limit(limit);
    }
    ;
    offset(offset) {
        return new _KQuery(this.apiName, this.appCtx, this.authType).offset(offset);
    }
    ;
    async count() {
        return new _KQuery(this.apiName, this.appCtx, this.authType).count();
    }
    ;
    useSystemAuth() {
        this.authType = constants_1.AuthTypeSystem;
        return this;
    }
    useUserAuth() {
        this.authType = constants_1.AuthTypeUser;
        return this;
    }
}
/**
 * _KQuery is kunlun query implement, implements ORM operations.
 */
class _KQuery {
    constructor(objectApiName, appCtx = null, authType = null) {
        if (authType) {
            this.authType = authType;
        }
        if (!objectApiName) {
            throw new server_common_node_1.exceptions.InvalidParamError('objectApiName is empty');
        }
        queryPropertiesStore.set(this, {
            apiName: objectApiName,
            appCtx: appCtx,
            queryBuilder: new queryBuilder_1.QueryBuilder(objectApiName),
            queryV2: appCtx && appCtx.mode === 'openSDK' ? new logicV2_1.QueryV2(objectApiName) : null, // QueryV2 是提供给 openSDK 使用的
        });
    }
    async find() {
        this.findPreCheck();
        const { apiName, appCtx, queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (appCtx && appCtx.dataVersion === 'v3') {
            return await this.findV3(false);
        }
        if (queryV2) {
            const param = {
                limit: queryV2._limit,
                offset: queryV2._offset,
                sort: queryV2._order,
                fields: queryV2.fields,
                count: false,
                filter: (0, logicV2_1.buildCriterionV2)(queryV2.filter),
            };
            return await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
                return await Request.GetInstance().openSDKGetRecords(apiName, param);
            });
        }
        else {
            let criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
            if (queryBuilder.getLogic().logics.length > 0) {
                criterion = await (0, logic_1.handleCriterion)(criterion);
            }
            return await Request.GetInstance().getRecordsOrCountByCriterion(apiName, criterion, queryBuilder.fuzzySearch, queryBuilder.getOrder(), false, queryBuilder.getSelect(), queryBuilder.getOffset(), queryBuilder.getLimit(), false, this.authType);
        }
    }
    ;
    async findOne() {
        // 限制 limit 为 1
        this.limit(1);
        const records = await this.find();
        return records instanceof Array ? (records.length > 0 ? records[0] : null) : null;
    }
    ;
    /**
     * @Deprecated Use FindStream instead.
     */
    async findAll() {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryBuilder.getOrder().length > 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('findAll does not support orderBy and orderByDesc');
        }
        if (queryV2 && queryV2._order.length > 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('findAll does not support orderBy and orderByDesc');
        }
        return await this.getRecordsByPage();
    }
    ;
    async findStream(handler, pageLimit = 200) {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        let offset = 0, orders = [];
        if (queryV2) {
            offset = queryV2._offset;
            orders = queryV2._order;
        }
        else {
            offset = queryBuilder.getOffset();
            orders = queryBuilder.getOrder();
        }
        if (pageLimit === 0) {
            pageLimit = queryBuilder_1.defaultLimit;
        }
        if (orders.length === 0 && offset === 0) {
            // 走主键翻页
            return await this.walkRecordsByID(handler, pageLimit);
        }
        // 走 limit offset 翻页
        return await this.walkRecordsByLimitOffset(handler, pageLimit);
    }
    async walkRecordsByID(handler, pageLimit) {
        const { apiName, appCtx, queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        let limit = 0, selectFields = [];
        if (queryV2) {
            if (queryV2.isSetLimit) {
                limit = queryV2._limit;
            }
            selectFields = queryV2.fields;
        }
        else {
            if (queryBuilder.isSetLimit) {
                limit = queryBuilder.getLimit();
            }
            selectFields = queryBuilder.getSelect();
        }
        let maxId = 0, queryCount = 0;
        let criterionV2;
        let criterion;
        if (queryV2) {
            criterionV2 = (0, logicV2_1.buildCriterionV2)(queryV2.filter);
            criterionV2.push({ leftValue: '_id', operator: operator_1.operates.GT, rightValue: maxId });
        }
        else {
            criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
            if (queryBuilder.getLogic().logics.length > 0) { // 有自定义搜索条件时，需要获取 fields
                criterion = await (0, logic_1.handleCriterion)(criterion);
            }
            // 在最后，添加 _id>maxId 条件
            criterion = (0, logic_1.addIDCriterion)(criterion, apiName, maxId);
        }
        while (true) {
            let newLimit = pageLimit;
            if (limit > 0 && limit - queryCount < pageLimit) {
                newLimit = limit - queryCount;
            }
            if (newLimit <= 0) {
                break;
            }
            let rs;
            if (queryV2) {
                criterionV2[criterionV2.length - 1].rightValue = maxId;
                const param = {
                    limit: newLimit,
                    offset: 0,
                    sort: [{ field: '_id', direction: 'asc', type: '' }],
                    fields: selectFields,
                    count: false,
                    filter: criterionV2,
                };
                rs = await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
                    return await Request.GetInstance().openSDKGetRecords(apiName, param);
                });
            }
            else if (appCtx && appCtx.dataVersion === 'v3') {
                // 更新 maxId
                criterion.conditions[criterion.conditions.length - 1].right.settings.data = maxId;
                // 转换成 V3 的 criterion
                const criterionV3 = (0, logic_1.convertCriterionToCriterionV3)(criterion);
                rs = await Request.GetInstance().getRecordsV3OrCounByCriterion(apiName, criterionV3, queryBuilder.quickQuery, queryBuilder.quickQueryFields, [new order_1.Order('_id', 'asc')], queryBuilder.getSelect(), 0, newLimit, false, this.authType);
            }
            else {
                // 更新 maxId
                criterion.conditions[criterion.conditions.length - 1].right.settings.data = maxId;
                // 发起请求
                rs = await Request.GetInstance().getRecordsOrCountByCriterion(apiName, criterion, queryBuilder.fuzzySearch, [new order_1.Order('_id', 'asc')], false, queryBuilder.getSelect(), 0, newLimit, false, this.authType);
            }
            queryCount += rs.length;
            rs.forEach((r) => {
                maxId = r._id > maxId ? r._id : maxId;
            });
            try {
                if (rs.length > 0) {
                    await handler(rs);
                }
            }
            catch (err) {
                throw err;
            }
            if (rs.length < pageLimit) {
                break;
            }
        }
    }
    async walkRecordsByLimitOffset(handler, pageLimit) {
        const { apiName, appCtx, queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        let limit = 0, offset = 0, selectFields = [], orders = [];
        if (queryV2) {
            if (queryV2.isSetLimit) {
                limit = queryV2._limit;
            }
            offset = queryV2._offset;
            selectFields = queryV2.fields;
            orders = queryV2._order;
        }
        else {
            if (queryBuilder.isSetLimit) {
                limit = queryBuilder.getLimit();
            }
            offset = queryBuilder.getOffset();
            selectFields = queryBuilder.getSelect();
            orders = queryBuilder.getOrder();
        }
        // 当用户未设置排序字段时，强制指定为主键增序，避免数据重复
        if (!orders || orders.length === 0) {
            orders = [{ field: '_id', direction: 'asc', type: '' }];
        }
        let maxId = 0, queryCount = 0;
        let criterionV2;
        let criterion;
        if (queryV2) {
            criterionV2 = (0, logicV2_1.buildCriterionV2)(queryV2.filter);
            criterionV2.push({ leftValue: '_id', operator: operator_1.operates.GT, rightValue: maxId });
        }
        else {
            criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
            if (queryBuilder.getLogic().logics.length > 0) { // 有自定义搜索条件时，需要获取 fields
                criterion = await (0, logic_1.handleCriterion)(criterion);
            }
            // 在最后，添加 _id>maxId 条件
            criterion = (0, logic_1.addIDCriterion)(criterion, apiName, maxId);
        }
        let curOffset = offset;
        while (true) {
            let newLimit = function () {
                if (limit == 0) {
                    return pageLimit;
                }
                if (offset + limit - curOffset < pageLimit) {
                    return offset + limit - curOffset;
                }
                return pageLimit;
            }();
            if (newLimit <= 0) {
                break;
            }
            let rs;
            if (queryV2) {
                criterionV2[criterionV2.length - 1].rightValue = maxId;
                const param = {
                    limit: newLimit,
                    offset: curOffset,
                    sort: orders,
                    fields: selectFields,
                    count: false,
                    filter: criterionV2,
                };
                rs = await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
                    return await Request.GetInstance().openSDKGetRecords(apiName, param);
                });
            }
            else if (appCtx && appCtx.dataVersion === 'v3') {
                // 更新 maxId
                criterion.conditions[criterion.conditions.length - 1].right.settings.data = maxId;
                // 转换成 V3 的 criterion
                const criterionV3 = (0, logic_1.convertCriterionToCriterionV3)(criterion);
                rs = await Request.GetInstance().getRecordsV3OrCounByCriterion(apiName, criterionV3, queryBuilder.quickQuery, queryBuilder.quickQueryFields, orders, selectFields, curOffset, newLimit, false, this.authType);
            }
            else {
                // 更新 maxId
                criterion.conditions[criterion.conditions.length - 1].right.settings.data = maxId;
                // 发起请求
                rs = await Request.GetInstance().getRecordsOrCountByCriterion(apiName, criterion, queryBuilder.fuzzySearch, orders, false, selectFields, curOffset, newLimit, false, this.authType);
            }
            queryCount += rs.length;
            try {
                if (rs.length > 0) {
                    await handler(rs);
                }
            }
            catch (err) {
                throw err;
            }
            if (rs.length < pageLimit) {
                break;
            }
            curOffset += pageLimit;
        }
    }
    async getRecordsByPage() {
        const { apiName, appCtx, queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        let maxId = 0, records = [];
        while (true) {
            let rs;
            if (queryV2) {
                let criterion = (0, logicV2_1.buildCriterionV2)(queryV2.filter);
                criterion.push({ leftValue: '_id', operator: operator_1.operates.GT, rightValue: maxId });
                const param = {
                    limit: 200,
                    offset: 0,
                    sort: [{ field: '_id', direction: 'asc', type: '' }],
                    fields: queryV2.fields,
                    count: false,
                    filter: criterion,
                };
                rs = await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
                    return await Request.GetInstance().openSDKGetRecords(apiName, param);
                });
            }
            else {
                let criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
                if (queryBuilder.getLogic().logics.length > 0) {
                    criterion = await (0, logic_1.handleCriterion)(criterion);
                }
                criterion = (0, logic_1.addIDCriterion)(criterion, apiName, maxId);
                rs = await Request.GetInstance().getRecordsOrCountByCriterion(apiName, criterion, null, // FindAll 不再迭代
                [new order_1.Order('_id', 'asc')], false, queryBuilder.getSelect(), 0, queryBuilder_1.defaultLimit, false, this.authType);
            }
            rs.forEach((r) => {
                maxId = r._id > maxId ? r._id : maxId;
            });
            records.push(...rs);
            if (rs.length < queryBuilder_1.defaultLimit) {
                break;
            }
        }
        return records;
    }
    orderBy(fieldApiNames, ...restFieldApiNames) {
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        let fields = server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames);
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryV2) {
            queryV2.orderBy(fields);
        }
        else {
            queryBuilder.addOrders(fields, order_1.ASC);
        }
        return this;
    }
    orderByDesc(fieldApiNames, ...restFieldApiNames) {
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        let fields = server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames);
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryV2) {
            queryV2.orderByDesc(fields);
        }
        else {
            queryBuilder.addOrders(fields, order_1.DESC);
        }
        return this;
    }
    select(fieldApiNames, ...restFieldApiNames) {
        const { appCtx } = queryPropertiesStore.get(this);
        fieldApiNames = !fieldApiNames ? [] : fieldApiNames;
        let fields = server_common_node_1.utils.argsToList(fieldApiNames, restFieldApiNames);
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryV2) {
            queryV2.select(fields);
        }
        else {
            queryBuilder.addSelects(fields);
        }
        return this;
    }
    where(conditionMap) {
        // 如果 where 内是空，直接返回
        if (!conditionMap || Object.keys(conditionMap).length === 0) {
            return this;
        }
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryV2) {
            queryV2.where(conditionMap);
        }
        else {
            let logic;
            // 如果 conditionMap 不是 Logic，需要构建为 Logic
            if (!(conditionMap instanceof logic_1.Logic)) {
                logic = (0, logic_1.buildLogic)([conditionMap]);
            }
            else {
                logic = conditionMap;
            }
            queryBuilder.addLogic(logic);
        }
        return this;
    }
    fuzzySearch(keyword, fieldAPINames) {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (queryV2) {
            throw new server_common_node_1.exceptions.InvalidParamError(`OpenSDK does not implement FuzzySearch`);
        }
        if (queryBuilder.fuzzySearch) {
            throw new server_common_node_1.exceptions.InvalidParamError(`FuzzySearch can only be called once`);
        }
        if (!keyword) {
            throw new server_common_node_1.exceptions.InvalidParamError(`FuzzySearch's keyword can not be empty`);
        }
        if (!fieldAPINames || fieldAPINames.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError(`FuzzySearch's fieldAPINames can not be empty`);
        }
        queryBuilder.fuzzySearch = {
            keyword: keyword,
            fieldAPINames: fieldAPINames,
        };
        queryBuilder.quickQuery = keyword;
        queryBuilder.quickQueryFields = fieldAPINames;
        return this;
    }
    limit(limit) {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        limit = Number(limit);
        if (queryV2) {
            queryV2.limit(limit);
        }
        else {
            queryBuilder.setLimit(limit);
        }
        return this;
    }
    ;
    offset(offset) {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        offset = Number(offset);
        if (queryV2) {
            queryV2.offset(offset);
        }
        else {
            queryBuilder.setOffset(offset);
        }
        return this;
    }
    ;
    async count() {
        const { apiName, appCtx, queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        if (appCtx && appCtx.dataVersion === 'v3') {
            return await this.findV3(true);
        }
        if (queryV2) {
            const param = {
                limit: 1,
                offset: queryV2._offset,
                fields: queryV2.fields,
                sort: queryV2._order,
                count: true,
                filter: (0, logicV2_1.buildCriterionV2)(queryV2.filter),
            };
            param.count = true;
            return await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
                return await Request.GetInstance().openSDKGetRecords(apiName, param);
            });
        }
        else {
            let criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
            if (queryBuilder.getLogic().logics.length > 0) {
                criterion = await (0, logic_1.handleCriterion)(criterion);
            }
            return await Request.GetInstance().getRecordsOrCountByCriterion(apiName, criterion, queryBuilder.fuzzySearch, queryBuilder.getOrder(), false, queryBuilder.getSelect(), queryBuilder.getOffset(), queryBuilder.getLimit(), true, this.authType);
        }
    }
    ;
    async findV3(needCount) {
        const { apiName, queryBuilder } = queryPropertiesStore.get(this);
        let criterion = (0, logic_1.buildCriterion)(queryBuilder.getLogic(), apiName);
        if (queryBuilder.getLogic().logics.length > 0) {
            criterion = await (0, logic_1.handleCriterion)(criterion);
        }
        const criterionV3 = (0, logic_1.convertCriterionToCriterionV3)(criterion);
        const res = await Request.GetInstance().getRecordsV3OrCounByCriterion(apiName, criterionV3, queryBuilder.quickQuery, queryBuilder.quickQueryFields, queryBuilder.getOrder(), queryBuilder.getSelect(), queryBuilder.getOffset(), queryBuilder.getLimit(), needCount, this.authType);
        if (needCount) {
            return res;
        }
        return res;
    }
    findPreCheck() {
        const { queryBuilder, queryV2 } = queryPropertiesStore.get(this);
        let limit = queryBuilder_1.defaultLimit;
        if (queryV2) {
            limit = queryV2._limit;
        }
        else {
            limit = queryBuilder.limit;
        }
        if (limit < 1) {
            // need import exceptions
            throw new server_common_node_1.exceptions.InvalidParamError(`limit(${limit}) < 1`);
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
function applyMixins(derivedCtor, constructors) {
    constructors.forEach((baseCtor) => {
        Object.getOwnPropertyNames(baseCtor.prototype).forEach((name) => {
            Object.defineProperty(derivedCtor.prototype, name, Object.getOwnPropertyDescriptor(baseCtor.prototype, name) ||
                Object.create(null));
        });
    });
}
applyMixins(_KObject, [_KObjectSync, _KObjectAsync, _KObjectQuery]);
applyMixins(_KApplicationObject, [_KObjectSync, _KObjectQuery]); // @ts-ignore
