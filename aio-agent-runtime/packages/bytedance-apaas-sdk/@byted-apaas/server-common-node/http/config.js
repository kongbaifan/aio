"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getAuthorization = exports.getBaseUrl = exports.concatHost = exports.getFaasinfraHostAndToken = exports.setFaasinfraHostAndToken = exports.getOpenapiHostAndToken = exports.setOpenapiHostAndToken = exports.initHttpConf = exports.PatchHttpConfig = exports.DeleteHttpConfig = exports.PostHttpConfig = exports.PutHttpConfig = exports.GetHttpConfig = exports.HttpConfig = exports.getAuthorizationV2 = exports.setTempUseLGW = void 0;
const nodeClsCtx_1 = require("../utils/nodeClsCtx");
function getUtils() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../utils/utils');
}
function getExceptions() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../utils/exceptions');
}
function getConstant() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../constants/constants');
}
function getOpenapi() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./openapi');
}
function getFaasinfra() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./faasinfra');
}
function getCredential() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../credential/credential').getCredential;
}
// 存储tcc配置的超时时间
let apiTimeoutFromTcc = null;
// openapi 相关配置
let openapiConf = {
    host: '',
    authorization: '',
};
// faasinfra 相关配置
let faasinfraConf = {
    host: '',
    authorization: '',
};
// 内网域名不能带到外网，全部从 env 中获取
// openapiEnv2config innerapi 内外域名
const innerapiEnv2config = {
    staging_boe: {
        host_external: '',
    },
    staging: {
        host_external: 'https://apaas-innerapi-lr.feishu-pre.cn',
    },
    gray: {
        host_external: 'https://apaas-innerapi.feishu-pre.cn',
    },
    online: {
        host_external: 'https://apaas-innerapi.feishu.cn',
    },
    staging_boei18n: {
        host_external: '',
    },
    online_my: {
        host_external: 'https://apaas-innerapi-my.byteintl.net',
    },
    online_sg: {
        host_external: 'https://apaas-innerapi-my.byteintl.net',
    },
};
// openapiEnv2config openapi 内外域名
const openapiEnv2config = {
    staging_boe: {
        host_external: '',
    },
    staging: {
        host_external: 'https://oapi-kunlun-staging.bytedance.com',
    },
    gray: {
        host_external: 'https://oapi-kunlun-gray.kundou.cn',
    },
    online: {
        host_external: 'https://oapi-kunlun.kundou.cn',
    },
    staging_boei18n: {
        host_external: '',
    },
    online_my: {
        host_external: 'https://oapi-kunlun-my.byteintl.net',
    },
    online_sg: {
        host_external: 'https://apaas-innerapi-my.byteintl.net',
    },
};
const faasinfraEnv2config = {
    staging_boe: {
        host_external: '',
    },
    staging: {
        host_external: 'https://apaas-faasinfra-staging.bytedance.com',
    },
    gray: {
        host_external: 'https://apaas-faasinfra-gray.kundou.cn',
    },
    online: {
        host_external: 'https://apaas-faasinfra.kundou.cn',
    },
    staging_boei18n: {
        host_external: '',
    },
    online_my: {
        host_external: 'https://apaas-faasinfra-my.byteintl.net',
    },
    online_sg: {
        host_external: 'https://apaas-innerapi-my.byteintl.net',
    },
};
class HttpConfig {
    /**
     * @param method                请求方法
     * @param path                  请求path
     * @param reqTimeoutTccKey      请求超时时间的 tcc key
     * @param reqTimeout            请求超时时间，默认值12s
     * @param connTimeout           连接超时时间，默认值2s
     * @param secureConnTimeout     TLS 连接超时时间，默认值1s
     */
    constructor(method, path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000, secureConnTimeout = 1000) {
        this.method = method;
        this.path = path;
        this.reqTimeout = reqTimeout;
        this.reqTimeoutTccKey = reqTimeoutTccKey;
        this.connTimeout = connTimeout;
        this.connTimeoutTccKey = 'http_connect_timeout';
        this.secureConnTimeout = secureConnTimeout;
        this.secureConnTimeoutTccKey = 'http_secure_connect_timeout';
    }
    /**
     * 获取请求超时时间
     *
     * @returns {number|*}
     */
    getReqTimeout() {
        const apiTimeoutFromTcc = getTimeoutMap(this.reqTimeoutTccKey);
        if (apiTimeoutFromTcc && apiTimeoutFromTcc[this.reqTimeoutTccKey]) {
            return apiTimeoutFromTcc[this.reqTimeoutTccKey];
        }
        return this.reqTimeout;
    }
    /**
     * 获取连接超时时间
     *
     * @returns {number|*}
     */
    getConnTimeout() {
        const apiTimeoutFromTcc = getTimeoutMap(this.connTimeoutTccKey);
        if (apiTimeoutFromTcc && apiTimeoutFromTcc[this.connTimeoutTccKey]) {
            return apiTimeoutFromTcc[this.connTimeoutTccKey];
        }
        return this.connTimeout;
    }
    /**
     * 获取TLS连接超时时间
     *
     * @returns {number|*}
     */
    getSecureConnTimeout() {
        let timeouts = getTimeoutMap(this.secureConnTimeoutTccKey);
        if (timeouts && timeouts[this.secureConnTimeoutTccKey]) {
            return timeouts[this.secureConnTimeoutTccKey];
        }
        return this.secureConnTimeout;
    }
    /**
     * 获取请求的服务，如 openapi 或 faasinfra
     *
     * @returns {*}
     */
    getReqServer() {
        return this.reqTimeoutTccKey.split('_')[0];
    }
    /**
     * 获取请求方法
     *
     * @returns {*}
     */
    getReqMethod() {
        return this.reqTimeoutTccKey.split('_')[1];
    }
}
exports.HttpConfig = HttpConfig;
function getTimeoutMap(key) {
    const tccMap = getUtils().getApiTimeoutFromTcc();
    if (tccMap && tccMap[key]) {
        return tccMap;
    }
    return getConstant().ApiTimeoutDefaultMap;
}
class GetHttpConfig extends HttpConfig {
    constructor(path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000) {
        super('GET', path, reqTimeoutTccKey, reqTimeout, connTimeout);
    }
}
exports.GetHttpConfig = GetHttpConfig;
class PostHttpConfig extends HttpConfig {
    constructor(path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000) {
        super('POST', path, reqTimeoutTccKey, reqTimeout, connTimeout);
    }
}
exports.PostHttpConfig = PostHttpConfig;
class PutHttpConfig extends HttpConfig {
    constructor(path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000) {
        super('PUT', path, reqTimeoutTccKey, reqTimeout, connTimeout);
    }
}
exports.PutHttpConfig = PutHttpConfig;
class DeleteHttpConfig extends HttpConfig {
    constructor(path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000) {
        super('DELETE', path, reqTimeoutTccKey, reqTimeout, connTimeout);
    }
}
exports.DeleteHttpConfig = DeleteHttpConfig;
class PatchHttpConfig extends HttpConfig {
    constructor(path, reqTimeoutTccKey, reqTimeout = 12000, connTimeout = 2000) {
        super('PATCH', path, reqTimeoutTccKey, reqTimeout, connTimeout);
    }
}
exports.PatchHttpConfig = PatchHttpConfig;
function setTempUseLGW() {
    (0, nodeClsCtx_1.getReqCtx)()._temp_use_agw = "true";
}
exports.setTempUseLGW = setTempUseLGW;
function getOpenapiHost() {
    const domain = process.env.KOpenApiDomain;
    if (domain) {
        return domain;
    }
    return openapiEnv2config[getUtils().getEnvWithBoe()].host_external;
}
/**
 * 从 env 里获取，外网版域名用来兜底
 */
