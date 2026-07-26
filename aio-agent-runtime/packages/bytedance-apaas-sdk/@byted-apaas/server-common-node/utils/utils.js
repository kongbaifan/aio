"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getDebugCode = exports.isOpenSDKMode = exports.isOnlineDev = exports.getFunctionsType = exports.isOnlineDebug = exports.isLocalDebug = exports.setDebugType = exports.isDebug = exports.getDistributedHandleMask = exports.getTriggerType = exports.getSource = exports.getArrayLength = exports.isRegex = exports.isObject = exports.mockUserID = exports.getUserIDFromCtx = exports.getUser = exports.getDomainFromCtx = exports.getNamespaceFromCtx = exports.getTenantTypeFromCtx = exports.getTenantNameFromCtx = exports.getTenantIDFromCtx = exports.setTenant = exports.getEvent = exports.getApp = exports.getTenant = exports.printErrorLog = exports.printDebugLog = exports.printInfoLog = exports.isDeployedGlobalFuncNames = exports.getFuncLabel = exports.getFuncVersionID = exports.isAsync = exports.getInstanceID = exports.getObjectLabel = exports.getSourceLabel = exports.getSourceID = exports.getTriggerTime = exports.handleErrorMsg = exports.getRetryTimesFromTcc = exports.getApiTimeoutFromTcc = exports.getLoggerInfo = exports.getDeployedGlobalFuncMap = exports.getDeployedGlobalFuncNames = exports.setLogID = exports.getFunctionAPIID = exports.getExecuteID = exports.getRateLimitDowngradeFromHeader = exports.getRateLimitFromHeader = exports.getLogID = void 0;
exports.isMicroservice = exports.getKldxVersionsStr = exports.getKldxVersions = exports.getPkgVersion = exports.replaceErrorStack = exports.checkRequiredParam = exports.checkTypeOfParams = exports.isHttpConnectError = exports.getRequireFunc = exports.getGlobalVariableByKey = exports.getGlobalVariable = exports.getLoopMasks = exports.getMetrics = exports.fail = exports.success = exports.modifySource = exports.getHttpMethod = exports.isCloseIntranetDomain = exports.getFaasinfraToken = exports.getOpenapiToken = exports.getEnvWithBoe = exports.setXTTEnvOnlyDebug = exports.getLaneKey = exports.getEnvKey = exports.getEnv = exports.getBoe = exports.setEnv = exports.setBoe = exports.isBoe = exports.getFaasType = exports.setCredential = exports.setModeForOpenSDK = exports.setPlatformEnvTypeForOpenSDK = exports.getPlatformEnvTypeForOpenSDK = exports.getModeForOpenSDK = exports.getCredential = exports.setHttpHeaders = exports.getInvokeFuncApiAlias = exports.setInvokeFuncName = exports.getInvokeFuncName = exports.handleFuncName = exports.getTriggerTaskIDStr = exports.getTriggerTaskID = exports.mkdirs = exports.requireFunction = exports.getGlobalFunc = exports.argsToList = exports.getColorNameById = exports.stringify = exports.getOrSetFlowVersion = void 0;
exports.getServerInfo = exports.getFaaSInfraPSMAndCluster = exports.getOpenAPIPSMAndCluster = exports.isTmpUseLGW = exports.getFaaSInfraPSM = exports.getLGWCluster = exports.getLGWPSM = exports.getInnerapiAPIPSM = exports.setSDKInfo = exports.getTraceHeader = exports.isExternal = exports.getSocketAddr = exports.isTrueString = exports.enableMesh = exports.isCloseMesh = exports.getGlobalAuthType = exports.delKeyPath = exports.getValueByPath = exports.hasKeyPath = exports.getFuncAPIName = exports.getCurFuncMetaConf = exports.getFuncMetaConf = exports.getHttpHeaders = exports.addEnvTypeToHeader = exports.addFunctionAPIIDToHeader = exports.addEnvIDToHeader = exports.addLaneIDToHeader = exports.getEnvType = exports.getEnvID = exports.getLaneID = exports.formatAuthType = exports.aesCbcDecrypt = exports.hexDecode = exports.aesDecryptText = exports.paddingN = exports.decryptBySvcIDAndNS = exports.decryptByTNameAndNS = exports.getFaasinfraDomain = exports.getOpenapiDomain = exports.getClientSecret = exports.getClientId = exports.getPrefixAPI = exports.isKunlunOrg = exports.getOrgId = exports.getServiceSecret = exports.getServiceId = exports.getBizIDC = exports.addPersistAPaaSValuetoHeader = exports.getAPaaSPersistFaaSMap = exports.getFaaSType = void 0;
exports.sleepMs = exports.getMeshDestReqTimeout = void 0;
const nodeClsCtx = require("./nodeClsCtx");
const nodeClsCtx_1 = require("./nodeClsCtx");
const metrics_1 = require("../context/metrics");
const exceptions_1 = require("./exceptions");
const constants_1 = require("../constants/constants");
const path = require('path');
const fs = require('fs');
const CryptoJS = require('crypto-js');
function throwInvalidParamError(msg) {
    const exceptions = require('./exceptions');
    throw new exceptions.InvalidParamError(msg);
}
function throwInternalError(msg) {
    const exceptions = require('./exceptions');
    throw new exceptions.InternalError(msg);
}
function getHttpConfig() {
    return require('../http/config');
}
// common 依赖----------------------------------------------------------------------------------------------------------------------------------------
/**
 * logId和requestId用的同一个值
 */
