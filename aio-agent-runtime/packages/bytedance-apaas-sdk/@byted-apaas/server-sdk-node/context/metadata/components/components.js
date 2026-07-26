"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.mobile = exports.desktop = exports.Component = void 0;
const common_1 = require("./common");
Object.defineProperty(exports, "Component", { enumerable: true, get: function () { return common_1.Component; } });
const recordDetail_1 = require("./desktop/recordDetail");
const list_1 = require("./desktop/list");
const list_2 = require("./mobile/list");
const desktop = {
    RecordDetail: recordDetail_1.RecordDetail,
    List: list_1.List,
};
exports.desktop = desktop;
const mobile = {
    List: list_2.List,
};
exports.mobile = mobile;
