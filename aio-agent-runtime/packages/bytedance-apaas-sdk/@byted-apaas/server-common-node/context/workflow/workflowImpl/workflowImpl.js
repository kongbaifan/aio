"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Flow = exports.WorkflowImpl = void 0;
const utils_1 = require("../../../utils/utils");
class WorkflowImpl {
    /**
     * 1.0 传递的是 workflow
     * 2.0 传递的是 flow
     * 3.0 传递的是 flow 下面带有 variables 等结构
     *
     * 预期，同时兼容 flow & workflow 的 context
     * 优先以 flow 为准，且校验 flow 下的 variables 为 object
     * 否则降级解析 workflow 进行挂载
     */
    constructor(flowParams, workflowParams) {
        let flowCtx = workflowParams;
        if ((0, utils_1.getOrSetFlowVersion)({ flow: flowParams, workflow: workflowParams }) === 'v3') {
            flowCtx = flowParams;
        }
        if (flowCtx) {
            this.apiName = flowCtx.apiName;
            this.instanceId = flowCtx.instanceId;
            this.variableTypes = flowCtx.variables;
            // 去除 key value 结构
            this.variables = {};
            for (let key of Object.keys(this.variableTypes)) {
                this.variables[key] = this.variableTypes[key].value;
            }
        }
    }
    async updateVariable(keyOrVariablesMap, value) {
        return null;
    }
    ;
    terminate(workflowInstanceId, options) {
        return null;
    }
    getExecutionUserTaskInfo(executionId) {
        return Promise.resolve([]);
    }
    execute(APIName, options) {
        return Promise.resolve(undefined);
    }
    getExecutionInfo(executionId) {
        return Promise.resolve(undefined);
    }
    revokeExecution(executionId, options) {
        return Promise.resolve(undefined);
    }
}
exports.WorkflowImpl = WorkflowImpl;
class Flow extends WorkflowImpl {
    constructor(flowParams, workflowParams) {
        /**
         * 1.0 传递的是 workflow
         * 2.0 传递的是 flow
         * 3.0 传递的是 flow 下面带有 variables 等结构
         *
         * 预期，同时兼容 flow & workflow 的 context
         * 优先以 flow 为准，且校验 flow 下的 variables 为 object
         * 否则降级解析 workflow 进行挂载
         */
        super(flowParams, workflowParams);
        if (!flowParams) {
            return;
        }
        this.execution = flowParams.execution;
    }
    getExecutionUserTaskInfo(executionId) {
        return null;
    }
    execute(APIName, options) {
        return null;
    }
    getExecutionInfo(executionId) {
        return null;
    }
    revokeExecution(executionId, options) {
        return null;
    }
}
exports.Flow = Flow;