function getLogID() {
    return nodeClsCtx.getLogID();
}
exports.getLogID = getLogID;
function getRateLimitFromHeader() {
    return nodeClsCtx.getRateLimitFromHeader();
}
exports.getRateLimitFromHeader = getRateLimitFromHeader;
function getRateLimitDowngradeFromHeader() {
    return nodeClsCtx.getRateLimitDowngradeFromHeader();
}
exports.getRateLimitDowngradeFromHeader = getRateLimitDowngradeFromHeader;
function getExecuteID() {
    return nodeClsCtx.getExecuteID();
}
exports.getExecuteID = getExecuteID;
function getFunctionAPIID() {
    return nodeClsCtx.getFunctionAPIID();
}
exports.getFunctionAPIID = getFunctionAPIID;
function setLogID(logID) {
    nodeClsCtx.setLogID(logID);
}
exports.setLogID = setLogID;
function getDeployedGlobalFuncNames() {
    return nodeClsCtx.getDeployedGlobalFuncNames();
}
exports.getDeployedGlobalFuncNames = getDeployedGlobalFuncNames;
function getDeployedGlobalFuncMap() {
    return nodeClsCtx.getDeployedGlobalFuncMap();
}
exports.getDeployedGlobalFuncMap = getDeployedGlobalFuncMap;
function getLoggerInfo() {
    return nodeClsCtx.getLoggerInfo();
}
exports.getLoggerInfo = getLoggerInfo;
function getApiTimeoutFromTcc() {
    return nodeClsCtx.getApiTimeoutFromTcc();
}
exports.getApiTimeoutFromTcc = getApiTimeoutFromTcc;
function getRetryTimesFromTcc() {
    return nodeClsCtx.getRetryTimesFromTcc();
}
exports.getRetryTimesFromTcc = getRetryTimesFromTcc;
// TODO 处理打点 metrics，下掉 ctx
function handleErrorMsg(e) {
    if (!e || !(e instanceof Error) || !e.message) {
        return;
    }
    if (e.message.indexOf('inspirecloud.db') > -1) {
        e.message = e.message.replace('inspirecloud.db', 'mongodb');
    }
    if (e.message.indexOf('inspirecloud.file') > -1) {
        e.message = e.message.replace('inspirecloud.file', 'oss');
    }
    if (e.message.indexOf('inspirecloud.redis') > -1) {
        e.message = e.message.replace('inspirecloud.file', 'redis');
    }
    if (e.message.indexOf('bc.redis') > -1) {
        e.message = e.message.replace('inspirecloud.file', 'redis');
    }
    e.message = e.message.replace('inspirecloud.', 'aPaaS.');
}
exports.handleErrorMsg = handleErrorMsg;
function getTriggerTime() {
    return nodeClsCtx.getTriggerTime();
}
exports.getTriggerTime = getTriggerTime;
function getSourceID() {
    return nodeClsCtx.getSourceID();
}
exports.getSourceID = getSourceID;
function getSourceLabel() {
    return nodeClsCtx.getSourceLabel();
}
exports.getSourceLabel = getSourceLabel;
function getObjectLabel() {
    return nodeClsCtx.getObjectLabel();
}
exports.getObjectLabel = getObjectLabel;
function getInstanceID() {
    return nodeClsCtx.getInstanceID();
}
exports.getInstanceID = getInstanceID;
function isAsync() {
    return nodeClsCtx.isAsync();
}
exports.isAsync = isAsync;
function getFuncVersionID() {
    return nodeClsCtx.getFuncVersionID();
}
exports.getFuncVersionID = getFuncVersionID;
function getFuncLabel() {
    return nodeClsCtx.getFuncLabel();
}
exports.getFuncLabel = getFuncLabel;
function isDeployedGlobalFuncNames(context, funcName) {
    let funcNames = getDeployedGlobalFuncNames();
    if (funcNames) {
        return funcNames.includes(funcName);
    }
    return false;
}
exports.isDeployedGlobalFuncNames = isDeployedGlobalFuncNames;
function printInfoLog(msg) {
    if (!isKunlunOrg() || isDebug() || isMicroservice() || isOpenSDKMode()) {
        return;
    }
    console.info(msg);
}
exports.printInfoLog = printInfoLog;
function printDebugLog(msg) {
    if (process.env.openDebug !== "true") {
        return;
    }
    console.info(msg);
}
exports.printDebugLog = printDebugLog;
function printErrorLog(msg) {
    if (!isKunlunOrg()) {
        console.trace(`errLog: ${msg}`);
    }
    if (!isKunlunOrg() || isDebug() || isMicroservice() || isOpenSDKMode()) {
        return;
    }
    console.error(msg);
}
exports.printErrorLog = printErrorLog;
// core or metadata 依赖----------------------------------------------------------------------------------------------------------------------------------------
function getTenant() {
    return nodeClsCtx.getTenant();
}
exports.getTenant = getTenant;
function getApp() {
    return nodeClsCtx.getApp();
}
exports.getApp = getApp;
function getEvent() {
    return nodeClsCtx.getEvent();
}
exports.getEvent = getEvent;
function setTenant(tenant) {
    nodeClsCtx.setTenant(tenant);
}
exports.setTenant = setTenant;
// tenant相关接口
// 1.tenantID
function getTenantIDFromCtx() {
    return getTenant().id;
}
exports.getTenantIDFromCtx = getTenantIDFromCtx;
// 2.tenantName，即kunlun的domainName
function getTenantNameFromCtx() {
    if (isMicroservice()) {
        return process.env.KTenantName;
    }
    let name = getTenant().name;
    return name ? name : "";
}
exports.getTenantNameFromCtx = getTenantNameFromCtx;
// 3.tenantType
function getTenantTypeFromCtx() {
    return getTenant().type;
}
exports.getTenantTypeFromCtx = getTenantTypeFromCtx;
// 4.namespace
function getNamespaceFromCtx() {
    if (!isKunlunOrg() || isMicroservice()) {
        return process.env.KNamespace;
    }
    const namespace = getTenant().namespace;
    if (!namespace) {
        throwInternalError('namespace is empty');
    }
    return namespace;
}
exports.getNamespaceFromCtx = getNamespaceFromCtx;
// 5.domain，表示outsideDomainName，即三方租户的domainName
function getDomainFromCtx() {
    return getTenant().domain;
}
exports.getDomainFromCtx = getDomainFromCtx;
function getUser() {
    return nodeClsCtx.getUser();
}
exports.getUser = getUser;
function getUserIDFromCtx() {
    return getUser()._id;
}
exports.getUserIDFromCtx = getUserIDFromCtx;
function mockUserID(userID) {
    nodeClsCtx.mockUserID(userID);
}
exports.mockUserID = mockUserID;
/**
 * 仅仅是Object，不是Array
 *
 * @param value
 * @returns {boolean}
 */
