"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.GlobalConfig = void 0;
const Request = require("../../request/interface");
class GlobalConfig {
    /**
     * 根据 key 获取对应的全局变量
     * @param key 全局变量的 key
     */
    async getVar(key) {
        return await Request.GetInstance().getGlobalConfigByKey(key);
    }
}
exports.GlobalConfig = GlobalConfig;
