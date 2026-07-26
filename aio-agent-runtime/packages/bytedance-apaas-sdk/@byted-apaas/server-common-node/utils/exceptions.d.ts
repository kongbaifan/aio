import { _LanguageType, Multilingual } from '../kunlun/type/type';
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
declare enum errTypes {
    UserBaseError = "UserBaseError",
    FunctionError = "FunctionError",
    ValidError = "ValidError",
    BaseError = "BaseError",
    SystemError = "SystemError",
    InternalError = "InternalError",
    UnknownError = "UnknownError",
    TokenExpireError = "TokenExpireError",
    NoAuthError = "NoAuthError",
    ParamError = "ParamError",
    UnmarshalError = "UnmarshalError",
    CallHttpConnectError = "CallHttpConnectError",
    CallOpenapiError = "CallOpenapiError",
    CallFaasinfraError = "CallFaasinfraError",
    RateLimitError = "RateLimitError",
    BusinessError = "BusinessError",
    InvalidParamError = "InvalidParamError",
    GlobalVariableError = "GlobalVariableError",
    DeveloperBugError = "DeveloperBugError",
    DeveloperResponseCircularError = "DeveloperResponseCircularError",
    ParamWarn = "ParamWarn",
    DeveloperBugWarn = "DeveloperBugWarn",
    GlobalVariableWarn = "GlobalVariableWarn"
}
declare enum errCodes {
    FUNCTION_ERROR = "k_cf_ec_100001",
    VALIDATION_ERROR = "k_cf_ec_100002",
    DEVELOPER_ERROR = "k_cf_ec_400001783",
    INTERNAL_ERROR = "k_cf_ec_200001",
    Flows_NoPermission = "k_wf_ec_200036",
    Flows_NotExist = "k_wf_ec_2001006",
    Flows_ExecutionNotExist = "k_wf_ec_2001005",
    Flows_NotSupportCallFlowType = "k_wf_ec_2001004",
    Flows_NotSupportRevokeFlow = "k_wf_ec_2001003",
    Flows_NoReqInputParamErr = "k_wf_ec_2001002",
    Flows_InvalidParamErr = "k_wf_ec_2001001",
    /** @deprecated */
    RATE_LIMIT_ERROR = "k_cf_ec_200009",
    /** @deprecated */
    OPENAPI_RATE_LIMIT_ERROR = "k_op_ec_20003",
    /** @deprecated */
    FAASINFRA_RATE_LIMIT_ERROR = "k_fs_ec_000004",
    /** @deprecated */
    INVALID_PARAM_ERROR = "k_cf_ec_300001",
    /** @deprecated */
    GLOBAL_VARIABLE_ERROR = "k_cf_ec_30003",
    /** @deprecated */
    TOKEN_EXPIRE_ERROR = "k_cf_ec_200002",
    /** @deprecated */
    AUTH_ERROR = "k_cf_ec_200003",
    /** @deprecated */
    UNMARSHAL_ERROR = "k_cf_ec_200005",
    /** @deprecated */
    CALL_OPENAPI_ERROR = "k_cf_ec_200006",
    /** @deprecated */
    CALL_FAASINFRA_ERROR = "k_cf_ec_200007",
    /** @deprecated */
    CALL_HTTP_CONNECTION_ERROR = "k_cf_ec_200008"
}
/**
 * 用户return的error
 * msg 为 Multilingual
 */
declare class UserBaseError {
    code: string;
    type: string[];
    msg: string | _LanguageType[];
    constructor(code: string, message: Multilingual);
}
/**
 * 函数错误类
 */
declare class FunctionError extends UserBaseError {
    /**
     * 函数错误类
     * @param message 错误信息
     */
    constructor(message: Multilingual);
}
/**
 * 不合法错误类
 */
declare class ValidError extends UserBaseError {
    /**
     * 不合法错误类
     * @param message 错误信息
     */
    constructor(message: Multilingual);
}
declare class BaseError extends Error {
    code: string;
    msg: string;
    notRetry: boolean;
    type: string[];
    constructor(code: string, message: string, notRetry?: boolean);
}
declare class SystemError extends BaseError {
    constructor(code: string, message: string, notRetry?: boolean);
}
declare class InternalError extends SystemError {
    constructor(message: string);
}
/**
 * @deprecated
 */
declare class UnknownError extends SystemError {
    constructor(message: string);
}
/**
 * @deprecated
 */
declare class TokenExpireError extends SystemError {
    constructor();
}
declare class NoAuthError extends SystemError {
    constructor(message: string);
}
/**
 * @deprecated
 */
declare class ParamError extends SystemError {
    constructor(message: string);
}
declare class UnmarshalError extends SystemError {
    constructor(message: string);
}
declare class CallHttpConnectError extends SystemError {
    constructor(message: string);
}
declare class CallOpenapiError extends SystemError {
    constructor(message: string);
}
declare class CallFaasinfraError extends SystemError {
    constructor(message: string);
}
/** @deprecated */
declare class RateLimitError extends SystemError {
    /**
     * 限流异常类
     * @param message 错误信息
     */
    constructor(message: string);
}
declare class BusinessError extends BaseError {
    constructor(code: string, message: string, notRetry?: boolean);
}
declare class InvalidParamError extends BusinessError {
    constructor(message: string);
}
/** @deprecated */
declare class GlobalVariableError extends BusinessError {
    constructor(message: string);
}
declare class DeveloperBugError extends BusinessError {
    constructor(message: string);
}
declare class DeveloperResponseCircularError extends BusinessError {
    constructor();
}
/**
 * @deprecated
 */
declare class ParamWarn extends BusinessError {
    constructor(message: string);
}
/**
 * @deprecated
 */
declare class DeveloperBugWarn extends BusinessError {
    constructor(message: string);
}
/**
 * @deprecated
 */
declare class GlobalVariableWarn extends BusinessError {
    constructor(message: string);
}
declare global {
    /**
     * 限流异常类
     */
    class RateLimitError extends SystemError {
        /**
         * 限流异常类
         * @param message 错误信息
         */
        constructor(message: string);
    }
    /**
     * 函数错误类
     */
    class FunctionError extends UserBaseError {
        /**
         * 函数错误类
         * @param message 错误信息
         */
        constructor(message: Multilingual);
    }
    /**
     * 不合法错误类
     */
    class ValidationError extends UserBaseError {
        /**
         * 不合法错误类
         * @param message 错误信息
         */
        constructor(message: Multilingual);
    }
}
declare function IsInstanceOfError(err: any, eType: errTypes): any;
declare function appendLogID(message: any): any;
export { errCodes, errTypes, IsInstanceOfError, appendLogID, UserBaseError, BaseError, FunctionError, ValidError, SystemError, InternalError, UnknownError, TokenExpireError, NoAuthError, ParamError, UnmarshalError, CallOpenapiError, CallFaasinfraError, CallHttpConnectError, RateLimitError, BusinessError, InvalidParamError, DeveloperBugError, DeveloperResponseCircularError, GlobalVariableError, ParamWarn, DeveloperBugWarn, GlobalVariableWarn, };
