"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getNamespaceForOpenAndFaaSSDK = exports.getTenantInfo = exports.transFlowVariableToMap = exports.transMapToFlowVariable = exports.getTriggerCtx = exports.getDebugExtraInfo = void 0;
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const common = require("@byted-apaas/server-common-node");
const interface_1 = require("./interface");
const credential_1 = require("@byted-apaas/server-common-node/credential/credential");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const common_1 = require("../application/impl/common");
const utils = common.utils;
const checkUtils = common.checkUtils;
const exceptions = common.exceptions;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls');
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
function getDebugExtraInfo() {
    let extra = {
        'FunctionFrameVersion': 'FunctionFrameV2',
    };
    if (utils.isDebug()) {
        extra.DebugInfo = utils.getDebugCode();
    }
    return extra;
}
exports.getDebugExtraInfo = getDebugExtraInfo;
function getTriggerCtx() {
    let triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[constants_1.headers.triggerTaskId] = taskID;
    }
    let temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[constants_1.headers.distributedHandleMask] = temp;
    }
    let reqCtx = nodeCls.get(constants_1.headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[constants_1.headers.loopMasks] = reqCtx.loopMasks;
    }
    return triggerCtx;
}
exports.getTriggerCtx = getTriggerCtx;
function transMapToFlowVariable(params) {
    let variables = [];
    if (params) {
        if (checkUtils.isNotObject(params)) {
            throw new exceptions.InvalidParamError(`params should be object, and not array`);
        }
        for (const [k, v] of Object.entries(params)) {
            variables.push({ api_name: k, value: v });
        }
    }
    return variables;
}
exports.transMapToFlowVariable = transMapToFlowVariable;
function transFlowVariableToMap(variables) {
    let data = {};
    if (variables && Array.isArray(variables)) {
        for (const o of variables) {
            data[o.api_name] = o.value;
        }
    }
    return data;
}
exports.transFlowVariableToMap = transFlowVariableToMap;
async function getTenantInfo(appCtx) {
    if (!appCtx) {
        appCtx = {
            mode: 'faasSDK',
            credential: new credential_1.AppCredential(utils.getClientId(), utils.getClientSecret(), true)
        };
    }
    if (!appCtx.credential) {
        throw new exceptions_1.InvalidParamError(`credential is empty`);
    }
    return await (0, common_1.runCtxForOpenSDK)(appCtx, async () => {
        return await (0, interface_1.GetInstance)().getTenantInfo(appCtx);
    });
}
exports.getTenantInfo = getTenantInfo;
async function getNamespaceForOpenAndFaaSSDK() {
    if (utils.isOpenSDKMode()) { // TODO check need assign?
        return (await utils.getCredential().getTenantInfo()).namespace;
    }
    return utils.getNamespaceFromCtx();
}
exports.getNamespaceForOpenAndFaaSSDK = getNamespaceForOpenAndFaaSSDK;
