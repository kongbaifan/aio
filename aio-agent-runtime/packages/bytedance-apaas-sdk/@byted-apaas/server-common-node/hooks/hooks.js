"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.error = exports.post = exports.invoke = exports.pre = void 0;
const vefaas_logger_1 = require("../utils/vefaas_logger");
const utils = require("../utils/utils");
const utils_1 = require("../utils/utils");
const exceptions = require("../utils/exceptions");
const httpConfig = require("../http/config");
const checkUtils = require("../utils/checkUtils");
const resultUtils = require("../utils/resultUtils");
const nodeClsCtx = require("../utils/nodeClsCtx");
const logger_1 = require("../utils/logger");
const paramHandler = require("./paramHandler");
const constants = require("../constants/constants");
const context_1 = require("../context/context");
const workflowHandler = require("./workflowHandler");
const timeZone_1 = require("../constants/timeZone");
const countryCode_1 = require("../constants/countryCode");
const tool_1 = require("../kunlun/tool/impl/tool");
const kunlun_1 = require("../kunlun/kunlun");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
const functionTriggerType = constants.functionTriggerType;
const headers = constants.headers;
const constants_1 = require("../constants/constants");
const permissionUtils = require("../utils/permissionUtils");
const pressure_1 = require("../http/pressure");
function mountApplication() {
    if (!global.application) {
        global.application = {};
    }
    if (!global.application.constants) {
        global.application.constants = {};
    }
    global.application.constants.type = kunlun_1.kunlun.type;
    global.application.constants.errorCode = kunlun_1.kunlun.errorCode;
    global.application.constants.GMTOffset = timeZone_1.GMTOffset;
    global.application.constants.countryCode = countryCode_1.area2code;
    if (!global.application.error) {
        global.application.error = {};
    }
    global.application.error.FunctionError = exceptions.FunctionError;
    global.application.error.ValidationError = exceptions.ValidError;
    global.application.error.RateLimitError = exceptions.RateLimitError;
}
/**
 * 系统代理函数首先调用 common.pre 来初始化 kunlun 和 context 的部分实现
 * @param params      用户参数结构
 * @param context     common 的公共 context 结构
 * @param requireFunc
 */
