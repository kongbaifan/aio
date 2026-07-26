"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.checkTriggerSign = exports.needCheckSign = exports.checkFile = exports.checkWorkflowAndFlowVariableTypes = exports.checkWorkflowAndFlow = exports.checkInitiator = exports.checkTenant = exports.checkHeaders = exports.checkCtx = exports.isNotObject = exports.isObject = void 0;
function getConstant() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../constants/constants');
}
function getExceptions() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./exceptions');
}
function throwInternalError(msg) {
    throw new (getExceptions()).InternalError(msg);
}
function throwInvalidParamError(msg) {
    throw new (getExceptions()).InvalidParamError(msg);
}
/**
 * 仅仅是Object，不是Array
 *
 * @param value
 * @returns {boolean}
 */
function isObject(value) {
    if (value === null) {
        return false;
    }
    if (value instanceof Object) {
        if (!(value instanceof Array)) {
            return true;
        }
    }
    return false;
}
exports.isObject = isObject;
/**
 * 这里把数组认为也不是对象
 *
 * @param value
 */
function isNotObject(value) {
    if (value === null) {
        return true;
    }
    if (value instanceof Array) {
        return true;
    }
    return !(value instanceof Object);
}
exports.isNotObject = isNotObject;
/**
 * ctx不可以为空
 *
 * @param ctx
 */
function checkCtx(ctx) {
    if (!ctx) {
        throwInternalError('ctx is empty');
    }
    if (isNotObject(ctx)) {
        throwInternalError('ctx is not object');
    }
}
exports.checkCtx = checkCtx;
/**
 * 校验headers
 * 1.不可以为空
 * 2.是一个对象
 *
 * @param ctx
 */
function checkHeaders(ctx) {
    checkCtx(ctx);
    if (!ctx.sysHeaders) {
        throwInternalError('ctx.sysHeaders is empty');
    }
    if (isNotObject(ctx.sysHeaders)) {
        throwInternalError('ctx.sysHeaders is not object');
    }
}
exports.checkHeaders = checkHeaders;
/**
 * 校验tenant
 * 1.不可以为空
 * 2.有属性name，id, type
 *
 * @param ctx
 */
function checkTenant(ctx) {
    checkCtx(ctx);
    if (!ctx.tenant) {
        throwInternalError('ctx.tenant is empty');
    }
    if (!ctx.tenant.name) {
        throwInternalError('ctx.tenant.name is empty');
    }
    if (!ctx.tenant.id) {
        throwInternalError('ctx.tenant.id is empty');
    }
    if (!ctx.tenant.namespace) {
        throwInternalError('ctx.tenant.namespace is empty');
    }
}
exports.checkTenant = checkTenant;
/**
 * 校验initiator
 * 1.不可以为空
 * 2.有属性id
 *
 * @param ctx
 */
function checkInitiator(ctx) {
    checkCtx(ctx);
    if (!ctx.initiator) {
        throwInternalError('ctx.initiator is empty');
    }
    if (!ctx.initiator._id) {
        throwInternalError('ctx.initiator._id is empty');
    }
}
exports.checkInitiator = checkInitiator;
/**
 * 校验workflow
 * 1.不为空
 * 2.是对象
 * 3.instanceId不为空
 *
 * @param ctx
 */
function checkWorkflowAndFlow(ctx) {
    checkCtx(ctx);
    if (!ctx.workflow) {
        throwInternalError('context.workflow is empty');
    }
    if (isNotObject(ctx.workflow)) {
        throwInternalError(`context.workflow is not object, but ${typeof (ctx.workflow)}`);
    }
    if (!ctx.flow) {
        throwInternalError('context.flow is empty');
    }
    if (isNotObject(ctx.flow)) {
        throwInternalError(`context.flow is not object, but ${typeof (ctx.flow)}`);
    }
    const { isDebug } = require('./utils');
    if (!ctx.workflow.instanceId && !isDebug(ctx)) {
        throwInternalError('context.workflow.instanceId is empty');
    }
    if (!ctx.flow.instanceId && !isDebug(ctx)) {
        throwInternalError('context.flow.instanceId is empty');
    }
}
exports.checkWorkflowAndFlow = checkWorkflowAndFlow;
/**
 * 校验workflow.variables
 * 1.不为空
 * 2.是对象
 *
 * @param ctx
 * @param key
 */
