"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Retry = void 0;
const common = require("@byted-apaas/server-common-node");
const { InvalidParamError } = common.exceptions;
const maxLimit = 10;
/**
 * 重试工具类
 */
// eslint-disable-next-line unicorn/no-static-only-class,@typescript-eslint/no-extraneous-class
class Retry {
    static async retryTool(promiseFunc, retryConfig) {
        // The number of times to retry before failing
        let retryCnt = 3;
        if (retryConfig && retryConfig.retryCount >= 0) {
            if (!((typeof retryConfig.retryCount === 'number') && retryConfig.retryCount >= 0 && retryConfig.retryCount <= maxLimit)) {
                throw new InvalidParamError(`param retryCount(${retryConfig.retryCount}) invalid: must number and between (0, 10]`);
            }
            retryCnt = retryConfig.retryCount;
        }
        // the delay(ms) between retry requests. By default there is no delay
        let retryDelay = 0;
        if (retryConfig && retryConfig.retryDelay) {
            if (!((typeof retryConfig.retryCount === 'number') && retryConfig.retryDelay >= 0)) {
                throw new InvalidParamError(`param retryDelay(${retryConfig.retryDelay}) invalid: must number`);
            }
            retryDelay = retryConfig.retryDelay;
        }
        return await Retry.retryFunc(promiseFunc, { retryCount: retryCnt, retryDelay });
    }
    static async retryFunc(promiseFunc, retryConfig) {
        let cnt = 0;
        do {
            try {
                return await promiseFunc();
            }
            catch (e) {
                if (e.code === common.exceptions.errCodes.OPENAPI_RATE_LIMIT_ERROR || e.code === common.exceptions.errCodes.FAASINFRA_RATE_LIMIT_ERROR || e.notRetry) {
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
