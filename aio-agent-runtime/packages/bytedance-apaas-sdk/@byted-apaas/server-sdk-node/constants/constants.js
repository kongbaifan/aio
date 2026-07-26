"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.triggerType = exports.httpStatusCodes = exports.httpHeaderKeys = exports.notifyModel = void 0;
exports.notifyModel = {
    key: 'ee.kunlun.cloudfunction.faas_buildin',
};
exports.httpHeaderKeys = {
    statusCode: 'X-Kunlun-Status-Code',
    location: 'Location',
};
exports.httpStatusCodes = {
    redirect: 302,
};
exports.triggerType = {
    defaultTrigger: 'default-trigger',
};
