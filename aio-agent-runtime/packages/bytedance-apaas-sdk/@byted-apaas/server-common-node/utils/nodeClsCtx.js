"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.isCloseIntranetDomain = exports.getFaasType = exports.getFaasinfraToken = exports.getOpenapiToken = exports.getTriggerTaskIDStr = exports.getTriggerTaskID = exports.isAsync = exports.setInvokeFuncName = exports.getInvokeFuncName = exports.getTriggerTime = exports.getServiceID = exports.getFunctionsVersion = exports.getDebugCode = exports.isOnlineDebug = exports.isLocalDebug = exports.isDebug = exports.getDistributedHandleMask = exports.getRetryTimesFromTcc = exports.getApiTimeoutFromTcc = exports.getDeployedGlobalFuncMap = exports.getDeployedGlobalFuncNames = exports.getTriggerType = exports.getSource = exports.getLoggerInfo = exports.getFunctionAPIID = exports.getExecuteID = exports.getRateLimitDowngradeFromHeader = exports.getRateLimitFromHeader = exports.getLogID = exports.getFlowVersion = exports.setFlowVersion = exports.setEnvKey = exports.setLogID = exports.setDebugType = exports.getLaneKey = exports.getEnvKey = exports.getEnv = exports.setEnv = exports.getBoe = exports.setBoe = exports.mockUserID = exports.getUser = exports.setTenant = exports.getEvent = exports.getApp = exports.getTenant = exports.add = exports.addObject = exports.getDynCtx = exports.getReqCtx = void 0;
exports.getPressureConfig = exports.getPressureNeedDecelerate = exports.getAPaaSPersistFaaSPressureSignalId = exports.setSDKInfo = exports.getSDKTransientConf = exports.getSDKConf = exports.getFuncAPIName = exports.getFuncMetaConf = exports.setUnauthFieldMap = exports.getUnauthFieldMap = exports.getHttpHeaders = exports.getEnvType = exports.getEnvID = exports.getLaneID = exports.getModeForOpenSDK = exports.addModeForOpenSDK = exports.getPlatformEnvTypeForOpenSDK = exports.addPlatformEnvTypeForOpenSDK = exports.getOpenSDKKeys = exports.getCredential = exports.addCredential = exports.getRequireFunc = exports.setHttpHeaders = exports.getGlobalVariables = exports.getLoopMasks = exports.addMetrics = exports.getMetrics = exports.getFuncLabel = exports.getFuncVersionID = exports.getInstanceID = exports.getObjectLabel = exports.getSourceLabel = exports.getSourceID = exports.getHttpMethod = void 0;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const constants_1 = require("../constants/constants");
const user_1 = require("../context/user");
const logid_1 = require("./logid");
function getUtils() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./utils');
}
var NodeClsKeys;
(function (NodeClsKeys) {
    NodeClsKeys["REQ_CTX"] = "x-kunlun-request-context";
    NodeClsKeys["DYN_CTX"] = "x-kunlun-dynamic-context";
    NodeClsKeys["Org_CTX"] = "x-apaas-node-cls";
})(NodeClsKeys || (NodeClsKeys = {}));
/**
 * 静态请求上下文
 */
function getReqCtx() {
    let key = NodeClsKeys.REQ_CTX;
    if (!getUtils().isKunlunOrg()) {
        key = NodeClsKeys.Org_CTX;
    }
    let reqCtx = nodeCls.get(key);
    if (!reqCtx) {
        reqCtx = nodeCls.create(key);
    }
    return reqCtx;
}
exports.getReqCtx = getReqCtx;
/**
 * 动态请求上下文
 */
function getDynCtx() {
    let dynCtx = nodeCls.get(NodeClsKeys.DYN_CTX);
    if (!dynCtx) {
        dynCtx = nodeCls.create(NodeClsKeys.DYN_CTX);
    }
    return dynCtx;
}
exports.getDynCtx = getDynCtx;
/**
 * 批量添加请求上下文
 * @param params
 */
function addObject(params) {
    for (let key in params) {
        if (params.hasOwnProperty(key)) {
            add(key, params[key]);
        }
    }
}
exports.addObject = addObject;
/**
 * 添加请求上下文
 * @param key
 * @param value
 */
