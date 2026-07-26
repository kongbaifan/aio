"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getTokenWithCache = exports.doRequestWithConnRetry = exports.dealOptionForLane = exports.dealOptionForENV = exports.getTokenOptions = exports.getOptions = exports.HttpOptions = void 0;
const config_1 = require("./config");
const config = require("./config");
const utils = require("../utils/utils");
const constants_1 = require("../constants/constants");
const constants_2 = require("./constants");
const rate_limit_1 = require("./rate_limit");
const nodeClsCtx = require("../utils/nodeClsCtx");
const utils_1 = require("../utils/utils");
const pressure_1 = require("./pressure");
const got = require('got');
const http = require('http');
const https = require('https');
const exceptions_1 = require("../utils/exceptions");
const logger_1 = require("../utils/logger");
const httpAgentConfig = {
    keepAlive: true,
    keepAliveMsecs: 10000,
    maxSockets: 100,
    maxTotalSockets: 500,
    maxFreeSockets: 20,
};
const httpAgent = new http.Agent({
    keepAlive: httpAgentConfig.keepAlive,
    keepAliveMsecs: httpAgentConfig.keepAliveMsecs,
    maxSockets: httpAgentConfig.maxSockets,
    maxTotalSockets: httpAgentConfig.maxTotalSockets,
    maxFreeSockets: httpAgentConfig.maxFreeSockets,
});
const httpsAgent = new https.Agent({
    keepAlive: httpAgentConfig.keepAlive,
    keepAliveMsecs: httpAgentConfig.keepAliveMsecs,
    maxSockets: httpAgentConfig.maxSockets,
    maxTotalSockets: httpAgentConfig.maxTotalSockets,
    maxFreeSockets: httpAgentConfig.maxFreeSockets,
});
class HttpOptions {
    constructor(method, timeout, agent, headers, reqPath, reqServer, reqMethod, retry = 0) {
        this.method = method;
        this.timeout = timeout;
        this.agent = agent;
        this.headers = headers;
        this._reqPath = reqPath;
        this._reqServer = reqServer;
        this._reqMethod = reqMethod;
        this.retry = retry;
        this._skipPreIntercept = false;
    }
}
exports.HttpOptions = HttpOptions;
function getOptions(ctx, httpConfig) {
    return new HttpOptions(httpConfig.method, {
        'connect': httpConfig.getConnTimeout(),
        'secureConnect': httpConfig.getSecureConnTimeout(),
        'request': httpConfig.getReqTimeout(),
    }, {
        http: httpAgent,
        https: httpsAgent
    }, {
        'Tenant': utils.getTenantNameFromCtx(),
        // 'Authorization': config.getAuthorization(httpConfig.getReqServer()),
        'User': -1,
        'x-tt-logid': utils.getLogID(),
        'x-kunlun-logid': utils.getLogID(),
        'Kldx-Version': '4.0.0',
        ...utils.getTraceHeader(),
    }, httpConfig.path, httpConfig.getReqServer(), httpConfig.getReqMethod());
}
exports.getOptions = getOptions;
function getTokenOptions(ctx, httpConfig) {
    return new HttpOptions(httpConfig.method, {
        'connect': httpConfig.getConnTimeout(),
        'secureConnect': httpConfig.getSecureConnTimeout(),
        'request': httpConfig.getReqTimeout(),
    }, {
        http: httpAgent,
        https: httpsAgent
    }, {
        'x-tt-logid': utils.getLogID(),
        'x-kunlun-logid': utils.getLogID(),
        'Kldx-Version': '4.0.0',
        ...utils.getTraceHeader(),
    }, httpConfig.path, httpConfig.getReqServer(), httpConfig.getReqMethod());
}
exports.getTokenOptions = getTokenOptions;
function dealOptionForENV(options) {
    let key = constants_1.headers.envKey;
    let envKey = nodeClsCtx.getEnvKey();
    if (envKey && envKey.startsWith('boe_')) {
        if (!options.headers) {
            options.headers = {};
        }
        options.headers[constants_1.headers.useKeyForBOE] = 1;
        options.headers[key] = envKey;
    }
    if (envKey && envKey.startsWith('ppe_')) {
        if (!options.headers) {
            options.headers = {};
        }
        options.headers[constants_1.headers.useKeyForPPE] = 1;
        options.headers[key] = envKey;
    }
}
exports.dealOptionForENV = dealOptionForENV;
function dealOptionForLane(options) {
    let key = constants_1.headers.laneHttpHeader;
    let laneKey = nodeClsCtx.getLaneKey();
    if (laneKey) {
        options.headers[key] = laneKey;
    }
}
exports.dealOptionForLane = dealOptionForLane;
const serverMap = {
    'openapi': 0,
    'faasinfra': 0,
};
const getAuthTokenPath = ['/auth/v1/appToken', '/auth/v1/service/token'];
async function doRequestWithConnRetry(path, options, connRetryTimes = 2) {
    const rateLimitFromHeader = utils.getRateLimitFromHeader();
    const oldRateLimit = rate_limit_1.limiter.getMaxRequest();
    if (rate_limit_1.limiter.resetRateLimiter(rateLimitFromHeader)) {
        // 重置限流
        utils.printInfoLog(`time: ${Date.now()};pid: ${process.pid};reset rateLimit, oldRateLimit: ${oldRateLimit}, newRateLimit: ${rateLimitFromHeader};`);
    }
    if (!options._skipPreIntercept && !rate_limit_1.limiter.allowRequest()) {
        // 上报日志告警 使用特定结构，faasinfra 即可识别并告警
        const logger = new logger_1.Logger();
        logger.setLogType(constants_1.RATE_LIMIT_LOG_TYPE);
        logger.warn(`request limit exceeded quota, maxRequest: ${rate_limit_1.limiter.getMaxRequest()}`);
        const downgradeValue = utils.getRateLimitDowngradeFromHeader();
        utils.printInfoLog(`rate limit info, maxRequest: ${rate_limit_1.limiter.getMaxRequest()}; with req len: ${rate_limit_1.limiter.getReqLength()} and downgrade value: ${downgradeValue} (${typeof downgradeValue})`);
        if (downgradeValue === 'false') {
            utils.fail(options, Date.now());
            throw new exceptions_1.InternalError(`rate limit over error, maxRequest: ${rate_limit_1.limiter.getMaxRequest()}; req len: ${rate_limit_1.limiter.getReqLength()}; downgrade value: ${downgradeValue}`);
        }
    }
    if (!options._skipPreIntercept && !getAuthTokenPath.includes(path) && nodeClsCtx.getPressureNeedDecelerate()) {
        // 反压中心 降速
        // getPressureDecelerator前需要调用initPressureDecelerator初始化
        const key = nodeClsCtx.getAPaaSPersistFaaSPressureSignalId();
        const sleeptime = await (0, pressure_1.getPressureDecelerator)()?.getSleeptime(key) || 0;
        if (sleeptime > 0) {
            const logger = new logger_1.Logger(); // 降速日志
            logger.setLogType(constants_1.SPEED_DOWN_LOG_TYPE);
            const msg = {
                key, sleep_time: sleeptime,
            };
            const msgStr = JSON.stringify(msg);
            logger.warn(msgStr);
            await utils.sleepMs(sleeptime);
        }
    }
    (0, utils_1.addLaneIDToHeader)(options);
    (0, utils_1.addEnvIDToHeader)(options);
    (0, utils_1.addFunctionAPIIDToHeader)(options);
    (0, utils_1.addEnvTypeToHeader)(options);
    dealOptionForENV(options);
    dealOptionForLane(options);
    // 持久化请求头全链路透传递
    utils.addPersistAPaaSValuetoHeader(options);
    if (path !== '/auth/v1/appToken' && path !== '/auth/v1/service/token') {
        options.headers.Authorization = await (0, config_1.getAuthorizationV2)(options._reqServer);
    }
    let times = 0, beginReqTime = 0;
    const logId = utils.getLogID();
    const url = config.concatHost(options._reqServer, path);
    const baseUrl = config.getBaseUrl(options._reqServer);
    const serverInfo = utils.getServerInfo(options._reqServer);
    let withAgent = true, tmpErr = new exceptions_1.InternalError(`Request failed with status code 502`);
    do {
        const opt = { ...options };
        if (utils.getFaasType() == constants_1.faaSAccessType.ByteFaaSExternalAccessType && process.env.KSDKIPVersion === String(constants_1.IPVersion.V6)) {
            opt.family = constants_1.IPVersion.V6;
        }
        let bodyLog = '';
        try {
            bodyLog = JSON.stringify(opt.json);
            if (bodyLog !== undefined && bodyLog.length > 10000) {
                bodyLog = bodyLog.slice(0, 10000);
            }
        }
        catch (e) {
            utils.printErrorLog(`parse body error, err: ${e}`);
        }
        try {
            let resp;
            beginReqTime = new Date().getTime();
            if (utils.enableMesh() && serverInfo.psm && serverInfo.cluster) {
                utils.printInfoLog(`request begin [mesh], logId: ${logId}, withAgent:${withAgent}, timestamp: ${beginReqTime}, url: ${url}, timeout: ${JSON.stringify(opt.timeout)}, headers: ${JSON.stringify(options.headers)}, body: ${bodyLog}`);
                resp = await tranRespGotMeshToAxios(serverInfo, path, opt, beginReqTime);
                let meshFlag = '';
                if (resp && resp.headers) {
                    meshFlag = (resp.headers[constants_1.headers.EnvoyRespFlag]) || '';
                }
                let endReqTime = new Date().getTime();
                utils.printInfoLog(`request end [mesh], meshFlag: ${meshFlag}, logId: ${logId}, withAgent:${withAgent}, beginReqTime: ${beginReqTime}, endReqTime: ${endReqTime}, cost: ${endReqTime - beginReqTime}, url: ${url}`);
            }
            else {
                incrementServerRequest(options._reqServer);
                utils.printInfoLog(`request begin, logId: ${logId}, withAgent:${withAgent}, timestamp: ${beginReqTime}, url: ${url}, timeout: ${JSON.stringify(opt.timeout)}, headers: ${JSON.stringify(options.headers)}, body: ${bodyLog}, serverMap: ${serverMap}`);
                resp = await tranRespGotToAxios(url, opt, beginReqTime);
                decrementServerRequest(options._reqServer);
                let endReqTime = new Date().getTime();
                utils.printInfoLog(`request end, logId: ${logId}, withAgent:${withAgent}, beginReqTime: ${beginReqTime}, endReqTime: ${endReqTime}, cost: ${endReqTime - beginReqTime}, url: ${url}, serverMap: ${serverMap}`);
            }
            return [resp, beginReqTime];
        }
        catch (err) {
            decrementServerRequest(options._reqServer);
            if (err.message && err.message.includes('Request failed with status code 502')) {
                withAgent = false;
                tmpErr = err;
                continue;
            }
            let optStr = '';
            try {
                optStr = JSON.stringify(opt);
            }
            catch (e) {
                utils.printErrorLog(`parse option error, err: ${e}`);
            }
            let endReqTime = new Date().getTime();
            utils.printErrorLog(`request end, logId: ${logId}, withAgent:${withAgent}, beginReqTime: ${beginReqTime}, endReqTime: ${endReqTime}, cost: ${endReqTime - beginReqTime}, url: ${baseUrl}, err: ${err.stack}, option: ${optStr}, serverMap: ${serverMap}`);
            if (times >= connRetryTimes || !utils.isHttpConnectError(err)) {
                utils.fail(opt, beginReqTime);
                throw err;
            }
        }
    } while (times++ < connRetryTimes);
    if (!withAgent) {
        throw tmpErr;
    }
}
exports.doRequestWithConnRetry = doRequestWithConnRetry;
function incrementServerRequest(server) {
    if (server === 'openapi') {
        serverMap.openapi++;
    }
    else if (server === 'faasinfra') {
        serverMap.faasinfra++;
    }
}
function decrementServerRequest(server) {
    if (server === 'openapi') {
        serverMap.openapi--;
    }
    else if (server === 'faasinfra') {
        serverMap.faasinfra--;
    }
}
async function tranRespGotToAxios(url, opt, beginReqTime) {
    let resp = await got(url, opt);
    let body = resp.body;
    if (!url.includes('/attachment/v1/download') && !url.includes('/api/attachment/v1/files/') && !url.includes('/attachment/v1/images/')) {
        try {
            body = JSON.parse(resp.body);
        }
        catch (e) {
            utils.fail(opt, beginReqTime);
            throw new exceptions_1.UnmarshalError(e);
        }
    }
    resp.status = resp.statusCode;
    resp.data = body;
    return resp;
}
async function tranRespGotMeshToAxios(serverInfo, path, opt, beginReqTime) {
    let socketAddr = utils.getSocketAddr();
    const url = `http://unix:${socketAddr}:${path}`;
    // 开启 unix domain socket 通信
    opt.enableUnixSockets = true;
    // mesh 要求不包含 scheme 前缀
    opt.headers['destination-service'] = serverInfo.psm;
    opt.headers['destination-cluster'] = serverInfo.cluster;
    opt.headers['destination-request-timeout'] = (0, utils_1.getMeshDestReqTimeout)();
    const resp = await got(url, opt);
    let body = resp.body;
    if (!url.includes('/attachment/v1/download') && !url.includes('/api/attachment/v1/files/') && !url.includes('/attachment/v1/images/')) {
        try {
            body = JSON.parse(resp.body);
        }
        catch (e) {
            utils.fail(opt, beginReqTime);
            throw new exceptions_1.UnmarshalError(e);
        }
    }
    resp.status = resp.statusCode;
    resp.data = body;
    return resp;
}
function getRefreshIntervalByType(typ) {
    return typ + constants_2.tokenRefreshIntervalKey;
}
async function getTokenWithCache(doRequestPromise, tokenTypeKey, httpConfig, bodyJson) {
    if (!(constants_2.tokenCacheMap[tokenTypeKey].accessToken) || !(constants_2.tokenCacheMap[tokenTypeKey].expireTime) ||
        ((constants_2.tokenCacheMap[tokenTypeKey].expireTime - Date.now()) < constants_2.tokenCacheMap[getRefreshIntervalByType(tokenTypeKey)])) {
        let options = getTokenOptions(null, httpConfig);
        options.json = bodyJson;
        constants_2.tokenCacheMap[tokenTypeKey] = await doRequestPromise(null, options._reqPath, options);
    }
    return constants_2.tokenCacheMap[tokenTypeKey].accessToken;
}
exports.getTokenWithCache = getTokenWithCache;
