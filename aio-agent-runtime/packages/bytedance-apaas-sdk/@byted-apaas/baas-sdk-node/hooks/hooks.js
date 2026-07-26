"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.pre = void 0;
const api_1 = require("./api");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const tasks_1 = require("../tasks/tasks");
function pre(params, context, logger) {
    let prefixAPI = server_common_node_1.utils.getPrefixAPI();
    if (!prefixAPI) {
        return;
    }
    prefixAPI.split(',').forEach((v, _) => {
        if (!global[v]) {
            global[v] = {};
        }
        if (!global[v].mongodb) {
            global[v].mongodb = api_1.mongodb;
        }
        if (!global[v].redis) {
            global[v].redis = api_1.redis;
        }
        if (!global[v].oss) {
            global[v].oss = api_1.oss;
        }
        if (v === 'inspirecloud' || v === 'lark') {
            global[v].db = api_1.mongodb;
            global[v].file = api_1.oss;
        }
    });
    // 默认挂载 kunlun
    if (!global.kunlun.mongodb) {
        global.kunlun.mongodb = api_1.mongodb;
    }
    if (!global.kunlun.redis) {
        global.kunlun.redis = api_1.redis;
    }
    if (!global.kunlun.oss) {
        global.kunlun.oss = api_1.oss;
    }
    mountBaaS(context, logger);
}
exports.pre = pre;
function mountBaaS(context, logger) {
    if (!global.baas) {
        global.baas = {};
    }
    if (!global.baas.mongodb) {
        global.baas.mongodb = api_1.mongodb;
    }
    if (!global.baas.redis) {
        global.baas.redis = api_1.redis;
    }
    if (!global.baas.oss) {
        global.baas.oss = api_1.oss;
    }
    if (!global.baas.tasks) {
        global.baas.tasks = {};
    }
    global.baas.tasks = new tasks_1.Tasks((0, api_1.getFunctionSync)(context, logger));
}
