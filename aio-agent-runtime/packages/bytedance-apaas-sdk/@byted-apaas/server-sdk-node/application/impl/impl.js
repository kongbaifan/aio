"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Application = void 0;
const credential_1 = require("@byted-apaas/server-common-node/credential/credential");
const db_1 = require("../../context/db/impl/db");
const tool_1 = require("@byted-apaas/server-common-node/kunlun/tool/impl/tool");
const function_1 = require("../function/function");
const common_1 = require("../../request/common");
const resources_1 = require("../../context/resources/impl/resources");
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const integration_1 = require("../../context/integration/impl/integration");
class Application {
    constructor(clientID, clientSecret) {
        this.appCtx = {
            mode: 'openSDK',
            credential: new credential_1.AppCredential(clientID, clientSecret),
            debugType: constants_1.DefaultDebugType ? constants_1.DefaultDebugType : '2',
            env: 'online',
        };
        this.data = new db_1.ApplicationDB(this.appCtx);
        this.resources = new resources_1._OpenSDKResources(this.appCtx);
        this.integration = new integration_1._OpenSDKIntegration(this.appCtx);
        this.tools = new tool_1.Tool();
        this.tools.getTenantInfo = async () => {
            return await (0, common_1.getTenantInfo)(this.appCtx);
        };
    }
    cloudfunction(funcName) {
        return new function_1.Function(this.appCtx, funcName);
    }
    env(platformEnvType) {
        this.appCtx.env = platformEnvType;
        return this;
    }
    // 设置本地调试模式
    localDebugMode() {
        this.appCtx.debugType = '2';
        return this;
    }
    setLaneName(laneName) {
        this.appCtx.x_tt_env = laneName;
        return this;
    }
}
exports.Application = Application;