async function pre(params, context, requireFunc) {
    // check sign for low-code access qfw intranet
    if (checkUtils.needCheckSign(context)) {
        checkUtils.checkTriggerSign(params, context);
    }
    // 参数归位
    [params, context] = paramHandler.handle(params, context);
    const copyCtx = context;
    const reqCtx = nodeClsCtx.getReqCtx();
    return await reqCtx.run(async () => {
        initRequestContext(context, requireFunc);
        // 对于非昆仑租户，重写console方法
        if (!(0, utils_1.isKunlunOrg)()) {
            if (!(0, utils_1.isDebug)()) {
                console.log = vefaas_logger_1.VeFaaSLogger.log;
                console.info = vefaas_logger_1.VeFaaSLogger.info;
                console.warn = vefaas_logger_1.VeFaaSLogger.warn;
                console.error = vefaas_logger_1.VeFaaSLogger.error;
            }
            context = {};
            for (const key of Object.keys(copyCtx)) {
                if (!Object.values(headers).includes(key) && !Object.values(constants_1.innerCtxKey).includes(key) && !context[key]) {
                    context[key] = copyCtx[key];
                }
            }
            return [params, context, null, reqCtx];
        }
        if (context.permission) {
            await permissionUtils.appendUnauthFieldToParams(utils.getFuncAPIName(), 'input', params, context.permission._unauthFields);
        }
        mountApplication();
        if (!global.kunlun) {
            global.kunlun = {};
        }
        // 挂在 kunlun 类型 & 错误码
        global.kunlun.type = kunlun_1.kunlun.type;
        global.kunlun.errorCode = kunlun_1.kunlun.errorCode;
        // 初始化 kunlun
        let inspirecloud = (global.inspirecloud);
        if (inspirecloud) {
            // 使用 as any 是因为不希望对用户暴露，因此不存在 env 的声明
            global.kunlun.env = inspirecloud.env;
            global.kunlun.redis = inspirecloud.redis;
            global.kunlun.mongodb = inspirecloud.db;
            global.kunlun.oss = inspirecloud.file;
        }
        if (!global.kunlun.env) {
            global.kunlun.env = utils.getEnv();
        }
        // 使用 as any 是因为不希望对用户暴露，因此不存在 boe, getCurrentEnv, getCurrentEnvWithBoe 的声明
        global.kunlun.boe = (0, utils_1.getBoe)();
        global.kunlun.getCurrentEnv = utils_1.getEnv;
        global.kunlun.getCurrentEnvWithBoe = utils_1.getEnvWithBoe;
        // 使用 as any 是因为 GMTOffset、countryCode 定义为常量，无法修改
        global.kunlun.GMTOffset = timeZone_1.GMTOffset;
        global.kunlun.countryCode = countryCode_1.area2code;
        global.kunlun.tool = new tool_1.Tool();
        // 初始化全局异常类, 使用 as any 是因为全局没有声明，需要增加
        // TODO 增加 global 下的 Error 声明
        global.FunctionError = exceptions.FunctionError;
        global.ValidationError = exceptions.ValidError;
        global.RateLimitError = exceptions.RateLimitError;
        // 初始化 context, 采用全面的 context 挂载方式
        if (context) {
            (0, utils_1.getOrSetFlowVersion)({ flow: context.flow, workflow: context.workflow });
        }
        const tenant = utils.getTenant(), app = utils.getApp(), user = utils.getUser(), event = utils.getEvent();
        context = new context_1.Context(context, tenant, app, user, event, utils.getHttpMethod());
        // 兼容老 common 逻辑，context 需要保有 sysHeaders 属性
        const source = (0, utils_1.getSource)();
        context.source = source;
        context.sysHeaders = {};
        context.sysHeaders[`${headers.distributedHandleMask}`] = utils.getDistributedHandleMask();
        context.sysHeaders[`${headers.globalVariablesKey}`] = utils.getGlobalVariable();
        context.sysHeaders.method = utils.getHttpMethod();
        context.set = utils.setHttpHeaders;
        // 防止 context.下的属性 被串改
        Object.freeze(context.sysHeaders);
        Object.freeze(context.tenant);
        Object.freeze(context.user);
        // 初始化 http 配置
        httpConfig.initHttpConf();
        // lane
        if (process.env._LANE_NAME_) {
            utils.setXTTEnvOnlyDebug(process.env._LANE_NAME_);
        }
        else if (process.env.X_TT_ENV) {
            utils.setXTTEnvOnlyDebug(process.env.X_TT_ENV);
        }
        let logger = new logger_1.Logger();
        return [params, context, logger, reqCtx];
    });
}
exports.pre = pre;
async function invoke(userFunc, params, context, logger) {
    if (nodeClsCtx.getPressureNeedDecelerate()) { // 初始化反压中心降速类
        const config = (0, pressure_1.newPressureConfigByJsonStr)(nodeClsCtx.getPressureConfig());
        (0, pressure_1.initPressureDecelerator)(nodeClsCtx.getReqCtx(), config);
    }
    let loopCtx = nodeCls.get('loopCtx');
    if (loopCtx && loopCtx.loopMasks && Array.isArray(loopCtx.loopMasks)) {
        return await userFunc(params, context, logger);
    }
    else {
        let loopMasks = utils.getLoopMasks();
        loopCtx = nodeCls.create('loopCtx');
        return await loopCtx.run(async () => {
            loopCtx.loopMasks = loopMasks;
            // 防止 context 被串改
            Object.freeze(context);
            return await userFunc(params, context, logger);
        });
    }
}
exports.invoke = invoke;
async function post(response, params, context, logger) {
    if (response === undefined || response === null) {
        if (logger)
            await logger.sendLog();
        return resultUtils.success(null);
    }
    // 用户返回的错误
    if (exceptions.IsInstanceOfError(response, exceptions.errTypes.UserBaseError)) {
        if (logger)
            await logger.sendLog();
        return resultUtils.failure(response);
    }
    const flowVersion = utils.getOrSetFlowVersion(context);
    if (flowVersion === 'v1') {
        switch (utils.getTriggerType()) {
            case functionTriggerType.Action:
            case functionTriggerType.ScheduleAutomation:
            case functionTriggerType.RecordAutomation:
            case functionTriggerType.Connector: {
                if (checkUtils.isNotObject(response)) {
                    throw new exceptions.InvalidParamError("return's value must be object");
                }
                workflowHandler.handleResponse(context, response);
            }
        }
    }
    // 防止用户返回数据成环, 返回开发者错误
    try {
        JSON.stringify(response);
    }
    catch {
        throw new exceptions.DeveloperResponseCircularError();
    }
    if (logger)
        await logger.sendLog();
    const permission = await permissionUtils.delParamsUnauthField(utils.getFuncAPIName(), 'output', response);
    return resultUtils.success(response, permission);
}
exports.post = post;
async function error(err, params, context, logger) {
    utils.handleErrorMsg(err);
    if (logger) {
        if (err instanceof Error) {
            // 用户代码问题，系统直接 throw，补全日志错误码和 logid 信息
            if (!exceptions.IsInstanceOfError(err, exceptions.errTypes.BaseError)) {
                err.message = exceptions.appendLogID(`${err.message} [${exceptions.errCodes.DEVELOPER_ERROR}]`);
            }
            if (exceptions.IsInstanceOfError(err, exceptions.errTypes.DeveloperResponseCircularError)) {
                logger.error(err.message);
            }
            else {
                logger.error(err.stack);
            }
        }
        else {
            logger.error(err);
        }
    }
    if (logger)
        await logger.sendLog();
    // 包括：所有平台问题（系统错误和业务错误）
    if (exceptions.IsInstanceOfError(err, exceptions.errTypes.BaseError)) {
        return resultUtils.failure(err);
    }
    return resultUtils.developerError(err);
}
exports.error = error;
function initRequestContext(context, requireFunc) {
    nodeClsCtx.add('tenant', paramHandler.parseTenantByContext(context));
    nodeClsCtx.add('app', paramHandler.parseAppByContext(context));
    nodeClsCtx.add('user', paramHandler.parseUserByContext(context));
    nodeClsCtx.add('event', paramHandler.getEventByContext(context));
    nodeClsCtx.add('metrics', []);
    nodeClsCtx.add('env', paramHandler.parseEnv());
    nodeClsCtx.add('boe', paramHandler.parseBoeByContext(context));
    nodeClsCtx.add('serviceID', paramHandler.parseServiceIDByContext(context));
    nodeClsCtx.add('sysHeaders', context.sysHeaders);
    nodeClsCtx.add('headers', context.headers);
    // sysHeaders: logID, loggerInfo, source, triggerType, deployedGlobalFuncNames, deployedGlobalFuncMap
    nodeClsCtx.add('responseHeaders', context.responseHeaders);
    nodeClsCtx.add('requireFunc', requireFunc);
    nodeClsCtx.add('unauthFields', {});
}
