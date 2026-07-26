"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.tool = exports.hooks = exports.globalVar = exports.oss = exports.redis = exports.mongodb = void 0;
var api_1 = require("../hooks/api");
Object.defineProperty(exports, "mongodb", { enumerable: true, get: function () { return api_1.mongodb; } });
Object.defineProperty(exports, "redis", { enumerable: true, get: function () { return api_1.redis; } });
Object.defineProperty(exports, "oss", { enumerable: true, get: function () { return api_1.oss; } });
Object.defineProperty(exports, "globalVar", { enumerable: true, get: function () { return api_1.globalVar; } });
exports.hooks = require("../hooks/hooks");
const server_common_node_1 = require("@byted-apaas/server-common-node");
exports.tool = server_common_node_1.tool;
