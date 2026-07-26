"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.GlobalVariableWarn = exports.DeveloperBugWarn = exports.ParamWarn = exports.GlobalVariableError = exports.DeveloperResponseCircularError = exports.DeveloperBugError = exports.InvalidParamError = exports.BusinessError = exports.RateLimitError = exports.CallHttpConnectError = exports.CallFaasinfraError = exports.CallOpenapiError = exports.UnmarshalError = exports.ParamError = exports.NoAuthError = exports.TokenExpireError = exports.UnknownError = exports.InternalError = exports.SystemError = exports.ValidError = exports.FunctionError = exports.BaseError = exports.UserBaseError = exports.appendLogID = exports.IsInstanceOfError = exports.errTypes = exports.errCodes = void 0;
const type_1 = require("../kunlun/type/type");
function isKFieldTypeMultilingual() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../kunlun/type/type').isKFieldTypeMultilingual;
}
function getUtils() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('./utils');
}
/**
 * 目前管理的异常有3类
 *
 * 1.用户返回。不可以throw
 *      return new FunctionError()
 * 2.系统错误，即框架层throw
 *      调用openapi错误，应该：throw new CallOpenapiError()
 * 3.业务错误，用户操作异常throw
 *      比如用户参数不合法，应该：throw new InvalidParamError()
 */
var errTypes;
(function (errTypes) {
    errTypes["UserBaseError"] = "UserBaseError";
    errTypes["FunctionError"] = "FunctionError";
    errTypes["ValidError"] = "ValidError";
    errTypes["BaseError"] = "BaseError";
    errTypes["SystemError"] = "SystemError";
    errTypes["InternalError"] = "InternalError";
    errTypes["UnknownError"] = "UnknownError";
    errTypes["TokenExpireError"] = "TokenExpireError";
    errTypes["NoAuthError"] = "NoAuthError";
    errTypes["ParamError"] = "ParamError";
    errTypes["UnmarshalError"] = "UnmarshalError";
    errTypes["CallHttpConnectError"] = "CallHttpConnectError";
    errTypes["CallOpenapiError"] = "CallOpenapiError";
    errTypes["CallFaasinfraError"] = "CallFaasinfraError";
    errTypes["RateLimitError"] = "RateLimitError";
    errTypes["BusinessError"] = "BusinessError";
    errTypes["InvalidParamError"] = "InvalidParamError";
    errTypes["GlobalVariableError"] = "GlobalVariableError";
    errTypes["DeveloperBugError"] = "DeveloperBugError";
    errTypes["DeveloperResponseCircularError"] = "DeveloperResponseCircularError";
    errTypes["ParamWarn"] = "ParamWarn";
    errTypes["DeveloperBugWarn"] = "DeveloperBugWarn";
    errTypes["GlobalVariableWarn"] = "GlobalVariableWarn";
})(errTypes || (errTypes = {}));
exports.errTypes = errTypes;
var errCodes;
(function (errCodes) {
    // User return error
    errCodes["FUNCTION_ERROR"] = "k_cf_ec_100001";
    errCodes["VALIDATION_ERROR"] = "k_cf_ec_100002";
    // User business error
    errCodes["DEVELOPER_ERROR"] = "k_cf_ec_400001783";
    // System error
    errCodes["INTERNAL_ERROR"] = "k_cf_ec_200001";
    // For developer error code
    //  无权限操作流程
    errCodes["Flows_NoPermission"] = "k_wf_ec_200036";
    // 流程不存在
    errCodes["Flows_NotExist"] = "k_wf_ec_2001006";
    //  流程实例 ID 不存在
    errCodes["Flows_ExecutionNotExist"] = "k_wf_ec_2001005";
    //  不支持调用此类型流程
    errCodes["Flows_NotSupportCallFlowType"] = "k_wf_ec_2001004";
    //  不支持撤销该流程 (无人工任务)
    errCodes["Flows_NotSupportRevokeFlow"] = "k_wf_ec_2001003";
    //  缺少流程的必填参数
    errCodes["Flows_NoReqInputParamErr"] = "k_wf_ec_2001002";
    //  流程参数中 APIName 无效
    errCodes["Flows_InvalidParamErr"] = "k_wf_ec_2001001";
    /** @deprecated */
    errCodes["RATE_LIMIT_ERROR"] = "k_cf_ec_200009";
    /** @deprecated */
    errCodes["OPENAPI_RATE_LIMIT_ERROR"] = "k_op_ec_20003";
    /** @deprecated */
    errCodes["FAASINFRA_RATE_LIMIT_ERROR"] = "k_fs_ec_000004";
    /** @deprecated */
    errCodes["INVALID_PARAM_ERROR"] = "k_cf_ec_300001";
    /** @deprecated */
    errCodes["GLOBAL_VARIABLE_ERROR"] = "k_cf_ec_30003";
    /** @deprecated */
    errCodes["TOKEN_EXPIRE_ERROR"] = "k_cf_ec_200002";
    /** @deprecated */
    errCodes["AUTH_ERROR"] = "k_cf_ec_200003";
    /** @deprecated */
    errCodes["UNMARSHAL_ERROR"] = "k_cf_ec_200005";
    /** @deprecated */
    errCodes["CALL_OPENAPI_ERROR"] = "k_cf_ec_200006";
    /** @deprecated */
    errCodes["CALL_FAASINFRA_ERROR"] = "k_cf_ec_200007";
    /** @deprecated */
    errCodes["CALL_HTTP_CONNECTION_ERROR"] = "k_cf_ec_200008";
})(errCodes || (errCodes = {}));
exports.errCodes = errCodes;
/**
 * 用户return的error
 * msg 为 Multilingual
 */
