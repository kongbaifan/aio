"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.OrderDESC = exports.OrderASC = exports.Order = exports.OperatorType = void 0;
var OperatorType;
(function (OperatorType) {
    OperatorType["INSERT"] = "insert";
    OperatorType["FIND"] = "find";
    OperatorType["FIND_ONE"] = "findOne";
    OperatorType["DISTINCT"] = "distinct";
    OperatorType["DELETE"] = "delete";
    OperatorType["COUNT"] = "count";
    OperatorType["UPDATE"] = "update";
    OperatorType["REPLACE"] = "replace";
    OperatorType["AGGREGATE"] = "aggregate";
    OperatorType["BULK_WRITE"] = "bulkWrite";
    OperatorType["AUTOFILL_POPULATE_SPEC"] = "autofillPopulateSpec";
})(OperatorType = exports.OperatorType || (exports.OperatorType = {}));
class Order {
    constructor(name, direction) {
        this.name = name;
        this.direction = direction;
    }
}
exports.Order = Order;
class OrderASC extends Order {
    constructor(field) {
        super(field, 1);
    }
}
exports.OrderASC = OrderASC;
class OrderDESC extends Order {
    constructor(field) {
        super(field, -1);
    }
}
exports.OrderDESC = OrderDESC;