function checkWorkflowAndFlowVariableTypes(ctx, key) {
    if (!key) {
        throwInvalidParamError('key is empty');
    }
    checkWorkflowAndFlow(ctx);
    if (!ctx.workflow.variableTypes) {
        throwInvalidParamError('workflow.variables is empty');
    }
    if (isNotObject(ctx.workflow.variableTypes)) {
        throwInvalidParamError('workflow.variables is not object');
    }
    // eslint-disable-next-line no-prototype-builtins
    if (!ctx.workflow.variableTypes.hasOwnProperty(key)) {
        throwInvalidParamError(`context.workflow.variables.${key} is not exist`);
    }
    if (isNotObject(ctx.workflow.variableTypes[key])) {
        throwInvalidParamError(`context.workflow.variables.${key} is not object, but ${typeof (ctx.workflow.variableTypes[key])}`);
    }
    // eslint-disable-next-line no-prototype-builtins
    if (!ctx.workflow.variableTypes[key].hasOwnProperty('type')) {
        throwInvalidParamError(`context.workflow.variables.${key}.type is empty`);
    }
    if (!ctx.flow.variableTypes) {
        throwInvalidParamError('flow.variables is empty');
    }
    if (isNotObject(ctx.flow.variableTypes)) {
        throwInvalidParamError('flow.variables is not object');
    }
    // eslint-disable-next-line no-prototype-builtins
    if (!ctx.flow.variableTypes.hasOwnProperty(key)) {
        throwInvalidParamError(`context.flow.variables.${key} is not exist`);
    }
    if (isNotObject(ctx.flow.variableTypes[key])) {
        throwInvalidParamError(`context.flow.variables.${key} is not object, but ${typeof (ctx.flow.variableTypes[key])}`);
    }
    // eslint-disable-next-line no-prototype-builtins
    if (!ctx.flow.variableTypes[key].hasOwnProperty('type')) {
        throwInvalidParamError(`context.flow.variables.${key}.type is empty`);
    }
}
exports.checkWorkflowAndFlowVariableTypes = checkWorkflowAndFlowVariableTypes;
function checkFile(file) {
    if (typeof (file) !== 'string') {
        throwInvalidParamError(`file name should be string`);
    }
    if (file.endsWith('/')) {
        throwInvalidParamError(`file name '${file}' is invalid`);
    }
}
exports.checkFile = checkFile;
function needCheckSign(ctx) {
    if (ctx && ctx.headers && ctx.headers[getConstant().headers.faasAccessType]) {
        if (ctx.headers[getConstant().headers.faasAccessType] === getConstant().faaSAccessType.InspirecloudIntranetAccessType) {
            return true;
        }
    }
    return false;
}
exports.needCheckSign = needCheckSign;
function checkTriggerSign(params, context) {
    // 1.get tenant
    let tenant = null;
    if (!context || !context.headers || !context.headers[getConstant().headers.tenant]) {
        throw new (getExceptions()).NoAuthError('Failed to authenticate: context.headers["x-kunlun-tenant"] is empty');
    }
    try {
        tenant = JSON.parse(context.headers[getConstant().headers.tenant]);
    }
    catch (e) {
        throw new (getExceptions()).NoAuthError('Failed to authenticate: an error occurred while parsing tenant, ' + e.message);
    }
    if (!tenant) {
        throw new (getExceptions()).NoAuthError('Failed to authenticate: context.headers["x-kunlun-tenant"].name is empty');
    }
    // 2.get sign
    if (!context.headers[getConstant().headers.signV2]) {
        throw new (getExceptions()).NoAuthError('Failed to authenticate: context.headers["x-kunlun-sign-v2"] is empty');
    }
    // 3.check
    const salt = Buffer.from(context.headers[getConstant().headers.signSalt], 'hex').toString('utf8');
    const hashContent = tenant.name + tenant.namespace + context.headers[getConstant().headers.invokeFuncName] + salt;
    const signReqV2 = context.headers[getConstant().headers.signV2];
    const signCur = require('crypto').createHash('sha256').update(hashContent).digest('hex').toUpperCase();
    if (signReqV2 !== signCur) {
        throw new (getExceptions()).NoAuthError('Failed to authenticate: signReq !== signCur');
    }
}
exports.checkTriggerSign = checkTriggerSign;
