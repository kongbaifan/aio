"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Flow = void 0;
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const Request = require("../../../../request/interface");
const server_common_node_1 = require("@byted-apaas/server-common-node");
class Flow {
    constructor(flowParams) {
        this.execution = flowParams?.execution;
        this.apiName = flowParams?.apiName;
        this.instanceId = flowParams?.instanceId;
    }
    async execute(apiName, options, async) {
        if (!apiName || typeof apiName !== 'string') {
            throw new exceptions_1.InvalidParamError(`param's type (${apiName}) need string, but is ${typeof apiName}`);
        }
        if (options && options.params && server_common_node_1.checkUtils.isNotObject(options.params)) {
            throw new exceptions_1.InvalidParamError(`options.params's type (${options}) need object, but is ${Array.isArray(options) ? 'array' : typeof options.params}`);
        }
        if (!options) {
            options = {};
        }
        return await Request.GetInstance().executeFlow(apiName, options, async);
    }
    async getExecutionInfo(executionId) {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) is not matched to number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().getExecutionInfo(executionId);
    }
    async getExecutionUserTaskInfo(executionId) {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) need number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().getExecutionUserTaskInfo(BigInt(executionId));
    }
    async revokeExecution(executionId, options) {
        if (!executionId || typeof executionId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${executionId}) is need number, but is ${typeof executionId}`);
        }
        return await Request.GetInstance().revokeExecution(executionId, options);
    }
    async getApprovalInstanceList(options) {
        return await Request.GetInstance().getApprovalInstanceList(options);
    }
    async getApprovalInstance(options) {
        if (!options || !options.approvalInstanceId) {
            throw new exceptions_1.InvalidParamError(`required parameter approvalInstanceId is empty`);
        }
        if (typeof options.approvalInstanceId !== 'number') {
            throw new exceptions_1.InvalidParamError(`param's type (${options.approvalInstanceId}) is need number, but is ${typeof options.approvalInstanceId}`);
        }
        return await Request.GetInstance().getApprovalInstance(options);
    }
}
exports.Flow = Flow;