function isObject(value) {
    if (value === undefined) {
        return false;
    }
    return Object.prototype.toString.call(value) === '[object Object]';
}
exports.isObject = isObject;
function isRegex(value) {
    if (value === undefined) {
        return false;
    }
    return Object.prototype.toString.call(value) === '[object RegExp]';
}
exports.isRegex = isRegex;
function getArrayLength(arr) {
    if (!arr || !(arr instanceof Array)) {
        return 0;
    }
    return arr.length;
}
exports.getArrayLength = getArrayLength;
/**
 * source表示函数的类型，目前支持2种source
 * 1: 表示 workflow
 * 2: 表示 global_function
 * 3: 表示 automation
 * 4: 表示 schedule-automation
 *
 * @returns {string|*}
 */
function getSource() {
    return nodeClsCtx.getSource();
}
exports.getSource = getSource;
function getTriggerType() {
    if (isMicroservice()) {
        return 'microservice';
    }
    return nodeClsCtx.getTriggerType();
}
exports.getTriggerType = getTriggerType;
function getDistributedHandleMask() {
    return nodeClsCtx.getDistributedHandleMask();
}
exports.getDistributedHandleMask = getDistributedHandleMask;
function isDebug() {
    return nodeClsCtx.isDebug();
}
exports.isDebug = isDebug;
function setDebugType(debugType) {
    nodeClsCtx.setDebugType(debugType);
}
exports.setDebugType = setDebugType;
function isLocalDebug() {
    return nodeClsCtx.isLocalDebug();
}
exports.isLocalDebug = isLocalDebug;
function isOnlineDebug() {
    return nodeClsCtx.isOnlineDebug();
}
exports.isOnlineDebug = isOnlineDebug;
function getFunctionsType() {
    return nodeClsCtx.getFunctionsVersion();
}
exports.getFunctionsType = getFunctionsType;
function isOnlineDev() {
    return getFunctionsType() === 1;
}
exports.isOnlineDev = isOnlineDev;
function isOpenSDKMode() {
    return getModeForOpenSDK() === 'openSDK';
}
exports.isOpenSDKMode = isOpenSDKMode;
function getDebugCode() {
    return nodeClsCtx.getDebugCode();
}
exports.getDebugCode = getDebugCode;
function checkFlow(flowParam) {
    return flowParam && isObject(flowParam.variables);
}
function getOrSetFlowVersion(context) {
    let flowVersion = nodeClsCtx.getFlowVersion();
    if (flowVersion) {
        return flowVersion;
    }
    if (checkFlow(context.flow)) {
        flowVersion = 'v3';
    }
    else if (context.flow) {
        flowVersion = 'v2';
    }
    else if (context.workflow) {
        flowVersion = 'v1';
    }
    else {
        flowVersion = '-';
    }
    nodeClsCtx.setFlowVersion(flowVersion);
    return flowVersion;
}
exports.getOrSetFlowVersion = getOrSetFlowVersion;
/**
 * 处理循环引用
 *
 * @param value
 * @param cutCircle
 * @param replacer
 * @param space
 * @returns {string}
 */
function stringify(value, cutCircle = false, replacer = null, space = '') {
    if (cutCircle) {
        return JSON.stringify(deepCopy(value), replacer, space);
    }
    return JSON.stringify(value, replacer, space);
}
exports.stringify = stringify;
function getColorNameById(id) {
    if (colorId2name[id]) {
        return colorId2name[id];
    }
    return '';
}
exports.getColorNameById = getColorNameById;
/**
 * 场景：传参a、b、c、d、e，以下方式等效
 * 方式一：(a, b, c, d, e)
 * 方式二：([a, b, c, d, e])
 * 方式三：(a, [b, c], d, e)
 *
 * @param args
 * @returns {[]}
 */
function argsToList(...args) {
    let values = [];
    for (let arg of args) {
        if (typeof arg === 'undefined') {
            continue;
        }
        if (arg instanceof Array) {
            for (let a of arg) {
                if (typeof arg === 'undefined') {
                    continue;
                }
                values.push(a);
            }
        }
        else {
            values.push(arg);
        }
    }
    return values;
}
exports.argsToList = argsToList;
function getGlobalFunc(context, funcName, requireFunc) {
    if (!requireFunc) {
        requireFunc = getRequireFunc();
    }
    // 只有 debug 模式才判断
    if (isDebug()) {
        if (!isDeployedGlobalFuncNames(null, funcName)) {
            return null;
        }
    }
    try {
        return requireFunc(funcName);
    }
    catch (err) {
        if (err.message.includes('Cannot find module')) {
            return null;
        }
        else {
            throw err;
        }
    }
}
exports.getGlobalFunc = getGlobalFunc;
function requireFunction(apiName) {
    const requireFunc = getRequireFunc();
    try {
        return requireFunc(apiName);
    }
    catch (err) {
        if (err.message.includes('Cannot find module')) {
            throw new Error(`The function (${apiName}) does not exist.`);
        }
        throw err;
    }
}
exports.requireFunction = requireFunction;
function mkdirs(dirpath) {
    if (!fs.existsSync(path.dirname(dirpath))) {
        mkdirs(path.dirname(dirpath));
    }
    if (!fs.existsSync(dirpath)) {
        fs.mkdirSync(dirpath);
    }
}
exports.mkdirs = mkdirs;
function getTriggerTaskID() {
    return nodeClsCtx.getTriggerTaskID();
}
exports.getTriggerTaskID = getTriggerTaskID;
function getTriggerTaskIDStr() {
    return nodeClsCtx.getTriggerTaskIDStr();
}
exports.getTriggerTaskIDStr = getTriggerTaskIDStr;
/**
 * 兼容有无namespace的场景
 *
 * @param context
 * @param funcName
 * @returns {string|*}
 */