class UserBaseError {
    constructor(code, message) {
        this.code = code;
        this.type = new Array(0);
        this.type.push(errTypes.UserBaseError);
        // instanceof 改动4
        // if (message instanceof Multilingual) {
        if (isKFieldTypeMultilingual()(message)) {
            this.msg = message.toJSON();
        }
        else {
            this.msg = new type_1.Multilingual(message).toJSON();
        }
    }
}
exports.UserBaseError = UserBaseError;
/**
 * 函数错误类
 */
class FunctionError extends UserBaseError {
    /**
     * 函数错误类
     * @param message 错误信息
     */
    constructor(message) {
        super(errCodes.FUNCTION_ERROR, message);
        this.type.push(errTypes.UserBaseError);
    }
}
exports.FunctionError = FunctionError;
/**
 * 不合法错误类
 */
class ValidError extends UserBaseError {
    /**
     * 不合法错误类
     * @param message 错误信息
     */
    constructor(message) {
        super(errCodes.VALIDATION_ERROR, message);
        this.type.push(errTypes.ValidError);
    }
}
exports.ValidError = ValidError;
class BaseError extends Error {
    constructor(code, message, notRetry = false) {
        super(appendLogID(`${message} [${code}]`));
        this.type = new Array(0);
        this.type.push(errTypes.BaseError);
        this.code = code;
        this.msg = message;
        this.notRetry = notRetry;
    }
}
exports.BaseError = BaseError;
// 框架层throw的error
class SystemError extends BaseError {
    constructor(code, message, notRetry = false) {
        super(code, message, notRetry);
        this.type.push(errTypes.SystemError);
    }
}
exports.SystemError = SystemError;
class InternalError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.InternalError);
    }
}
exports.InternalError = InternalError;
/**
 * @deprecated
 */
class UnknownError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.UnknownError);
    }
}
exports.UnknownError = UnknownError;
/**
 * @deprecated
 */
class TokenExpireError extends SystemError {
    constructor() {
        super(errCodes.INTERNAL_ERROR, `token expire`);
        this.type.push(errTypes.TokenExpireError);
    }
}
exports.TokenExpireError = TokenExpireError;
class NoAuthError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.NoAuthError);
    }
}
exports.NoAuthError = NoAuthError;
/**
 * @deprecated
 */
class ParamError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.ParamError);
    }
}
exports.ParamError = ParamError;
class UnmarshalError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.UnmarshalError);
    }
}
exports.UnmarshalError = UnmarshalError;
class CallHttpConnectError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.CallHttpConnectError);
    }
}
exports.CallHttpConnectError = CallHttpConnectError;
class CallOpenapiError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.CallOpenapiError);
    }
}
exports.CallOpenapiError = CallOpenapiError;
class CallFaasinfraError extends SystemError {
    constructor(message) {
        super(errCodes.INTERNAL_ERROR, message);
        this.type.push(errTypes.CallFaasinfraError);
    }
}
exports.CallFaasinfraError = CallFaasinfraError;
/** @deprecated */
class RateLimitError extends SystemError {
    /**
     * 限流异常类
     * @param message 错误信息
     */
    constructor(message) {
        super(errCodes.RATE_LIMIT_ERROR, message, true);
        this.type.push(errTypes.RateLimitError);
    }
}
exports.RateLimitError = RateLimitError;
// 业务错误
class BusinessError extends BaseError {
    constructor(code, message, notRetry = false) {
        super(code, message, notRetry);
        this.type.push(errTypes.BusinessError);
    }
}
exports.BusinessError = BusinessError;
class InvalidParamError extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.InvalidParamError);
    }
}
exports.InvalidParamError = InvalidParamError;
/** @deprecated */
class GlobalVariableError extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.GlobalVariableError);
    }
}
exports.GlobalVariableError = GlobalVariableError;
class DeveloperBugError extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.DeveloperBugError);
    }
}
exports.DeveloperBugError = DeveloperBugError;
class DeveloperResponseCircularError extends BusinessError {
    constructor() {
        super(errCodes.DEVELOPER_ERROR, 'Invalid Function Response: circular structure');
        this.type.push(errTypes.DeveloperResponseCircularError);
    }
}
exports.DeveloperResponseCircularError = DeveloperResponseCircularError;
// -------------下面的即将废弃，不建议再使用了--------------------
/**
 * @deprecated
 */
class ParamWarn extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.ParamWarn);
    }
}
exports.ParamWarn = ParamWarn;
/**
 * @deprecated
 */
class DeveloperBugWarn extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.DeveloperBugWarn);
    }
}
exports.DeveloperBugWarn = DeveloperBugWarn;
/**
 * @deprecated
 */
class GlobalVariableWarn extends BusinessError {
    constructor(message) {
        super(errCodes.DEVELOPER_ERROR, message);
        this.type.push(errTypes.GlobalVariableWarn);
    }
}
exports.GlobalVariableWarn = GlobalVariableWarn;
function IsInstanceOfError(err, eType) {
    if (err && err.hasOwnProperty && err.hasOwnProperty('type') && Array.isArray(err.type)) {
        return err.type.includes(eType);
    }
    return false;
}
exports.IsInstanceOfError = IsInstanceOfError;
function appendLogID(message) {
    if (message instanceof Error) {
        if (message.message && typeof message.message.includes === 'function' && !message.message.includes('(logID=')) {
            message.message += `(logID=${getUtils().getLogID()})`;
        }
        return message;
    }
    else if (IsInstanceOfError(message, errTypes.UserBaseError)) {
        return message;
    }
    return (message && typeof message === 'string' && message.includes('(logID=')) ? message : message + `(logID=${getUtils().getLogID()})`;
}
exports.appendLogID = appendLogID;
