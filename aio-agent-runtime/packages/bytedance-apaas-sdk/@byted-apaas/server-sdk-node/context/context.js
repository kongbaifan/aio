"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Context = void 0;
const server_common_node_1 = require("@byted-apaas/server-common-node");
class Context extends server_common_node_1.Context {
    /**
     * 全局函数
     * @param funcName 函数名
     */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    function(funcName) {
        return null;
    }
    /**
     * 根据 apiName 获取对应的全局变量
     * @param apiName 全局变量的 API Name
     */
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    async getVar(apiName) {
        return null;
    }
}
exports.Context = Context;