function getInnerAPIHost() {
    const domain = process.env.KInnerAPIDomain;
    if (domain) {
        return domain;
    }
    return innerapiEnv2config[getUtils().getEnvWithBoe()].host_external;
}
/**
 * 从 env 里获取，外网版域名用来兜底
 */
function getFaasinfraHost() {
    const domain = process.env.KFaaSInfraDomain;
    if (domain) {
        return domain;
    }
    return faasinfraEnv2config[getUtils().getEnvWithBoe()].host_external;
}
/**
 * @deprecated
 */
function setOpenapiConf() {
    openapiConf.authorization = getUtils().getOpenapiToken();
    openapiConf.host = getOpenapiHost();
}
/**
 * @deprecated
 */
function setFaasinfraConf() {
    faasinfraConf.authorization = getUtils().getFaasinfraToken();
    faasinfraConf.host = getFaasinfraHost();
}
/**
 * @deprecated
 * @param apiTimeout
 */
function setApiTimeoutFromTcc(apiTimeout) {
    apiTimeoutFromTcc = apiTimeout;
}
function concatHost(server, path) {
    if (!getUtils().isKunlunOrg() || getUtils().isMicroservice()) {
        if (server === 'openapi') {
            return getUtils().getOpenapiDomain() + path;
        }
        else if (server === 'faasinfra') {
            return getUtils().getFaasinfraDomain() + path;
        }
        throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
    }
    if (server === 'openapi') {
        return getOpenapiHost() + path;
    }
    else if (server === 'faasinfra') {
        return getFaasinfraHost() + path;
    }
    throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
}
exports.concatHost = concatHost;
function getBaseUrl(server) {
    if (!getUtils().isKunlunOrg() || getUtils().isMicroservice()) {
        if (server === 'openapi') {
            return getUtils().getOpenapiDomain();
        }
        else if (server === 'faasinfra') {
            return getUtils().getFaasinfraDomain();
        }
        throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
    }
    if (server === 'openapi') {
        return getOpenapiHost();
    }
    else if (server === 'faasinfra') {
        return getFaasinfraHost();
    }
    throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
}
exports.getBaseUrl = getBaseUrl;
async function getAuthorizationV2(server) {
    if (!getUtils().isKunlunOrg()) {
        return await getFaasinfra().getServiceToken();
    }
    if (getUtils().isMicroservice()) {
        return await getOpenapi().getAppToken();
    }
    else if (getUtils().isOnlineDev()) {
        return getPlatformAuthorization(server);
    }
    else {
        return await getCredential()().getToken();
    }
}
exports.getAuthorizationV2 = getAuthorizationV2;
function getPlatformAuthorization(server) {
    if (server === 'openapi') {
        return getUtils().getOpenapiToken();
    }
    else if (server === 'faasinfra') {
        return getUtils().getFaasinfraToken();
    }
    throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
}
/**
 * @deprecated
 * @param server
 */
