"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.developerError = exports.unknown = exports.failure = exports.success = void 0;
const utils = require("./utils");
const exceptions = require("./exceptions");
class Result {
    constructor(code, msg, data, extraInfo, permission) {
        this.code = code;
        this.msg = msg;
        this.data = data;
        this.permission = permission;
        if (!utils.isDebug()) {
            this.extraInfo = extraInfo;
        }
    }
}
class ExtraInfo {
    constructor(metrics, errorStack) {
        this.metrics = metrics;
        this.errorStack = errorStack;
        this.kldxVersion = utils.getKldxVersionsStr();
    }
}
function success(data, permission) {
    let extraInfo = utils.isDebug() ? {} : new ExtraInfo(utils.getMetrics());
    return new Result('0', 'success', data, extraInfo, permission);
}
exports.success = success;
function failure(err) {
    let extraInfo = utils.isDebug() ? {} : new ExtraInfo(utils.getMetrics(), getStackByError(err));
    return new Result(err.code, err.msg, null, extraInfo);
}
exports.failure = failure;
function getStackByError(err) {
    if (err instanceof Error) {
        return err.stack;
    }
    return err;
}
function unknown(err) {
    let extraInfo = utils.isDebug() ? {} : new ExtraInfo(utils.getMetrics(), getStackByError(err));
    const e = new exceptions.InternalError('internal error');
    return new Result(e.code, e.msg, null, extraInfo);
}
exports.unknown = unknown;
function developerError(err) {
    return failure(new exceptions.DeveloperBugError(err.message));
}
exports.developerError = developerError;