function add(key, value) {
    const reqCtx = getReqCtx();
    reqCtx[key] = value;
}
exports.add = add;
function getTenant() {
    const reqCtx = getReqCtx();
    return reqCtx.tenant;
}
exports.getTenant = getTenant;
function getApp() {
    const reqCtx = getReqCtx();
    return reqCtx.app;
}
exports.getApp = getApp;
function getEvent() {
    const reqCtx = getReqCtx();
    return reqCtx.event;
}
exports.getEvent = getEvent;
function setTenant(tenant) {
    add('tenant', tenant);
}
exports.setTenant = setTenant;
function getUser() {
    const reqCtx = getReqCtx();
    if (reqCtx.user && reqCtx.user._id) {
        return new user_1.User(reqCtx.user._id, reqCtx.user.initiator._locale);
    }
    return new user_1.User(-1, { language: 'zh_CN', timezone: { location: 'Asia/Shanghai', offset: 'GMT+0800' } });
}
exports.getUser = getUser;
function mockUserID(userID) {
    const reqCtx = getReqCtx();
    reqCtx.user = new user_1.User(userID, { language: 'zh_CN', timezone: { location: 'Asia/Shanghai', offset: 'GMT+0800' } });
}
exports.mockUserID = mockUserID;
function setBoe(boe) {
    add('boe', boe);
}
exports.setBoe = setBoe;
function getBoe() {
    const reqCtx = getReqCtx();
    return reqCtx.boe;
}
exports.getBoe = getBoe;
function setEnv(env) {
    add('env', env);
}
exports.setEnv = setEnv;
function getEnv() {
    const reqCtx = getReqCtx();
    return reqCtx.env;
}
exports.getEnv = getEnv;
function getSysHeaders() {
    return getReqCtx().sysHeaders;
}
function getEnvKey() {
    return getByHeaders(constants_1.headers.envKey);
}
exports.getEnvKey = getEnvKey;
function getLaneKey() {
    return getByHeaders(constants_1.headers.laneCtxKey);
}
exports.getLaneKey = getLaneKey;
function setDebugType(debugType) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.headers.debug] = debugType;
    add('sysHeaders', sysHeaders);
}
exports.setDebugType = setDebugType;
function setLogID(logID) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.headers.kunlunLogid] = logID;
    add('sysHeaders', sysHeaders);
}
exports.setLogID = setLogID;
function setEnvKey(env) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.headers.envKey] = env;
    add('sysHeaders', sysHeaders);
}
exports.setEnvKey = setEnvKey;
function setFlowVersion(flowVersion) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.nodeClsKey.flowVersion] = flowVersion;
    add('sysHeaders', sysHeaders);
}
exports.setFlowVersion = setFlowVersion;
function getFlowVersion() {
    return getByHeaders(constants_1.nodeClsKey.flowVersion);
}
exports.getFlowVersion = getFlowVersion;
// sysHeaders: logID, loggerInfo, triggerType, deployedGlobalFuncNames, deployedGlobalFuncMap,
// apiTimeoutFromTcc, getRetryTimesFromTcc, globalVariablesKey
function getByHeaders(key) {
    const reqCtx = getReqCtx();
    if (reqCtx.sysHeaders && reqCtx.sysHeaders[key]) {
        return reqCtx.sysHeaders[key];
    }
    return undefined;
}
function isNumeric(str) {
    return !isNaN(Number(str)) && str.trim() !== '';
}
function getLogID() {
    let logid = getByHeaders(constants_1.headers.kunlunLogid);
    if (!logid) {
        logid = (0, logid_1.default)();
        setLogID(logid);
    }
    return logid;
}
exports.getLogID = getLogID;
// 头部不传，返回0；0 代表不限；
function getRateLimitFromHeader() {
    const rateLimit = getByHeaders(constants_1.headers.SDKPodRateLimitQuota);
    typeof rateLimit === 'string' && !isNaN(Number(rateLimit));
    if (isNumeric(rateLimit)) {
        return Number(rateLimit);
    }
    return 0;
}
exports.getRateLimitFromHeader = getRateLimitFromHeader;
function getRateLimitDowngradeFromHeader() {
    const downgrade = getByHeaders(constants_1.headers.SDKPodRateLimitDowngradeHeader);
    if (downgrade !== undefined) {
        return downgrade;
    }
    return 'false';
}
exports.getRateLimitDowngradeFromHeader = getRateLimitDowngradeFromHeader;
function getExecuteID() {
    return getByHeaders(constants_1.headers.ExecuteID);
}
exports.getExecuteID = getExecuteID;
function getFunctionAPIID() {
    return getByHeaders(constants_1.headers.FunctionAPIID);
}
exports.getFunctionAPIID = getFunctionAPIID;
class LoggerInfo {
}
function getLoggerInfo() {
    let loggerInfo = getByHeaders(constants_1.headers.loggerInfo);
    if (loggerInfo) {
        return loggerInfo;
    }
    return new LoggerInfo();
}
exports.getLoggerInfo = getLoggerInfo;
function getSourceFromDynCtx() {
    const dynCtx = getDynCtx();
    if (dynCtx.source) {
        return dynCtx.source;
    }
    return '';
}
function getSourceFromReqCtx() {
    return getByHeaders(constants_1.headers.source);
}
function getSource() {
    let source = getSourceFromDynCtx();
    if (!source) {
        source = getSourceFromReqCtx();
    }
    return source;
}
exports.getSource = getSource;
function getTriggerType() {
    return getByHeaders(constants_1.headers.triggerType);
}
exports.getTriggerType = getTriggerType;
function getDeployedGlobalFuncNames() {
    return getByHeaders(constants_1.headers.deployedGlobalFunctions);
}
exports.getDeployedGlobalFuncNames = getDeployedGlobalFuncNames;
function getDeployedGlobalFuncMap() {
    return getByHeaders(constants_1.headers.deployedGlobalFunctionMap);
}
exports.getDeployedGlobalFuncMap = getDeployedGlobalFuncMap;
function getApiTimeoutFromTcc() {
    return getByHeaders(constants_1.headers.apiTimeoutFromTcc);
}
exports.getApiTimeoutFromTcc = getApiTimeoutFromTcc;
function getRetryTimesFromTcc() {
    let retryTimes = getByHeaders(constants_1.headers.retryTimesFromTcc);
    if (retryTimes > 3) {
        return 3;
    }
    if (retryTimes < 0) {
        return 0;
    }
    return retryTimes;
}
exports.getRetryTimesFromTcc = getRetryTimesFromTcc;
function getDistributedHandleMask() {
    return getByHeaders(constants_1.headers.distributedHandleMask);
}
exports.getDistributedHandleMask = getDistributedHandleMask;
function isDebug() {
    const debugKey = getByHeaders(constants_1.headers.debug);
    return debugKey === '1' || debugKey === '2';
}
exports.isDebug = isDebug;
function isLocalDebug() {
    return getByHeaders(constants_1.headers.debug) === '2';
}
exports.isLocalDebug = isLocalDebug;
function isOnlineDebug() {
    return getByHeaders(constants_1.headers.debug) === '1';
}
exports.isOnlineDebug = isOnlineDebug;
function getDebugCode() {
    return getByHeaders(constants_1.headers.debugCodeUrl);
}
exports.getDebugCode = getDebugCode;
function getFunctionsVersion() {
    let v = getByHeaders(constants_1.headers.functionsVersion);
    if (!v) {
        return 0;
    }
    return Number(v);
}
exports.getFunctionsVersion = getFunctionsVersion;
function getServiceID() {
    const reqCtx = getReqCtx();
    return reqCtx.serviceID;
}
exports.getServiceID = getServiceID;
function getTriggerTime() {
    return Number(getByHeaders(constants_1.headers.triggerTime));
}
exports.getTriggerTime = getTriggerTime;
function getInvokeFuncName() {
    return getByHeaders(constants_1.headers.invokeFuncName);
}
exports.getInvokeFuncName = getInvokeFuncName;
function setInvokeFuncName(funcName) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.headers.invokeFuncName] = funcName;
    add('sysHeaders', sysHeaders);
}
exports.setInvokeFuncName = setInvokeFuncName;
function isAsync() {
    return getByHeaders(constants_1.headers.asyncTask) === '1';
}
exports.isAsync = isAsync;
function getTriggerTaskID() {
    let taskId = getByHeaders(constants_1.headers.triggerTaskId);
    if (!taskId) {
        return 0;
    }
    return Number(taskId);
}
exports.getTriggerTaskID = getTriggerTaskID;
function getTriggerTaskIDStr() {
    const taskId = getByHeaders(constants_1.headers.triggerTaskIdStr);
    if (!taskId) {
        return '';
    }
    return String(taskId);
}
exports.getTriggerTaskIDStr = getTriggerTaskIDStr;
function getOpenapiToken() {
    return getByHeaders(constants_1.headers.openapiToken);
}
exports.getOpenapiToken = getOpenapiToken;
function getFaasinfraToken() {
    return getByHeaders(constants_1.headers.faasinfraToken);
}
exports.getFaasinfraToken = getFaasinfraToken;
function getFaasType() {
    return getByHeaders(constants_1.headers.faasAccessType);
}
exports.getFaasType = getFaasType;
function isCloseIntranetDomain() {
    return getByHeaders(constants_1.headers.isCloseIntranetDomain) === 'true';
}
exports.isCloseIntranetDomain = isCloseIntranetDomain;
function getHttpMethod() {
    const method = getByHeaders('method');
    if (method) {
        return method;
    }
    return 'POST';
}
exports.getHttpMethod = getHttpMethod;
// loggerInfo: sourceID
function getSourceID() {
    return getLoggerInfo().sourceID;
}
exports.getSourceID = getSourceID;
function getSourceLabel() {
    return getLoggerInfo().sourceLabel;
}
exports.getSourceLabel = getSourceLabel;
function getObjectLabel() {
    return getLoggerInfo().objectLabel;
}
exports.getObjectLabel = getObjectLabel;
function getInstanceID() {
    return getLoggerInfo().instanceID;
}
exports.getInstanceID = getInstanceID;
function getFuncVersionID() {
    return getLoggerInfo().functionVersionID;
}
exports.getFuncVersionID = getFuncVersionID;
function getFuncLabel() {
    return getLoggerInfo().functionLabel;
}
exports.getFuncLabel = getFuncLabel;
function getMetrics() {
    const reqCtx = getReqCtx();
    if (reqCtx.metrics) {
        return reqCtx.metrics;
    }
    return new Array();
}
exports.getMetrics = getMetrics;
function addMetrics(metrics) {
    const reqCtx = getReqCtx();
    if (!reqCtx.metrics) {
        reqCtx.metrics = new Array();
    }
    reqCtx.metrics.push(metrics);
}
exports.addMetrics = addMetrics;
function getLoopMasks() {
    let loopMasks = getByHeaders(constants_1.headers.loopMasks);
    if (loopMasks) {
        return loopMasks;
    }
    return [];
}
exports.getLoopMasks = getLoopMasks;
function getGlobalVariables() {
    return getByHeaders(constants_1.headers.globalVariablesKey);
}
exports.getGlobalVariables = getGlobalVariables;
function setHttpHeaders(key, value) {
    const reqCtx = getReqCtx();
    if (reqCtx.responseHeaders) {
        reqCtx.responseHeaders[key] = value;
    }
}
exports.setHttpHeaders = setHttpHeaders;
function getRequireFunc() {
    return getReqCtx().requireFunc;
}
exports.getRequireFunc = getRequireFunc;
function addCredential(credential) {
    add(constants_1.nodeClsKey.credential, credential);
}
exports.addCredential = addCredential;
function getCredential() {
    return getReqCtx().credential;
}
exports.getCredential = getCredential;
function getOpenSDKKeys() {
    return getReqCtx()[constants_1.nodeClsKey.openSDKKey];
}
exports.getOpenSDKKeys = getOpenSDKKeys;
function addPlatformEnvTypeForOpenSDK(envType) {
    let keys = getOpenSDKKeys();
    if (!keys) {
        keys = {};
    }
    keys.envType = envType;
    add(constants_1.nodeClsKey.openSDKKey, keys);
}
exports.addPlatformEnvTypeForOpenSDK = addPlatformEnvTypeForOpenSDK;
function getPlatformEnvTypeForOpenSDK() {
    let keys = getOpenSDKKeys();
    if (!keys) {
        return '';
    }
    return keys.envType;
}
exports.getPlatformEnvTypeForOpenSDK = getPlatformEnvTypeForOpenSDK;
function addModeForOpenSDK(mode) {
    let keys = getOpenSDKKeys();
    if (!keys) {
        keys = {};
    }
    keys.mode = mode;
    add(constants_1.nodeClsKey.openSDKKey, keys);
}
exports.addModeForOpenSDK = addModeForOpenSDK;
function getModeForOpenSDK() {
    let keys = getOpenSDKKeys();
    if (!keys) {
        return '';
    }
    return keys.mode;
}
exports.getModeForOpenSDK = getModeForOpenSDK;
function getLaneID() {
    const laneID = getByHeaders(constants_1.headers.LaneIDHeaderKey);
    if (laneID) {
        return laneID;
    }
    return '';
}
exports.getLaneID = getLaneID;
function getEnvID() {
    const envID = getByHeaders(constants_1.headers.EnvIDHeaderKey);
    if (envID) {
        return envID;
    }
    return '';
}
exports.getEnvID = getEnvID;
function getEnvType() {
    const envID = getByHeaders(constants_1.headers.EnvTypeHeaderKey);
    if (envID) {
        return envID;
    }
    return 0;
}
exports.getEnvType = getEnvType;
function getHttpHeaders() {
    const reqCtx = getReqCtx();
    return reqCtx.headers;
}
exports.getHttpHeaders = getHttpHeaders;
function getUnauthFieldMap() {
    const reqCtx = getReqCtx();
    if (!reqCtx.unauthFields) {
        reqCtx.unauthFields = {};
    }
    return reqCtx.unauthFields;
}
exports.getUnauthFieldMap = getUnauthFieldMap;
function setUnauthFieldMap(unauthFields) {
    const reqCtx = getReqCtx();
    reqCtx.unauthFields = unauthFields;
}
exports.setUnauthFieldMap = setUnauthFieldMap;
function getFuncMetaConf(apiName) {
    const funcMetaConf = getByHeaders(constants_1.headers.functionMetaConf);
    if (funcMetaConf && funcMetaConf[apiName.toLowerCase()]) {
        return funcMetaConf[apiName.toLowerCase()];
    }
    return {};
}
exports.getFuncMetaConf = getFuncMetaConf;
function getFuncAPIName() {
    return getByHeaders(constants_1.headers.functionAPIName);
}
exports.getFuncAPIName = getFuncAPIName;
function getSDKConf() {
    const sdkConfStr = getByHeaders(constants_1.headers.sdkConfKey);
    if (sdkConfStr === '') {
        return undefined;
    }
    try {
        return JSON.parse(sdkConfStr);
    }
    catch (err) {
        return undefined;
    }
}
exports.getSDKConf = getSDKConf;
function getSDKTransientConf() {
    const sdkConf = getSDKConf();
    if (!sdkConf) {
        return undefined;
    }
    return sdkConf.transientConf;
}
exports.getSDKTransientConf = getSDKTransientConf;
function setSDKInfo(fromSDK, fromVersion) {
    let sysHeaders = getSysHeaders();
    if (!sysHeaders) {
        sysHeaders = {};
    }
    sysHeaders[constants_1.APaaSPersistKey.PersistFaaSKeyFromSDKName] = fromSDK;
    sysHeaders[constants_1.APaaSPersistKey.PersistFaaSKeyFromSDKVersion] = fromVersion;
    add('sysHeaders', sysHeaders);
}
exports.setSDKInfo = setSDKInfo;
function getAPaaSPersistFaaSPressureSignalId() {
    const value = getByHeaders(constants_1.APaaSPersistKey.PersistFaaSKeyRequestSource);
    if (value && typeof value === 'string') {
        const reqSrc = JSON.parse(value);
        if (reqSrc && reqSrc[constants_1.APaaSPersistKey.RequestSourcePressureSignalId]) {
            return reqSrc[constants_1.APaaSPersistKey.RequestSourcePressureSignalId];
        }
    }
    return '';
}
exports.getAPaaSPersistFaaSPressureSignalId = getAPaaSPersistFaaSPressureSignalId;
function getPressureNeedDecelerate() {
    const value = getByHeaders(constants_1.headers.SdkPressureNeedDecelerateHeader);
    return value !== undefined
        && ((typeof value === 'string' && value.toLowerCase() === 'true')
            || value === true); // 直接使用严格相等判断
}
exports.getPressureNeedDecelerate = getPressureNeedDecelerate;
function getPressureConfig() {
    return getByHeaders(constants_1.headers.SdkPressureConfigHeader);
}
exports.getPressureConfig = getPressureConfig;