function handleFuncName(context, funcName) {
    let oldFuncName = funcName;
    const prefix = getNamespaceFromCtx() + '__';
    // 优先进行ApiAlias->ApiName转换
    let deployedGlobalFuncMap = getDeployedGlobalFuncMap();
    if (deployedGlobalFuncMap && Object.keys(deployedGlobalFuncMap).length !== 0) {
        let apiAlias = funcName;
        if (funcName.startsWith(prefix)) {
            apiAlias = funcName.substr(prefix.length);
        }
        return deployedGlobalFuncMap[apiAlias];
    }
    // 1.拼接namespace
    if (oldFuncName.indexOf(prefix) < 0) {
        funcName = prefix + oldFuncName;
    }
    // 2.判断拼接namespace后的合法性
    if (isDeployedGlobalFuncNames(null, funcName)) {
        return funcName;
    }
    // 3.判断拼接namespace前的合法性
    if (isDeployedGlobalFuncNames(null, oldFuncName)) {
        return oldFuncName;
    }
    throwInvalidParamError(`The function (${oldFuncName}) does not exist, please confirm ${oldFuncName} exists and has been deployed.`);
    return '';
}
exports.handleFuncName = handleFuncName;
function trimNSPrefix(apiName) {
    const nsPrefix = getNamespaceFromCtx() + '__';
    if (apiName.startsWith(nsPrefix)) {
        return apiName.substring(nsPrefix.length);
    }
    return apiName;
}
function getInvokeFuncName() {
    return nodeClsCtx.getInvokeFuncName();
}
exports.getInvokeFuncName = getInvokeFuncName;
function setInvokeFuncName(funcName) {
    nodeClsCtx.setInvokeFuncName(funcName);
}
exports.setInvokeFuncName = setInvokeFuncName;
function getInvokeFuncApiAlias() {
    let apiName = getInvokeFuncName();
    // 非全局函数，apiName 和 apiAlias 相差前缀 namespace__
    if (isOnlineDev() && getSource() !== constants_1.functionSources.globalFunction) {
        return trimNSPrefix(apiName);
    }
    // 全局函数且函数「已部署」，根据 map[alias]name，转换得到 alias
    let map = getDeployedGlobalFuncMap();
    if (map) {
        for (const key of Object.keys(map)) {
            if (map[key] === apiName) {
                return key;
            }
        }
    }
    // 全局函数且函数「未部署」，此时 map[alias]name 中没有对应的值
    return trimNSPrefix(apiName);
}
exports.getInvokeFuncApiAlias = getInvokeFuncApiAlias;
function setHttpHeaders(key, value) {
    nodeClsCtx.setHttpHeaders(key, value);
}
exports.setHttpHeaders = setHttpHeaders;
// 新增------------------------------------------------------------------------------------------------------------------------------
function getCredential() {
    return nodeClsCtx.getCredential();
}
exports.getCredential = getCredential;
function getModeForOpenSDK() {
    return nodeClsCtx.getModeForOpenSDK();
}
exports.getModeForOpenSDK = getModeForOpenSDK;
function getPlatformEnvTypeForOpenSDK() {
    let pEnv = nodeClsCtx.getPlatformEnvTypeForOpenSDK();
    return pEnv ? pEnv : 'online';
}
exports.getPlatformEnvTypeForOpenSDK = getPlatformEnvTypeForOpenSDK;
function setPlatformEnvTypeForOpenSDK(envType) {
    nodeClsCtx.addPlatformEnvTypeForOpenSDK(envType);
}
exports.setPlatformEnvTypeForOpenSDK = setPlatformEnvTypeForOpenSDK;
function setModeForOpenSDK(mode) {
    nodeClsCtx.addModeForOpenSDK(mode);
}
exports.setModeForOpenSDK = setModeForOpenSDK;
function setCredential(credential) {
    nodeClsCtx.addCredential(credential);
}
exports.setCredential = setCredential;
function getFaasType() {
    return nodeClsCtx.getFaasType();
}
exports.getFaasType = getFaasType;
function isBoe() {
    return nodeClsCtx.getBoe() === 'boe';
}
exports.isBoe = isBoe;
function setBoe(boe) {
    nodeClsCtx.setBoe(boe);
}
exports.setBoe = setBoe;
function setEnv(env) {
    nodeClsCtx.setEnv(env);
}
exports.setEnv = setEnv;
function getBoe() {
    return nodeClsCtx.getBoe();
}
exports.getBoe = getBoe;
function getEnv() {
    if (isMicroservice()) {
        return process.env.ENV;
    }
    return nodeClsCtx.getEnv();
}
exports.getEnv = getEnv;
function getEnvKey() {
    return nodeClsCtx.getEnvKey();
}
exports.getEnvKey = getEnvKey;
function getLaneKey() {
    return nodeClsCtx.getLaneKey();
}
exports.getLaneKey = getLaneKey;
// 设置 x_tt_env 仅调试时生效
function setXTTEnvOnlyDebug(xTTEnv) {
    if (!xTTEnv || !isDebug()) {
        return;
    }
    nodeClsCtx.setEnvKey(xTTEnv);
}
exports.setXTTEnvOnlyDebug = setXTTEnvOnlyDebug;
function getEnvWithBoe() {
    const env = getEnv();
    const bizIDC = getBizIDC();
    const boe = getBoe();
    if (boe) {
        return env + '_' + boe;
    }
    if (bizIDC) {
        return env + '_' + bizIDC;
    }
    return env;
}
exports.getEnvWithBoe = getEnvWithBoe;
function getOpenapiToken() {
    return nodeClsCtx.getOpenapiToken();
}
exports.getOpenapiToken = getOpenapiToken;
function getFaasinfraToken() {
    return nodeClsCtx.getFaasinfraToken();
}
exports.getFaasinfraToken = getFaasinfraToken;
function isCloseIntranetDomain() {
    return nodeClsCtx.isCloseIntranetDomain();
}
exports.isCloseIntranetDomain = isCloseIntranetDomain;
function getHttpMethod() {
    return nodeClsCtx.getHttpMethod();
}
exports.getHttpMethod = getHttpMethod;
function modifySource(ctx, source) {
    let resultCtx = { ...ctx };
    resultCtx.source = source;
    Object.freeze(resultCtx);
    return resultCtx;
}
exports.modifySource = modifySource;
function success(options, beginReqTime) {
    nodeClsCtx.addMetrics(new metrics_1.Metrics(options._reqServer, options._reqMethod, true, new Date().getTime() - beginReqTime));
}
exports.success = success;
function fail(options, beginReqTime) {
    nodeClsCtx.addMetrics(new metrics_1.Metrics(options._reqServer, options._reqMethod, false, new Date().getTime() - beginReqTime));
}
exports.fail = fail;
function getMetrics() {
    return nodeClsCtx.getMetrics();
}
exports.getMetrics = getMetrics;
function getLoopMasks() {
    return nodeClsCtx.getLoopMasks();
}
exports.getLoopMasks = getLoopMasks;
function getGlobalVariable() {
    let globalVariables = nodeClsCtx.getGlobalVariables();
    if (!globalVariables) {
        throw new exceptions_1.InternalError('internal error');
    }
    return globalVariables;
}
exports.getGlobalVariable = getGlobalVariable;
function getGlobalVariableByKey(key) {
    let globalVariables = getGlobalVariable();
    if (globalVariables[key] === undefined) {
        throw new exceptions_1.InvalidParamError(`undefined global variable (${key})`);
    }
    return globalVariables[key];
}
exports.getGlobalVariableByKey = getGlobalVariableByKey;
function getRequireFunc() {
    return nodeClsCtx.getRequireFunc();
}
exports.getRequireFunc = getRequireFunc;
function isHttpConnectError(err) {
    if (err) {
        if (err.event && ['connect', 'secureConnect', 'lookup'].includes(err.event)) {
            return true;
        }
        if (err.code && ['ECONNREFUSED', 'EHOSTUNREACH', 'EPIPE', 'ENETUNREACH', 'ENETDOWN', 'EHOSTDOWN', 'EAI_AGAIN'].includes(err.code)) {
            return true;
        }
        if (err.code === 'ECONNRESET' && (['read ECONNRESET', 'socket hang up'].includes(err.message))) {
            return true;
        }
    }
    return false;
}
exports.isHttpConnectError = isHttpConnectError;
/**
 * 检查参数本身或者其中元素的类型
 * @param name 参数名字，用来抛异常
 * @param typeValues 判断类型，TypeofValue 枚举
 * @param param 判断参数
 * @param checkUndefined 是否检查 undefined
 */
