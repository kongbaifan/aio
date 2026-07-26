"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Object = void 0;
const fields = require("./fields");
class Objects {
    constructor(obj) {
        if (!obj) {
            return;
        }
        this.label = obj.label;
        this.apiName = obj.api_name;
        this.displayName = '';
        this.searchSupplementaryInfo = [];
        this.searchableFields = [];
        this.fields = fields.parseFields(obj.fields);
    }
}
exports.Object = Objects;