function getAuthorization(server) {
    if (server === 'openapi') {
        if (!openapiConf || !openapiConf.authorization) {
            throw new (getExceptions()).InternalError('openapiConf.authorization is empty');
        }
        return openapiConf.authorization;
    }
    else if (server === 'faasinfra') {
        if (!faasinfraConf || !faasinfraConf.authorization) {
            throw new (getExceptions()).InternalError('faasinfraConf.authorization is empty');
        }
        return faasinfraConf.authorization;
    }
    throw new (getExceptions()).InternalError(`server (${server}) not in [openapi, faasinfra]`);
}
exports.getAuthorization = getAuthorization;
/**
 * @deprecated
 */
function setOpenapiHostAndToken(host, authorization) {
    openapiConf.host = host;
    openapiConf.authorization = authorization;
}
exports.setOpenapiHostAndToken = setOpenapiHostAndToken;
/**
 * @deprecated
 */
function getOpenapiHostAndToken() {
    return { host: getOpenapiHost(), authorization: getUtils().getOpenapiToken() };
}
exports.getOpenapiHostAndToken = getOpenapiHostAndToken;
/**
 * @deprecated
 */
function setFaasinfraHostAndToken(host, authorization) {
    faasinfraConf.host = host;
    faasinfraConf.authorization = authorization;
}
exports.setFaasinfraHostAndToken = setFaasinfraHostAndToken;
/**
 * @deprecated
 */
function getFaasinfraHostAndToken() {
    return { host: getFaasinfraHost(), authorization: getUtils().getFaasinfraToken() };
}
exports.getFaasinfraHostAndToken = getFaasinfraHostAndToken;
/**
 * @deprecated
 */
function initHttpConf() {
    setOpenapiConf();
    setFaasinfraConf();
    setApiTimeoutFromTcc(getUtils().getApiTimeoutFromTcc());
}
exports.initHttpConf = initHttpConf;
