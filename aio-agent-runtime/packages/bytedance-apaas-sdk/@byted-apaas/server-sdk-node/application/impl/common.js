"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runCtxForOpenSDK = void 0;
const utils = require("@byted-apaas/server-common-node/utils/utils");
const nodeClsCtx = require("@byted-apaas/server-common-node/utils/nodeClsCtx");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const crypto = require('crypto'); //nolint:byted_s_ts_no_require_imports
async function runCtxForOpenSDK(appCtx, promise) {
    if (appCtx && appCtx.mode === 'openSDK') {
        if (!appCtx.credential) {
            throw new exceptions_1.InvalidParamError(`credential is empty for openSDK`);
        }
        return nodeClsCtx.getReqCtx().run(async () => {
            utils.setModeForOpenSDK(appCtx.mode);
            utils.setCredential(appCtx.credential);
            utils.setDebugType(appCtx.debugType);
            switch (appCtx.env) {
                // @ts-ignore
                case 'developmentboe':
                    utils.setEnv('development');
                    utils.setBoe('boe');
                    break;
                // @ts-ignore
                case 'stagingboe':
                    utils.setEnv('staging');
                    utils.setBoe('boe');
                    break;
                case 'staging':
                    utils.setEnv('staging');
                    break;
                case 'gray':
                    utils.setEnv('gray');
                    break;
                case 'online':
                    utils.setEnv('online');
                    break;
                default:
                    throw new exceptions_1.InvalidParamError(`platformEnvType is invalid for ${appCtx.env}`);
            }
            utils.setInvokeFuncName('openSDK');
            utils.setTenant(await appCtx.credential.getTenantInfo());
            utils.setXTTEnvOnlyDebug(appCtx.x_tt_env);
            if (!utils.getLogID()) {
                utils.setLogID(crypto.randomBytes(16).toString('hex'));
            }
            return await promise();
        });
    }
    return await promise();
}
exports.runCtxForOpenSDK = runCtxForOpenSDK;
