"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.QueryBuilder = exports.defaultLimit = void 0;
const order_1 = require("./order");
const logic_1 = require("../../../kunlun/operator/impl/logic");
const server_common_node_1 = require("@byted-apaas/server-common-node");
// SDK 仅作 limit 小于 0 校验，其他校验拦截由底层控制，如当查询结果不满足受控条件时，limit 仅支持最大 200
exports.defaultLimit = 200;
/**
 * 查询构造器，在 DB 中被初始化，用于构建一次查询
 */
class QueryBuilder {
    constructor(objectApiName) {
        this.objectApiName = objectApiName;
        this.dataSource = '';
        this.select = [];
        this.where = null;
        this.limit = exports.defaultLimit;
        this.offset = 0;
        this.order = [];
        this.logic = new logic_1.Logic();
    }
    addLogic(logic) {
        this.logic.addLogic(logic);
    }
    getLogic() {
        return this.logic;
    }
    addSelect(fieldApiName) {
        this.select.push(fieldApiName);
    }
    addSelects(fields) {
        fields.forEach(field => {
            // field 非空，则 push 进查询条件
            if (field) {
                this.select.push(field);
            }
        });
    }
    getSelect() {
        return this.select;
    }
    addOrder(field, orderType) {
        this.order.push(new order_1.Order(field, orderType));
    }
    addOrders(fields, orderType) {
        fields.forEach(field => this.order.push(new order_1.Order(field, orderType)));
    }
    getOrder() {
        return this.order;
    }
    setOffset(offset) {
        if (offset < 0) {
            // need import exceptions
            throw new server_common_node_1.exceptions.InvalidParamError(`offset(${offset}) < 0`);
        }
        this.offset = offset;
    }
    setLimit(limit) {
        this.limit = limit;
        this.isSetLimit = true;
    }
    getLimit() {
        return this.limit;
    }
    getOffset() {
        return this.offset;
    }
}
exports.QueryBuilder = QueryBuilder;
