"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.GetFaaSInfraInstance = exports.GetInstance = exports.GetHttpInstance = void 0;
const openapi_1 = require("./openapi");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const faasinfra_1 = require("./faasinfra");
const version_1 = require("../version/version");
const requestInstanceMap = {
    'httpRequest': null,
    'rpcRequest': null,
};
function GetHttpInstance() {
    if (!requestInstanceMap.httpRequest) {
        requestInstanceMap.httpRequest = new openapi_1.RequestHttp();
        // 设置 SDK 版本信息到请求上下文，用于埋点上报
        server_common_node_1.utils.setSDKInfo(version_1.SDKName, version_1.SDKVersion);
    }
    return requestInstanceMap.httpRequest;
}
exports.GetHttpInstance = GetHttpInstance;
function GetInstance() {
    return GetHttpInstance();
}
exports.GetInstance = GetInstance;
function GetFaaSInfraInstance() {
    return new faasinfra_1.FaaSInfraRequest();
}
exports.GetFaaSInfraInstance = GetFaaSInfraInstance;
