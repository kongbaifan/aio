"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.tool = exports.Tool = void 0;
const retry_1 = require("./retry");
const http_1 = require("./http");
const utils_1 = require("../../../utils/utils");
class Tool {
    retry(promiseFunc, options) {
        return Promise.resolve(retry_1.Retry.retryTool(promiseFunc, options));
    }
    async http(request) {
        return Promise.resolve(http_1.Http.httpTool(request));
    }
    setLaneName(laneName) {
        (0, utils_1.setXTTEnvOnlyDebug)(laneName);
    }
    async getTenantInfo() {
        return Promise.resolve(undefined);
    }
}
exports.Tool = Tool;
/**
 * 工具方法
 */
exports.tool = new Tool();
