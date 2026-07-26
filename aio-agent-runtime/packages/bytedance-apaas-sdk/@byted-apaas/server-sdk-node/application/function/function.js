"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Function = void 0;
const interface_1 = require("../../request/interface");
const common_1 = require("../impl/common");
class Function {
    constructor(appCtx, apiName) {
        this.appCtx = appCtx;
        this.apiName = apiName;
    }
    async invoke(params) {
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await (0, interface_1.GetInstance)().invokeFuncWithAuth({
                APIName: this.apiName,
                isInvokeByAPIName: true
            }, params);
        });
    }
}
exports.Function = Function;
