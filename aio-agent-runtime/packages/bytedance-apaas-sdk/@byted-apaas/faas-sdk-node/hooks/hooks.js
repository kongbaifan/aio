"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.pre = void 0;
const tool_1 = require("../global/faas/tool/impl/tool");
const function_1 = require("../global/function/function");
function pre(params, context, logger) {
    if (!global.faas) {
        global.faas = {};
    }
    global.faas.tool = tool_1.tool;
    global.faas.function = (0, function_1.getFunctionSync)(context, logger);
    global.faas.microservice = function_1.invokeMicroservice;
}
exports.pre = pre;
