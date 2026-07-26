"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Tasks = exports._Options = void 0;
const common = require("@byted-apaas/server-common-node");
const Request = require("../../request/interface");
const utils = common.utils;
const exceptions = common.exceptions;
class _Options {
}
exports._Options = _Options;
// export async function asyncTaskV1(apiName: string, params: any, oldFuncName: string, isSync: boolean) {
//     return await invokeFuncSync(apiName, params, oldFuncName, false);
// }
class Tasks {
    constructor(_f) {
        this.f = _f;
    }
    /**
     * 创建异步任务
     * @param apiName 函数的 apiName
     * @param params 参数
     */
    async createAsyncTask(apiName, params) {
        if (apiName && params) {
            // low_code 1.0
            if (utils.isOnlineDev()) {
                // 1.debug模式
                if (utils.isDebug()) {
                    return await this.f(apiName).invoke(params);
                }
                // 2.运行时
                let newApiName = utils.handleFuncName(null, apiName);
                if (!newApiName) {
                    throw new exceptions.InvalidParamError(`The function (${apiName}) does not exist, please confirm ${apiName} exists and has been deployed.`);
                }
                let idOrName = {};
                if (newApiName === (apiName)) {
                    idOrName = {
                        APIName: newApiName,
                        isInvokeByAPIName: true,
                    };
                }
                else if (utils.isMicroservice()) {
                    idOrName = {
                        APIName: apiName,
                        isInvokeByAPIName: true,
                    };
                }
                else {
                    idOrName = {
                        APIId: newApiName,
                        isInvokeByAPIName: false,
                    };
                }
                return {
                    task_id: await Request.GetInstance().createAsyncTaskV1(idOrName, params),
                };
            }
            // low_code 2.0
            // 如果是本地调试模式，则直接异步执行
            if (utils.isLocalDebug()) {
                this.f(apiName).invoke(params);
                return { task_id: 1234567890123456 };
            }
            return {
                task_id: await Request.GetInstance().createAsyncTaskV2(apiName, params),
            };
        }
        else {
            throw new exceptions.InvalidParamError(`context.tasks.createAsyncTask params is error`);
        }
    }
    ;
    /**
     * 创建分布式任务
     * @param dataset 待处理数据组成的数组
     * @param handlerFunc 用于处理数据集的全局函数的 API name
     * @param progressCallbackFunc 任务进度发生变化时回调的全局函数的 API name，可通过传入 '' / null / undefined 跳过此步骤
     * @param completedCallbackFunc 任务完成时回调的全局函数的 API name，可通过传入 '' / null / undefined 跳过此步骤
     * @param options 高级配置参数，可选
     */
    async createDistributedTask(dataset, handlerFunc, progressCallbackFunc, completedCallbackFunc, options) {
        if (utils.isLocalDebug()) {
            throw new exceptions.InvalidParamError("Local debugging isn't supported for distributed tasks. You can only deploy them to the cloud");
        }
        if (utils.getDistributedHandleMask()) {
            throw new exceptions.InvalidParamError('Does not support creating distributed tasks in handler function and progress callback function');
        }
        // dataset
        if (!(dataset instanceof Array)) {
            throw new exceptions.InvalidParamError(`parameter dataset is not list`);
        }
        // handlerFunc
        if (!handlerFunc || typeof handlerFunc !== 'string') {
            throw new exceptions.InvalidParamError(`parameter handlerFunc is not string or handlerFunc is empty`);
        }
        // progressCallbackFunc
        if (progressCallbackFunc === null || progressCallbackFunc === undefined) {
            progressCallbackFunc = '';
        }
        if (typeof progressCallbackFunc !== 'string') {
            throw new exceptions.InvalidParamError(`parameter progressCallbackFunc is not string`);
        }
        // completedCallbackFunc
        if (completedCallbackFunc === null || completedCallbackFunc === undefined) {
            completedCallbackFunc = '';
        }
        if (typeof completedCallbackFunc !== 'string') {
            throw new exceptions.InvalidParamError(`parameter completedCallbackFunc is not string`);
        }
        // option.concurrency
        if (options.concurrency === null || options.concurrency === undefined) {
            options.concurrency = 5;
        }
        if ((typeof options.concurrency !== 'number') || options.concurrency <= 0) {
            throw new exceptions.InvalidParamError(`parameter option.concurrency is not Number or not graterThan 0`);
        }
        // option.maxSliceNumber
        if (options.maxSliceNumber === null || options.maxSliceNumber === undefined) {
            options.maxSliceNumber = 5;
        }
        if ((typeof options.maxSliceNumber !== 'number') || options.maxSliceNumber <= 0) {
            throw new exceptions.InvalidParamError(`parameter option.maxSliceNumber is not Number or not graterThan 0`);
        }
        // option.notifyStep
        if (options.progressCallbackStep === null || options.progressCallbackStep === undefined) {
            options.progressCallbackStep = 1;
        }
        if ((typeof options.progressCallbackStep !== 'number') || options.progressCallbackStep <= 0 || options.progressCallbackStep > 100) {
            throw new exceptions.InvalidParamError(`parameter option.progressCallbackStep is not Number or not between 0 and 100`);
        }
        if (utils.isOnlineDev()) {
            return Request.GetFaaSInfraInstance().createDistributeTaskV1([dataset], handlerFunc, progressCallbackFunc, completedCallbackFunc, options);
        }
        return Request.GetFaaSInfraInstance().createDistributeTaskV2([dataset], handlerFunc, progressCallbackFunc, completedCallbackFunc, options);
    }
    ;
}
exports.Tasks = Tasks;
