"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.GlobalVar = void 0;
const faasinfra_1 = require("../../http/faasinfra");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
class GlobalVar {
    async getVar(key) {
        let res = await (0, faasinfra_1.requestGlobalVar)(key);
        if (!res || !res.value_type) {
            throw new exceptions_1.InternalError(`global variable is invalid ${JSON.stringify(res)}`);
        }
        switch (res.value_type) {
            case 'string':
                return res.value;
            case 'number':
                let resNum = Number(res.value);
                if (isNaN(resNum)) {
                    throw new exceptions_1.InternalError(`value is not number ${res.value}`);
                }
                return resNum;
            default:
                return res.value;
        }
    }
}
exports.GlobalVar = GlobalVar;
