"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Order = exports.DESC = exports.ASC = void 0;
exports.ASC = 'asc';
exports.DESC = 'desc';
class Order {
    constructor(fieldApiName, direction) {
        this.field = fieldApiName;
        this.type = '';
        this.direction = direction;
    }
}
exports.Order = Order;
