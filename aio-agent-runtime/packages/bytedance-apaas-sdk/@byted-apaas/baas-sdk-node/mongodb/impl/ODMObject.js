"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildODMObject = void 0;
const proxy_1 = require("./proxy");
function buildODMObject(tableName, originRecord) {
    if (originRecord[proxy_1.p.tableName] === tableName) {
        return originRecord;
    }
    Object.defineProperties(originRecord, {
        [proxy_1.p.tableName]: {
            value: tableName,
            enumerable: false,
        }
    });
    return originRecord;
}
exports.buildODMObject = buildODMObject;
