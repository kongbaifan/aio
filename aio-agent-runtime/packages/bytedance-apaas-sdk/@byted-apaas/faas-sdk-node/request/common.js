"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getNamespaceForOpenAndFaaSSDK = exports.getTriggerCtx = void 0;
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
const common = require("@byted-apaas/server-common-node");
const permissionUtils = require("@byted-apaas/server-common-node/utils/permissionUtils");
const utils = common.utils;
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls'); //nolint:byted_s_ts_no_require_imports
function checkLoopCtx(reqCtx) {
    return reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks);
}
async function getTriggerCtx(params, funcAPIName) {
    const triggerCtx = {}, taskID = utils.getTriggerTaskID();
    if (taskID) {
        triggerCtx[constants_1.headers.triggerTaskId] = taskID;
    }
    const temp = utils.getDistributedHandleMask();
    if (temp) {
        triggerCtx[constants_1.headers.distributedHandleMask] = temp;
    }
    const reqCtx = nodeCls.get(constants_1.headers.loopCtxKey);
    if (checkLoopCtx(reqCtx)) {
        triggerCtx[constants_1.headers.loopMasks] = reqCtx.loopMasks;
    }
    triggerCtx.permission = await permissionUtils.delParamsUnauthField(funcAPIName, 'input', params);
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
