"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.VeFaaSLogger = void 0;
const logger_1 = require("./logger");
const utils_1 = require("./utils");
class VeFaaSLogger {
    static get_content(...args) {
        return (0, utils_1.stringify)({
            content: (0, logger_1.args2string)(args),
            function: (0, utils_1.getInvokeFuncName)(),
            requestID: (0, logger_1.utils)().getLogID(),
            triggerType: 'triggerType_' + (0, logger_1.utils)().getTriggerType(),
        });
    }
    static info(...args) {
        VeFaaSLogger.originConsoleInfo(VeFaaSLogger.get_content(...args));
    }
    static log(...args) {
        VeFaaSLogger.originConsoleLog(VeFaaSLogger.get_content(...args));
    }
    static warn(...args) {
        VeFaaSLogger.originConsoleWarn(VeFaaSLogger.get_content(...args));
    }
    static error(...args) {
        VeFaaSLogger.originConsoleError(VeFaaSLogger.get_content(...args));
    }
}
exports.VeFaaSLogger = VeFaaSLogger;
VeFaaSLogger.originConsoleLog = console.log;
VeFaaSLogger.originConsoleInfo = console.info;
VeFaaSLogger.originConsoleWarn = console.warn;
VeFaaSLogger.originConsoleError = console.error;