function checkTypeOfParams(name, typeValues, param, checkUndefined = true) {
    if (!typeValues || typeValues.length < 1) {
        return;
    }
    if (checkUndefined) {
        checkRequiredParam(name, param);
    }
    else {
        if (!param) {
            return;
        }
    }
    let tmp = typeof param, isThrow = true;
    for (const i in typeValues) {
        if (tmp === typeValues[i]) {
            isThrow = false;
        }
    }
    let typeStr = '', i = 0;
    for (i = 0; i < typeValues.length - 1; i++) {
        typeStr += `${typeValues[i]} or `;
    }
    typeStr += typeValues[i];
    if (isThrow) {
        throw new exceptions_1.InvalidParamError(`${name} is ${tmp}, but not ${typeStr}`);
    }
}
exports.checkTypeOfParams = checkTypeOfParams;
/**
 * 检查参数是否是 undefined
 * @param name 参数名字，用来抛异常
 * @param param 判断参数
 */
function checkRequiredParam(name, param) {
    if (!param) {
        throw new exceptions_1.InvalidParamError(`${name} is required`);
    }
}
exports.checkRequiredParam = checkRequiredParam;
function replaceErrorStack(err, before, after) {
    if (!err || !(err.stack)) {
        return;
    }
    err.stack = err.stack.replace(new RegExp(before, 'g'), after);
}
exports.replaceErrorStack = replaceErrorStack;
function deepCopy(source, refs) {
    if (!refs) {
        refs = new WeakSet();
    }
    if (!isObject(source) && !Array.isArray(source)) {
        return source;
    }
    if (refs.has(source)) {
        return '[Circular]';
    }
    let target = isObject(source) ? {} : [];
    for (let key in source) {
        if (source && source.hasOwnProperty && source.hasOwnProperty(key)) {
            refs.add(source);
            target[key] = deepCopy(source[key], refs);
            refs.delete(source);
        }
    }
    return target;
}
const colorId2name = {
    N: 'grey',
    B: 'blue',
    W: 'cyan',
    G: 'green',
    Y: 'yellow',
    O: 'orange',
    R: 'red',
    V: 'magenta',
    P: 'purple',
    I: 'blueMagenta',
};
const colorName2id = {
    grey: 'N',
    blue: 'B',
    cyan: 'W',
    green: 'G',
    yellow: 'Y',
    orange: 'O',
    red: 'R',
    magenta: 'V',
    purple: 'P',
    blueMagenta: 'I',
};
function getPkgVersion(pkgName) {
    let result = {};
    const requireFunc = getRequireFunc();
    try {
        let pkg = requireFunc(`../node_modules/${pkgName}/package.json`);
        if (pkg) {
            result[pkgName] = pkg.version;
        }
    }
    catch (err) {
    }
    return result;
}
exports.getPkgVersion = getPkgVersion;
function getKldxVersions() {
    const commonVersion = getPkgVersion('@byted-apaas/server-common');
    const coreVersion = getPkgVersion('@byted-apaas/server-sdk');
    const infraVersion = getPkgVersion('@kldx/baas-sdk');
    const faasVersion = getPkgVersion('@kldx/faas-sdk');
    return { ...commonVersion, ...coreVersion, ...infraVersion, ...faasVersion };
}
exports.getKldxVersions = getKldxVersions;
function getKldxVersionsStr() {
    return JSON.stringify(getKldxVersions());
}
exports.getKldxVersionsStr = getKldxVersionsStr;
function isMicroservice() {
    return process.env.KFaaSScene === 'microservice';
}
exports.isMicroservice = isMicroservice;
function getFaaSType() {
    if (isMicroservice()) {
        return constants_1.FaaSType.FaaSTypeMicroService;
    }
    else if (isOpenSDKMode()) {
        return constants_1.FaaSType.FaaSTypeOpenSDK;
    }
    else {
        return constants_1.FaaSType.FaaSTypeFunction;
    }
}
exports.getFaaSType = getFaaSType;
function getAPaaSPersistFaaSMap() {
    let persistFaaSMap = {};
    let sysHeaders = (0, nodeClsCtx_1.getReqCtx)().sysHeaders;
    if (sysHeaders) {
        for (let key of Object.keys(sysHeaders)) {
            let value = sysHeaders[key];
            if (key.startsWith(constants_1.APaaSPersistKey.APAAS_PERSIST_FAAS_PREFIX)) {
                persistFaaSMap[key] = value;
            }
        }
    }
    persistFaaSMap[constants_1.APaaSPersistKey.PersistFaaSKeyFaaSType] = getFaaSType();
    // 兜底逻辑 - 非全局函数
    if (getFaaSType() === constants_1.FaaSType.FaaSTypeFunction && !persistFaaSMap[constants_1.APaaSPersistKey.PersistFaaSKeyFuncAPIName]) {
        persistFaaSMap[constants_1.APaaSPersistKey.PersistFaaSKeyFuncAPIName] = getInvokeFuncApiAlias();
    }
    return persistFaaSMap;
}
exports.getAPaaSPersistFaaSMap = getAPaaSPersistFaaSMap;
function getAPaaSPersistMap() {
    let persistAPaaSMap = {};
    let sysHeaders = (0, nodeClsCtx_1.getReqCtx)().sysHeaders;
    if (sysHeaders) {
        for (let key of Object.keys(sysHeaders)) {
            let value = sysHeaders[key];
            if (key.startsWith(constants_1.APaaSPersistKey.APAAS_PERSIST_PREFIX)) {
                persistAPaaSMap[key] = value;
            }
        }
    }
    return persistAPaaSMap;
}
function addPersistAPaaSValuetoHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    let aPaaSHeaders = getAPaaSPersistMap();
    for (let key of Object.keys(aPaaSHeaders)) {
        options.headers[key] = aPaaSHeaders[key];
    }
}
exports.addPersistAPaaSValuetoHeader = addPersistAPaaSValuetoHeader;
function getBizIDC() {
    return process.env.KBizIDC;
}
exports.getBizIDC = getBizIDC;
function getServiceId() {
    if (process.env.KSvcID) {
        return process.env.KSvcID;
    }
    let serviceID = nodeClsCtx.getServiceID();
    if (serviceID) {
        return serviceID;
    }
    throw new exceptions_1.InternalError('serviceID is empty');
}
exports.getServiceId = getServiceId;
function getServiceSecret() {
    if (!process.env.KSvcSecret) {
        throw new exceptions_1.InternalError('process.env.KSvcSecret is empty');
    }
    return decryptBySvcIDAndNS(process.env.KSvcSecret);
}
exports.getServiceSecret = getServiceSecret;
function getOrgId() {
    if (process.env.KOrgID === undefined) {
        return constants_1.kunlunOrgID;
    }
    if (process.env.KOrgID === '0') {
        return constants_1.kunlunOrgID;
    }
    return process.env.KOrgID;
}
exports.getOrgId = getOrgId;
function isKunlunOrg() {
    return getOrgId() === constants_1.kunlunOrgID;
}
exports.isKunlunOrg = isKunlunOrg;
function getPrefixAPI() {
    if (isKunlunOrg()) {
        return 'kunlun';
    }
    return process.env.KPrefixAPI;
}
exports.getPrefixAPI = getPrefixAPI;
function getClientId() {
    if (!process.env.KClientID) {
        throw new exceptions_1.InternalError('process.env.KClientID is empty');
    }
    return decryptByTNameAndNS(process.env.KClientID);
}
exports.getClientId = getClientId;
function getClientSecret() {
    if (!process.env.KClientSecret) {
        throw new exceptions_1.InternalError('process.env.KClientSecret is empty');
    }
    return decryptByTNameAndNS(process.env.KClientSecret);
}
exports.getClientSecret = getClientSecret;
function getOpenapiDomain() {
    return getHttpConfig().getOpenapiHost();
}
exports.getOpenapiDomain = getOpenapiDomain;
function getFaasinfraDomain() {
    return getHttpConfig().getFaasinfraHost();
}
exports.getFaasinfraDomain = getFaasinfraDomain;
function decryptByTNameAndNS(encryptedText) {
    let tenantName = getTenantNameFromCtx();
    if (!tenantName) {
        throw new exceptions_1.InternalError('tenantName is empty');
    }
    // has check inner
    let namespace = getNamespaceFromCtx();
    let key = paddingN(tenantName + namespace, 32);
    return aesDecryptText(0, key, encryptedText);
}
exports.decryptByTNameAndNS = decryptByTNameAndNS;
function decryptBySvcIDAndNS(encryptedText) {
    let serviceID = getServiceId();
    let namespace = getNamespaceFromCtx();
    let key = paddingN(serviceID + namespace, 32);
    return aesDecryptText(0, key, encryptedText);
}
exports.decryptBySvcIDAndNS = decryptBySvcIDAndNS;
function paddingN(str, size) {
    if (str.length >= size) {
        return str.substr(0, size);
    }
    for (let i = str.length; i < size; i++) {
        str += '0';
    }
    return str;
}
exports.paddingN = paddingN;
function aesDecryptText(fieldID, encryptedKey, encryptedText) {
    // 限制 key 为 32 位
    if (encryptedKey.length !== 32) {
        throw new exceptions_1.InvalidParamError('length of encryptedKey is illegal');
    }
    // md5 算对应向量 得到对应的 16进制
    let initialVector = CryptoJS.MD5(`${fieldID}`).toString();
    // check 需要解密的文本
    if (encryptedText.length && encryptedText.length % 2 !== 0) {
        throw new exceptions_1.InvalidParamError(`length of text is illegal`);
    }
    // AES CBC 模式解密算法
    let decryptedText = aesCbcDecrypt(encryptedText, initialVector, encryptedKey);
    // 解密失败返回空串，抛异常感知
    if (!decryptedText) {
        throw new exceptions_1.InvalidParamError('decrypted text failed');
    }
    return decryptedText;
}
exports.aesDecryptText = aesDecryptText;
function hexDecode(hex) {
    const result = [];
    for (let i = 0; i < hex.length; i += 2) {
        result.push(String.fromCharCode(parseInt(hex.substr(i, 2), 16)));
    }
    return result.join('');
}
exports.hexDecode = hexDecode;
/**
 * 微服务环境变量解码
 * @param hexText 16进制文本
 * @param hexVector 16进制向量
 * @param utf8Key 解密秘钥
 */
