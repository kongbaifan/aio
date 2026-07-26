"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FaaSInfraRequest = void 0;
const common = require("@byted-apaas/server-common-node");
const url_1 = require("url");
const commonFaasinfraHttpPath = common.http.faasinfraHttpPath;
const { InternalError } = common.exceptions;
const commonHttp = common.http;
const faasinfra = common.http.faasinfra;
const replaceKeys = common.http.replaceKeys;
const utils = common.utils;
class FaaSInfraRequest {
    async invokeMicroserviceSync(apiName, path, method, body) {
        const reqPath = commonFaasinfraHttpPath.invokeMicroserviceSync;
        const options = commonHttp.getOptions(null, reqPath);
        const urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        options.json = {
            'microserviceId': apiName,
            path,
            method,
            'query': parseQueryParams(path),
        };
        // 处理 body 参数
        if (method.toUpperCase() !== 'GET') {
            options.json.body = JSON.stringify(body);
        }
        return await faasinfra.doRequest(null, urlPath, options);
    }
    async invokeMicroserviceAsync(apiName, path, method, body) {
        const reqPath = commonFaasinfraHttpPath.invokeMicroserviceAsync;
        const options = commonHttp.getOptions(null, reqPath);
        const urlPath = options._reqPath.replace(replaceKeys.namespace, utils.getNamespaceFromCtx());
        options.json = {
            'microserviceId': apiName,
            path,
            method,
            'query': parseQueryParams(path),
        };
        // 处理 body 参数
        if (method.toUpperCase() !== 'GET') {
            options.json.body = JSON.stringify(body);
        }
        return await faasinfra.doRequest(null, urlPath, options);
    }
}
exports.FaaSInfraRequest = FaaSInfraRequest;
function parseQueryParams(path) {
    const params = {};
    const url = new url_1.URL(path, 'https://aa.bb.cc');
    for (const [k, v] of url.searchParams.entries()) {
        if (typeof (k) !== 'string') {
            throw new InternalError(`The type of k should be string, but ${typeof (k)}`);
        }
        if (typeof (v) !== 'string') {
            throw new InternalError(`The type of v should be string, but ${typeof (v)}`);
        }
        params[k] = v.split(',');
    }
    if (Object.keys(params).length === 0) {
        return undefined;
    }
    return params;
}
