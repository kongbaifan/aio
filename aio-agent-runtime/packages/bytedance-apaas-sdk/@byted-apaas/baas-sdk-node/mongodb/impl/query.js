"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Query = void 0;
const constants_1 = require("./constants");
const faasinfra = require("../../http/faasinfra");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const operator_1 = require("./operator");
const condition_1 = require("./condition");
const proxy_1 = require("./proxy");
const options_1 = require("./options");
class Query {
    constructor(tableName) {
        this.tableName = tableName;
        this.args = new options_1.QueryOptions();
    }
    buildRequestParam() {
        if (!this.args.op) {
            throw new exceptions_1.InternalError('The value of op cannot be empty');
        }
        return {
            tableName: this.tableName,
            args: this.args.buildRequestParam(),
        };
    }
    /**
     * 查询记录，最大 1000 条
     */
    async find() {
        if (!this.args.isAggregate()) {
            this.args.op = constants_1.OperatorType.FIND;
        }
        let records = await faasinfra.requestMongodb(this.buildRequestParam());
        if (!Array.isArray(records)) {
            throw new exceptions_1.InternalError('The result of query is not array');
        }
        records.forEach(record => {
            Object.defineProperty(record, proxy_1.p.isQuery, {
                value: this.tableName,
                enumerable: false,
                writable: true,
            });
        });
        if (!records) {
            return [];
        }
        return records;
    }
    /**
     * 查询单条记录
     */
    async findOne() {
        this.args.op = constants_1.OperatorType.FIND_ONE;
        let record = await faasinfra.requestMongodb(this.buildRequestParam());
        if (!record) {
            return null;
        }
        if (!server_common_node_1.utils.isObject(record)) {
            throw new exceptions_1.InternalError('The result of query is not object');
        }
        Object.defineProperty(record, proxy_1.p.isQuery, {
            value: this.tableName,
            enumerable: false,
            writable: true,
        });
        return record;
    }
    async count() {
        this.args.op = constants_1.OperatorType.COUNT;
        let result = await faasinfra.requestMongodb(this.buildRequestParam());
        if (!result || !result.count) {
            return 0;
        }
        return result.count;
    }
    async delete() {
        this.args.op = constants_1.OperatorType.DELETE;
        return await faasinfra.requestMongodb(this.buildRequestParam());
    }
    async save() {
        this.args.handleUpdatedAt();
        this.args.op = constants_1.OperatorType.UPDATE;
        return await faasinfra.requestMongodb(this.buildRequestParam());
    }
    projection(value) {
        if (!value) {
            return this;
        }
        if (!server_common_node_1.utils.isObject(value)) {
            throw new exceptions_1.InvalidParamError(`The type of value (${value}) should be object, but ${typeof (value)}`);
        }
        Object.entries(value).forEach(([k, v]) => {
            if (typeof (k) !== 'string') {
                throw new exceptions_1.InvalidParamError(`The type of value (${k}) should be string, but ${typeof (value)}`);
            }
            if (v !== 0 && v !== 1) {
                throw new exceptions_1.InvalidParamError(`The value should be 0 or 1, but ${v}`);
            }
            this.args.addProjection(k, v);
        });
        return this;
    }
    sort(value) {
        if (!value) {
            return this;
        }
        if (Array.isArray(value)) {
            for (let item of value) {
                if (!server_common_node_1.utils.isObject(item)) {
                    throw new exceptions_1.InvalidParamError(`The type of value's item (${item}) should be object or array, but ${typeof (item)}`);
                }
                let entries = Object.entries(item);
                if (entries.length !== 1) {
                    throw new exceptions_1.InvalidParamError(`The length of value's item (${item}) should be 1, but ${entries.length}`);
                }
                entries.forEach(([k, v]) => {
                    if (typeof (k) !== 'string') {
                        throw new exceptions_1.InvalidParamError(`The type of value's item (${k}) should be string, but ${typeof (k)}`);
                    }
                    if (v !== 1 && v !== -1) {
                        throw new exceptions_1.InvalidParamError(`The value's item should be 1 or -1, but ${v}`);
                    }
                    this.args.addSort(k, v);
                });
            }
        }
        else if (server_common_node_1.utils.isObject(value)) {
            Object.entries(value).forEach(([k, v]) => {
                if (typeof (k) !== 'string') {
                    throw new exceptions_1.InvalidParamError(`The type of value (${k}) should be string, but ${typeof (k)}`);
                }
                if (v !== 1 && v !== -1) {
                    throw new exceptions_1.InvalidParamError(`The value should be 1 or -1, but ${v}`);
                }
                this.args.addSort(k, v);
            });
        }
        else {
            throw new exceptions_1.InvalidParamError(`The type of value (${value}) should be object or array, but ${typeof (value)}`);
        }
        return this;
    }
    skip(value) {
        this.args.setSkip(value);
        return this;
    }
    limit(value) {
        this.args.setLimit(value);
        return this;
    }
    // 聚合操作，好的实现方式是抽出 AggQuery 类，这里未抽取原因是与 qfw 对齐
    groupBy(field) {
        this.args.groupBy(field);
        return this;
    }
    as(alias) {
        this.args.as(alias);
        return this;
    }
    sum(field) {
        this.args.groupOp(field, operator_1.Operator.SUM);
        return this;
    }
    avg(field) {
        this.args.groupOp(field, operator_1.Operator.AVG);
        return this;
    }
    min(field) {
        if (this.args.isAggregate()) {
            this.args.groupOp(field, operator_1.Operator.MIN);
        }
        else {
            this.updateSetOp(field, operator_1.Operator.MIN);
        }
        return this;
    }
    max(field) {
        if (this.args.isAggregate()) {
            this.args.groupOp(field, operator_1.Operator.MAX);
        }
        else {
            this.updateSetOp(field, operator_1.Operator.MAX);
        }
        return this;
    }
    num() {
        this.args.groupOp(undefined, operator_1.Operator.NUM);
        return this;
    }
    first(field) {
        this.args.groupOp(field, operator_1.Operator.FIRST);
        return this;
    }
    last(field) {
        this.args.groupOp(field, operator_1.Operator.LAST);
        return this;
    }
    stdDevPop(field) {
        this.args.groupOp(field, operator_1.Operator.STD_DEV_POP);
        return this;
    }
    stdDevSamp(field) {
        this.args.groupOp(field, operator_1.Operator.STD_DEV_SAMP);
        return this;
    }
    mergeToArray(field) {
        this.args.groupOp(field, operator_1.Operator.PUSH);
        return this;
    }
    mergeToObject(field) {
        this.args.groupOp(field, operator_1.Operator.MERGE_OBJECTS);
        return this;
    }
    mergeToSet(field) {
        this.args.groupOp(field, operator_1.Operator.ADD_TO_SET);
        return this;
    }
    // 算术操作
    whereOp(value, op) {
        if (!this.wherePath) {
            return this;
        }
        return this.where({ [this.wherePath]: { [op]: value } });
    }
    equals(value) {
        return this.whereOp(value, operator_1.Operator.EQ);
    }
    eq(value) {
        return this.equals(value);
    }
    notEquals(value) {
        return this.whereOp(value, operator_1.Operator.NE);
    }
    ne(value) {
        return this.notEquals(value);
    }
    greaterThan(value) {
        return this.whereOp(value, operator_1.Operator.GT);
    }
    gt(value) {
        return this.greaterThan(value);
    }
    greaterThanOrEquals(value) {
        return this.whereOp(value, operator_1.Operator.GTE);
    }
    gte(value) {
        return this.greaterThanOrEquals(value);
    }
    lessThan(value) {
        return this.whereOp(value, operator_1.Operator.LT);
    }
    lt(value) {
        return this.lessThan(value);
    }
    lessThanOrEquals(value) {
        return this.whereOp(value, operator_1.Operator.LTE);
    }
    lte(value) {
        return this.lessThanOrEquals(value);
    }
    in(value) {
        return this.whereOp(value, operator_1.Operator.IN);
    }
    notIn(value) {
        return this.whereOp(value, operator_1.Operator.NIN);
    }
    nin(value) {
        return this.notIn(value);
    }
    regex(value) {
        if (typeof (value) === 'string') {
            return this.whereOp(value, operator_1.Operator.REGEX);
        }
        else if (server_common_node_1.utils.isRegex(value)) {
            return this.whereOp(value.source, operator_1.Operator.REGEX);
        }
        throw new exceptions_1.InvalidParamError(`The type of value should be string or regex, but ${typeof (value)}`);
    }
    near(geo, max, min = 0) {
        if (!this.wherePath) {
            return this;
        }
        return this.where({
            [this.wherePath]: {
                [operator_1.Operator.NEAR]: {
                    [operator_1.Operator.GEOMETRY]: geo,
                    [operator_1.Operator.MAX_DISTANCE]: max,
                    [operator_1.Operator.MIN_DISTANCE]: min,
                }
            }
        });
    }
    set(value) {
        if (!value) {
            throw new exceptions_1.InvalidParamError('The value cannot be empty');
        }
        if (typeof (value) === 'string') {
            this.updatePath = value;
        }
        else if (server_common_node_1.utils.isObject(value)) {
            this.args.setUpdate(value, operator_1.Operator.SET);
        }
        else {
            throw new exceptions_1.InvalidParamError(`The type of value should be string or object, but ${typeof (value)}`);
        }
        return this;
    }
    // updateSetOp
    updateSetOp(value, op) {
        if (!this.updatePath) {
            return this;
        }
        this.args.setUpdate({ [this.updatePath]: value }, op);
        return this;
    }
    to(value) {
        return this.updateSetOp(value, operator_1.Operator.SET);
    }
    increment(value) {
        return this.updateSetOp(value, operator_1.Operator.INC);
    }
    inc(value) {
        return this.increment(value);
    }
    multiply(value) {
        return this.updateSetOp(value, operator_1.Operator.MUL);
    }
    mul(value) {
        return this.multiply(value);
    }
    currentDate() {
        return this.updateSetOp(true, operator_1.Operator.CURRENT_DATE);
    }
    rename(value) {
        return this.updateSetOp(value, operator_1.Operator.RENAME);
    }
    unset() {
        return this.updateSetOp('', operator_1.Operator.UNSET);
    }
    setOnInsert(value) {
        if (!this.args.isUpsert()) {
            throw new exceptions_1.InvalidParamError(`The setOnInsert is not supported when upsert is false`);
        }
        this.args.setUpdate(value, operator_1.Operator.SET_ON_INSERT);
        return this;
    }
    /**
     * 关联查询 TODO 暂不支持
     *
     * @param value 关联查询规则，类型为字符串、对象或数组
     */
    populate(value) {
        if (!value) {
            throw new exceptions_1.InvalidParamError(`The value cannot be empty`);
        }
        if (typeof value === 'string') {
            this.args.addPopulate(value);
        }
        else if (Array.isArray(value)) {
            this.args.addPopulate(...value);
        }
        else if (server_common_node_1.utils.isObject(value)) {
            this.args.addPopulate(value);
        }
        else {
            throw new exceptions_1.InvalidParamError(`The type of value should be string, object or array, but ${typeof (value)}`);
        }
        return this;
    }
    replace(value) {
        this.args.setReplace(true);
        return this;
    }
    upsert() {
        this.args.setUpsert(true);
        return this;
    }
    /**
     * 指定查询选择某个索引
     *
     * @param value 索引名或索引定义
     */
    hint(value) {
        this.args.setHint(value);
        return this;
    }
    where(condition) {
        if (!condition) {
            return this;
        }
        else if (typeof condition === 'string') {
            this.wherePath = condition;
            return this;
        }
        let filter = this.handleCondition(condition);
        this.args.and(filter);
        return this;
    }
    and(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.args.and(...conditions);
        return this;
    }
    or(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.args.or(...conditions);
        return this;
    }
    nor(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.args.nor(...conditions);
        return this;
    }
    handleCondition(condition) {
        if (!condition) {
            return this;
        }
        else if (typeof condition === 'function') {
            return this.convertFilter({ $where: condition });
        }
        else if (condition._bsontype === 'ObjectID') {
            return this.convertFilter({ _id: condition });
        }
        else if (Array.isArray(condition)) {
            let ids = condition.map(v => v._id);
            return this.convertFilter({ _id: { '$in': ids } });
        }
        return this.convertFilter(condition);
    }
    convertFilter(arg) {
        if (!arg) {
            return;
        }
        if (!server_common_node_1.utils.isObject(arg)) {
            throw new exceptions_1.InternalError('arg is not object');
        }
        if (arg instanceof condition_1.Condition) {
            return arg.toJSON();
        }
        Object.entries(arg).forEach(([key, value]) => {
            if (typeof (key) !== 'string') {
                throw new exceptions_1.InvalidParamError(`The type of key should be string, but ${key}`);
            }
            if (server_common_node_1.utils.isRegex(value)) {
                arg[key] = { $regex: value.source };
            }
        });
        return arg;
    }
}
exports.Query = Query;
