"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.QueryOptions = void 0;
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const operator_1 = require("./operator");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const constants_1 = require("./constants");
class QueryOptions {
    constructor() {
        this.query = {};
    }
    buildRequestParam() {
        let param = { op: this.op };
        if (this.query !== undefined) {
            param.query = this.query;
        }
        if (this.projection !== undefined) {
            param.projection = this.projection;
        }
        if (this.sort !== undefined) {
            param.sort = this.sort;
        }
        if (this.skip !== undefined) {
            param.skip = this.skip;
        }
        if (this.limit !== undefined) {
            param.limit = this.limit;
        }
        if (this.populateFields !== undefined) {
            param.populateFields = this.populateFields;
        }
        if (this.update !== undefined) {
            param.update = this.update;
        }
        if (this.update !== undefined) {
            param.update = this.update;
        }
        if (this.replace !== undefined) {
            param.replace = this.replace;
        }
        if (this.hint !== undefined) {
            param.hint = this.hint;
        }
        if (this.aggregate) {
            this.pipeline.push(this.matchGeneral);
            this.pipeline.push(this.stage);
            param.pipeline = this.pipeline;
            param.query = undefined;
        }
        return param;
    }
    addProjection(key, value) {
        if (!this.projection) {
            this.projection = {};
        }
        this.projection[key] = value;
    }
    addSort(key, value) {
        if (!this.sort) {
            this.sort = [];
        }
        this.sort.push({ [key]: value });
    }
    addCondition(key, value) {
        if (!this.query) {
            this.query = {};
        }
        if (this.query[key] !== undefined) {
            this.and({ key: value });
        }
        else {
            this.query[key] = value;
        }
    }
    addPopulate(...value) {
        if (this.populateFields === undefined) {
            this.populateFields = [];
        }
        this.populateFields.push(...value);
    }
    setSkip(skip) {
        if (typeof (skip) !== 'number') {
            throw new exceptions_1.InvalidParamError(`The type of skip (${skip}) should be number, but ${typeof (skip)}`);
        }
        if (skip < 0) {
            throw new exceptions_1.InvalidParamError(`The value of skip should be greater than or equals 0, but ${skip}`);
        }
        this.skip = skip;
    }
    setLimit(limit) {
        if (typeof (limit) !== 'number') {
            throw new exceptions_1.InvalidParamError(`The type of limit (${limit}) should be number, but ${typeof (limit)}`);
        }
        if (limit < 1 || limit > 1000) {
            throw new exceptions_1.InvalidParamError(`The value of limit should be 1~1000, but ${limit}`);
        }
        this.limit = limit;
    }
    and(...conditions) {
        this.logic(operator_1.Operator.AND, ...conditions);
    }
    or(...conditions) {
        this.logic(operator_1.Operator.OR, ...conditions);
    }
    nor(...conditions) {
        this.logic(operator_1.Operator.NOR, ...conditions);
    }
    logic(op, ...conditions) {
        if (conditions.length === 0) {
            return;
        }
        if (this.query && server_common_node_1.utils.isObject(this.query) && Object.keys(this.query).length > 0) {
            conditions = [this.query, ...conditions];
        }
        if (conditions.length === 0) {
            return;
        }
        else if (conditions.length === 1) {
            this.query = conditions[0];
        }
        else if (conditions.length > 1) {
            this.query = {};
            this.query[op] = conditions;
        }
    }
    setUpdate(value, op) {
        if (!server_common_node_1.utils.isObject(value)) {
            throw new exceptions_1.InvalidParamError(`The type of value should be object, but ${typeof (value)}`);
        }
        if (Object.keys(value).length === 0) {
            throw new exceptions_1.InvalidParamError(`The keys of value cannot be empty`);
        }
        if (this.update === undefined) {
            this.update = {};
        }
        if (this.update[op] === undefined) {
            this.update[op] = value;
        }
        else {
            this.update[op] = { ...this.update[op], ...value };
        }
    }
    handleUpdatedAt() {
        if (this.update === undefined) {
            return;
        }
        if (this.update[operator_1.Operator.SET] === undefined) {
            this.update[operator_1.Operator.SET] = {};
        }
        if (this.update[operator_1.Operator.SET].updatedAt === undefined) {
            this.setUpdate({ updatedAt: new Date() }, operator_1.Operator.SET);
        }
    }
    isAggregate() {
        return this.aggregate;
    }
    groupBy(field) {
        this.op = constants_1.OperatorType.AGGREGATE;
        if (!this.aggregate) {
            this.aggregate = true;
            this.stage = { type: 'group', group: {} };
            this.matchGeneral = { type: 'matchGeneral', match: {} };
        }
        if (this.pipeline === undefined) {
            this.pipeline = [];
        }
        if (this.query !== undefined) {
            this.matchGeneral.match = this.query;
        }
        if (field === undefined) {
            this.stage.group._id = null;
            return;
        }
        let autoAs;
        if (typeof field === 'string') {
            autoAs = field;
            field = '$' + field;
        }
        else {
            autoAs = JSON.stringify(field);
        }
        this.stage.idAlias = autoAs;
        this.stage.group._id = field;
        this.asForGroupBy = true;
    }
    groupOp(field, op) {
        if (!this.isAggregate()) {
            throw new exceptions_1.InvalidParamError('This operation cannot be used by non-aggregate operations');
        }
        this.asForGroupBy = false;
        let opNoPrefix = op.slice(1);
        if (field === undefined) {
            this.aggOpAs = `${opNoPrefix}()`;
        }
        else {
            this.aggOpAs = `${opNoPrefix}(${JSON.stringify(field)})`;
        }
        if (this.stage.group[this.aggOpAs] === undefined) {
            this.stage.group[this.aggOpAs] = {};
        }
        if (op === operator_1.Operator.NUM) {
            this.stage.group[this.aggOpAs][operator_1.Operator.SUM] = 1;
        }
        else if (typeof (field) === 'string') {
            this.stage.group[this.aggOpAs][op] = '$' + field;
        }
        else {
            this.stage.group[this.aggOpAs][op] = field;
        }
    }
    as(alias) {
        if (this.asForGroupBy) {
            this.stage.idAlias = alias;
        }
        else {
            let value = this.stage.group[this.aggOpAs];
            delete this.stage.group[this.aggOpAs];
            this.stage.group[alias] = value;
        }
    }
    setUpsert(upsert) {
        this.upsert = upsert;
    }
    setReplace(replace) {
        this.replace = replace;
    }
    setHint(hint) {
        this.hint = hint;
    }
    isUpsert() {
        return this.upsert === true;
    }
}
exports.QueryOptions = QueryOptions;