function aesCbcDecrypt(hexText, hexVector, utf8Key) {
    // 解密文本: 16 进制 转 2 进制
    let bin = CryptoJS.enc.Hex.parse(hexText);
    // 解密文本: 2 进制 转 Base64
    let b64 = CryptoJS.enc.Base64.stringify(bin);
    // 加密 key: 2 进制 utf8 编码
    let key = CryptoJS.enc.Utf8.parse(utf8Key);
    // 向量: 16 进制转 2进制字符编码
    let iv = CryptoJS.enc.Hex.parse(hexVector);
    // AES CBC Pkcs7 解码
    let decryptedData = CryptoJS.AES.decrypt(b64, key, {
        iv: iv,
        mode: CryptoJS.mode.CBC,
        padding: CryptoJS.pad.Pkcs7
    });
    // 解密后的数据获得需要 toString
    let decryptedStr = decryptedData.toString();
    // decryptedStr 是16进制，需要转码
    return hexDecode(decryptedStr);
}
exports.aesCbcDecrypt = aesCbcDecrypt;
function formatAuthType(authType) {
    if (!authType) {
        // 如果接口级未设置，获取全局级的配置
        authType = getGlobalAuthType();
    }
    let userID = getUserIDFromCtx();
    if (userID === -1 || authType === constants_1.AuthTypeSystem) {
        return constants_1.AuthTypeSystem;
    }
    else if (authType === constants_1.AuthTypeUser) {
        return constants_1.AuthTypeUser;
    }
    else if (authType === constants_1.AuthTypeMixUserSystem) {
        return constants_1.AuthTypeMixUserSystem;
    }
    return undefined;
}
exports.formatAuthType = formatAuthType;
function getLaneID() {
    return nodeClsCtx.getLaneID();
}
exports.getLaneID = getLaneID;
function getEnvID() {
    return nodeClsCtx.getEnvID();
}
exports.getEnvID = getEnvID;
function getEnvType() {
    return nodeClsCtx.getEnvType();
}
exports.getEnvType = getEnvType;
function addLaneIDToHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    options.headers[constants_1.headers.LaneIDHeaderKey] = getLaneID();
}
exports.addLaneIDToHeader = addLaneIDToHeader;
function addEnvIDToHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    options.headers[constants_1.headers.EnvIDHeaderKey] = getEnvID();
}
exports.addEnvIDToHeader = addEnvIDToHeader;
function addFunctionAPIIDToHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    options.headers[constants_1.headers.FunctionAPIID] = getFunctionAPIID();
}
exports.addFunctionAPIIDToHeader = addFunctionAPIIDToHeader;
function addEnvTypeToHeader(options) {
    if (!options.headers) {
        options.headers = {};
    }
    options.headers[constants_1.headers.EnvTypeHeaderKey] = getEnvType();
}
exports.addEnvTypeToHeader = addEnvTypeToHeader;
function getHttpHeaders() {
    return nodeClsCtx.getHttpHeaders();
}
exports.getHttpHeaders = getHttpHeaders;
function getFuncMetaConf(apiName) {
    return nodeClsCtx.getFuncMetaConf(apiName);
}
exports.getFuncMetaConf = getFuncMetaConf;
function getCurFuncMetaConf() {
    return nodeClsCtx.getFuncMetaConf(getFuncAPIName());
}
exports.getCurFuncMetaConf = getCurFuncMetaConf;
function getFuncAPIName() {
    return nodeClsCtx.getFuncAPIName();
}
exports.getFuncAPIName = getFuncAPIName;
function hasKeyPath(v, keyPath) {
    if (!v || !keyPath || !isObject(v) || keyPath.length === 0) {
        return false;
    }
    let temp = v;
    for (let key of keyPath) {
        if (!temp || !temp.hasOwnProperty(key)) {
            return false;
        }
        temp = temp[key];
    }
    return true;
}
exports.hasKeyPath = hasKeyPath;
function getValueByPath(v, keyPath) {
    if (!v || !keyPath || !isObject(v) || keyPath.length === 0) {
        return v;
    }
    let temp = v;
    for (let key of keyPath) {
        if (!temp || !temp.hasOwnProperty(key)) {
            return undefined;
        }
        temp = temp[key];
    }
    return temp;
}
exports.getValueByPath = getValueByPath;
function delKeyPath(v, keyPath) {
    if (!v || !keyPath || !isObject(v) || keyPath.length === 0) {
        return;
    }
    if (!hasKeyPath(v, keyPath)) {
        return;
    }
    const value = getValueByPath(v, keyPath.slice(0, keyPath.length - 1));
    delete value[keyPath[keyPath.length - 1]];
}
exports.delKeyPath = delKeyPath;
/**
 * 获取全局的鉴权类型，优先级低于接口级
 */
