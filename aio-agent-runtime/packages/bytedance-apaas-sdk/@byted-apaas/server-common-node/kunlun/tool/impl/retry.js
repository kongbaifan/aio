"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Retry = void 0;
const exceptions_1 = require("../../../utils/exceptions");
const maxLimit = 10;
/**
 * 重试工具类
 */
class Retry {
    static async retryTool(promiseFunc, retryConfig) {
        // The number of times to retry before failing
        let retryCnt = 3;
        if (retryConfig && retryConfig.retryCount >= 0) {
            if (!((typeof retryConfig.retryCount === 'number') && retryConfig.retryCount >= 0 && retryConfig.retryCount <= maxLimit)) {
                throw new exceptions_1.InvalidParamError(`param retryCount(${retryConfig.retryCount}) invalid: must number and between (0, 10]`);
            }
            retryCnt = retryConfig.retryCount;
        }
        // the delay(ms) between retry requests. By default there is no delay
        let retryDelay = 0;
        if (retryConfig && retryConfig.retryDelay) {
            if (!((typeof retryConfig.retryCount === 'number') && retryConfig.retryDelay >= 0)) {
                throw new exceptions_1.InvalidParamError(`param retryDelay(${retryConfig.retryDelay}) invalid: must number`);
            }
            retryDelay = retryConfig.retryDelay;
        }
        return await Retry.retryFunc(promiseFunc, { retryCount: retryCnt, retryDelay: retryDelay });
    }
    static async retryFunc(promiseFunc, retryConfig) {
        let cnt = 0;
        do {
            try {
                return await promiseFunc();
            }
            catch (e) {
                if (e.notRetry) {
                    throw e;
                }
                if (cnt >= retryConfig.retryCount) {
                    throw e;
                }
                if (retryConfig.retryDelay > 0) {
                    await new Promise(resolve => {
                        setTimeout(resolve, retryConfig.retryDelay);
                    });
                }
            }
        } while (cnt++ < retryConfig.retryCount);
    }
}
exports.Retry = Retry;
