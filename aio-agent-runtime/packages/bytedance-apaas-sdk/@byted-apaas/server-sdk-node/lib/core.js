"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Application = exports.metaData = exports.workflow = exports.microservice = exports.cloudfunction = exports.tasks = exports.msg = exports.resources = exports.db = exports.kunlun = exports.isNewSystemProxyFunc = exports.hooks = void 0;
exports.hooks = require("../hooks/hooks");
exports.isNewSystemProxyFunc = true;
var kunlun_1 = require("../kunlun/kunlun");
Object.defineProperty(exports, "kunlun", { enumerable: true, get: function () { return kunlun_1.kunlun; } });
var api_1 = require("../hooks/api");
Object.defineProperty(exports, "db", { enumerable: true, get: function () { return api_1.db; } });
Object.defineProperty(exports, "resources", { enumerable: true, get: function () { return api_1.resources; } });
Object.defineProperty(exports, "msg", { enumerable: true, get: function () { return api_1.msg; } });
Object.defineProperty(exports, "tasks", { enumerable: true, get: function () { return api_1.tasks; } });
Object.defineProperty(exports, "cloudfunction", { enumerable: true, get: function () { return api_1.cloudfunction; } });
Object.defineProperty(exports, "microservice", { enumerable: true, get: function () { return api_1.microservice; } });
Object.defineProperty(exports, "workflow", { enumerable: true, get: function () { return api_1.workflow; } });
Object.defineProperty(exports, "metaData", { enumerable: true, get: function () { return api_1.metaData; } });
Object.defineProperty(exports, "Application", { enumerable: true, get: function () { return api_1.Application; } });
