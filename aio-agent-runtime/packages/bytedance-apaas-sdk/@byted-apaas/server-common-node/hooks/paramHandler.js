"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.parseEnv = exports.parseSource = exports.parseBoeByContext = exports.getEventByContext = exports.parseAppByContext = exports.parseUserByContext = exports.parseTenantByContext = exports.parseServiceIDByContext = exports.handle = void 0;
const checkUtils = require("../utils/checkUtils");
const constants_1 = require("../constants/constants");
const exceptions = require("../utils/exceptions");
const querystring = require("querystring");
/**
 * params: {
 *     params: 用户参数，需要替换外层的params
 *     context: 上下文参数，需要把值添加到context下
 * }
 *
 * @param params
 * @param context
 * @returns {Promise<*[]>}
 */
function handle(params, context) {
    // 1.参数归位
    if (params) {
        if (params.context) {
            for (let key of Object.keys(params.context)) {
                context[key] = params.context[key];
                context.headers[key] = params.context[key];
            }
        }
        params = params.params;
    }
    // 2.拆分headers
    splitHeaders(context);
    return [params, context];
}
exports.handle = handle;
// 2.拆分headers：context.headers表示用户headers，context.sysHeaders表示系统headers
function splitHeaders(context) {
    const papiPrefix = 'papi-';
    const customHeaders = {};
    if (!context.sysHeaders) {
        context.sysHeaders = {};
    }
    for (let key of Object.keys(context.headers)) {
        let value = context.headers[key];
        if (key.startsWith(papiPrefix)) {
            customHeaders[key.slice(papiPrefix.length)] = value;
        }
        else {
            context.sysHeaders[key] = value;
        }
    }
    context.headers = customHeaders;
}
function parseServiceIDByContext(context) {
    if (context && context.sysHeaders && context.sysHeaders[constants_1.headers.serviceId]) {
        return context.sysHeaders[constants_1.headers.serviceId];
    }
    return '';
}
exports.parseServiceIDByContext = parseServiceIDByContext;
function parseTenantByContext(context) {
    // check context
    checkUtils.checkHeaders(context);
    let tenant = null;
    try {
        tenant = JSON.parse(context.sysHeaders[constants_1.headers.tenant]);
        delete context.sysHeaders[constants_1.headers.tenant];
    }
    catch (e) {
        throw new exceptions.InternalError('an error occurred while parsing tenant: ' + e.message);
    }
    Object.freeze(tenant);
    return tenant;
}
exports.parseTenantByContext = parseTenantByContext;
function parseUserByContext(context) {
    // check context
    checkUtils.checkHeaders(context);
    let user = null;
    try {
        user = JSON.parse(context.sysHeaders[constants_1.headers.initiator]);
        delete context.sysHeaders[constants_1.headers.initiator];
    }
    catch (e) {
        throw new exceptions.InternalError('an error occurred while parsing initiator: ' + e.message);
    }
    Object.freeze(user);
    return user;
}
exports.parseUserByContext = parseUserByContext;
function parseAppByContext(context) {
    // check context
    checkUtils.checkHeaders(context);
    let app = null;
    try {
        if (context.sysHeaders[constants_1.headers.app]) {
            app = JSON.parse(querystring.unescape(context.sysHeaders[constants_1.headers.app]));
            delete context.sysHeaders[constants_1.headers.app];
        }
    }
    catch (e) {
        throw new exceptions.InternalError('an error occurred while parsing app: ' + e.message);
    }
    Object.freeze(app);
    return app;
}
exports.parseAppByContext = parseAppByContext;
function getEventByContext(context) {
    // check context
    checkUtils.checkHeaders(context);
    return context.event;
}
exports.getEventByContext = getEventByContext;
function parseBoeByContext(context) {
    if (context && context.sysHeaders && context.sysHeaders[constants_1.headers.boe]) {
        return context.sysHeaders[constants_1.headers.boe];
    }
    return '';
}
exports.parseBoeByContext = parseBoeByContext;
function parseSource(context) {
    if (context && context.sysHeaders && context.sysHeaders[constants_1.headers.source]) {
        return context.sysHeaders[constants_1.headers.source];
    }
    return '';
}
exports.parseSource = parseSource;
function parseEnv() {
    if (global.kunlun && global.kunlun.env && global.kunlun.env.sys__currentEnv) {
        return global.kunlun.env.sys__currentEnv;
    }
    if (global.inspirecloud && global.inspirecloud.env && global.inspirecloud.env.sys__currentEnv) {
        return global.inspirecloud.env.sys__currentEnv;
    }
    if (process.env.ENV !== undefined) {
        return process.env.ENV;
    }
    throw new exceptions.InternalError('env is empty');
}
exports.parseEnv = parseEnv;
