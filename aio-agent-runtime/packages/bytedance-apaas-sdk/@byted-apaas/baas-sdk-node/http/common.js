"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getNamespaceForOpenAndFaaSSDK = exports.getTriggerCtx = exports.getDebugExtraInfo = void 0;
const common = require("@byted-apaas/server-common-node");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
const { headers } = common.constants;
const utils = common.utils;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
function getDebugExtraInfo() {
    const extra = {
        'FunctionFrameVersion': 'FunctionFrameV2',
    };
    if (utils.isDebug()) {
        extra.DebugInfo = utils.getDebugCode();
    }
    return extra;
}
exports.getDebugExtraInfo = getDebugExtraInfo;
async function getTriggerCtx(params, functinAPIName) {
    const triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[headers.triggerTaskId] = taskID;
    }
    const temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[headers.distributedHandleMask] = temp;
    }
    const reqCtx = nodeCls.get(headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[headers.loopMasks] = reqCtx.loopMasks;
    }
    triggerCtx.permission = await permissionUtils.delParamsUnauthField(functinAPIName, 'input', params);
    return triggerCtx;
}
exports.getTriggerCtx = getTriggerCtx;
async function getNamespaceForOpenAndFaaSSDK() {
    if (utils.isOpenSDKMode()) { // TODO check need assign?
        return (await utils.getCredential().getTenantInfo()).namespace;
    }
    return utils.getNamespaceFromCtx();
}
exports.getNamespaceForOpenAndFaaSSDK = getNamespaceForOpenAndFaaSSDK;
