"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports._Integration = exports._OpenSDKIntegration = void 0;
const common = require("@byted-apaas/server-common-node");
const common_1 = require("../../../application/impl/common");
const Request = require("../../../request/interface");
const exceptions = common.exceptions;
class _OpenSDKIntegration {
    constructor(appCtx) {
        this.appCtx = appCtx;
    }
    async getAppAccessToken(apiName) {
        if (!apiName) {
            throw new exceptions.InvalidParamError(`apiName is null`);
        }
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().getIntegrationAppAccessToken(apiName);
        });
    }
    async getDefaultAppAccessToken() {
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().getDefaultIntegrationAppAccessToken();
        });
    }
    async getDefaultTenantAccessToken() {
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().getDefaultIntegrationTenantAccessToken();
        });
    }
    async getTenantAccessToken(apiName) {
        if (!apiName) {
            throw new exceptions.InvalidParamError(`apiName is null`);
        }
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().getIntegrationTenantAccessToken(apiName);
        });
    }
}
exports._OpenSDKIntegration = _OpenSDKIntegration;
class _Integration {
    async getAppAccessToken(apiName) {
        if (!apiName) {
            throw new exceptions.InvalidParamError(`apiName is null`);
        }
        return await Request.GetInstance().getIntegrationAppAccessToken(apiName);
    }
    async getDefaultAppAccessToken() {
        return await Request.GetInstance().getDefaultIntegrationAppAccessToken();
    }
    async getDefaultTenantAccessToken() {
        return await Request.GetInstance().getDefaultIntegrationTenantAccessToken();
    }
    async getTenantAccessToken(apiName) {
        if (!apiName) {
            throw new exceptions.InvalidParamError(`apiName is null`);
        }
        return await Request.GetInstance().getIntegrationTenantAccessToken(apiName);
    }
}
exports._Integration = _Integration;