function getGlobalAuthType() {
    return process.env[constants_1.GlobalAuthTypeKey];
}
exports.getGlobalAuthType = getGlobalAuthType;
function isCloseMesh() {
    const sdkTransientConf = nodeClsCtx.getSDKTransientConf();
    if (!sdkTransientConf) {
        return false;
    }
    return !!sdkTransientConf.isCloseMesh;
}
exports.isCloseMesh = isCloseMesh;
function enableMesh() {
    if (isCloseMesh() || isDebug() || isExternal()) {
        return false;
    }
    return isTrueString(process.env[constants_1.EnvKeys.EnvKMeshHttp]) && isTrueString(process.env[constants_1.EnvKeys.EnvKMeshUDS]) && getSocketAddr() != '';
}
exports.enableMesh = enableMesh;
function isTrueString(v) {
    if (!v) {
        return false;
    }
    return 'true' === v.toString().toLowerCase();
}
exports.isTrueString = isTrueString;
function getSocketAddr() {
    const socketAddr = process.env[constants_1.EnvKeys.EnvKSocketAddr];
    if (!socketAddr) {
        return '';
    }
    return socketAddr.trim();
}
exports.getSocketAddr = getSocketAddr;
function isExternal() {
    const faasType = getFaaSType();
    return faasType === constants_1.faaSAccessType.AliyunFcAccessType || faasType === constants_1.faaSAccessType.ByteFaaSExternalAccessType;
}
exports.isExternal = isExternal;
function getTraceHeader() {
    return {
        traceparent: nodeClsCtx.getReqCtx().sysHeaders[constants_1.headers.traceParentKey],
        tracestate: nodeClsCtx.getReqCtx().sysHeaders[constants_1.headers.traceStateKey],
    };
}
exports.getTraceHeader = getTraceHeader;
function setSDKInfo(fromSDK, fromVersion) {
    nodeClsCtx.setSDKInfo(fromSDK, fromVersion);
}
exports.setSDKInfo = setSDKInfo;
function getInnerapiAPIPSM() {
    return process.env.KInnerAPIPSM;
}
exports.getInnerapiAPIPSM = getInnerapiAPIPSM;
function getLGWPSM() {
    return process.env.KLGWPSM;
}
exports.getLGWPSM = getLGWPSM;
function getLGWCluster() {
    return process.env.KLGWCluster;
}
exports.getLGWCluster = getLGWCluster;
function getFaaSInfraPSM() {
    return process.env.KFaaSInfraPSM;
}
exports.getFaaSInfraPSM = getFaaSInfraPSM;
function isTmpUseLGW() {
    return (0, nodeClsCtx_1.getReqCtx)() && (0, nodeClsCtx_1.getReqCtx)()._temp_use_agw && (0, nodeClsCtx_1.getReqCtx)()._temp_use_agw == "true";
}
exports.isTmpUseLGW = isTmpUseLGW;
function getOpenAPIPSMAndCluster() {
    return { psm: getLGWPSM(), cluster: getLGWCluster() };
}
exports.getOpenAPIPSMAndCluster = getOpenAPIPSMAndCluster;
function getFaaSInfraPSMAndCluster() {
    return { psm: getFaaSInfraPSM(), cluster: "default" };
}
exports.getFaaSInfraPSMAndCluster = getFaaSInfraPSMAndCluster;
function getServerInfo(server) {
    if (server === 'openapi') {
        return getOpenAPIPSMAndCluster();
    }
    else if (server === 'faasinfra') {
        return getFaaSInfraPSMAndCluster();
    }
    throwInternalError(`server (${server}) not in [openapi, faasinfra]`);
    return undefined;
}
exports.getServerInfo = getServerInfo;
function getMeshDestReqTimeout() {
    const conf = nodeClsCtx.getSDKTransientConf();
    if (conf && conf.meshDestReqTimeout > 0) {
        return conf.meshDestReqTimeout;
    }
    // 默认 60s
    return constants_1.DEFAULT_MESH_DEST_REQ_TIMEOUT;
}
exports.getMeshDestReqTimeout = getMeshDestReqTimeout;
function sleepMs(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
exports.sleepMs = sleepMs;
