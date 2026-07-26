"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.faasinfraHttpPath = exports.metricsMethodKeys = void 0;
const config_1 = require("@byted-apaas/server-common-node/http/config");
exports.metricsMethodKeys = {
    requestMongodb: 'faasinfra_requestMongodb',
    requestFile: 'faasinfra_requestFile',
    requestRedis: 'faasinfra_requestRedis',
    requestGlobalVar: 'faasinfra_requestGlobalVar',
};
exports.faasinfraHttpPath = {
    requestMongodb: new config_1.PostHttpConfig('/resource/v3/namespaces/:namespace/db', exports.metricsMethodKeys.requestMongodb),
    requestFile: new config_1.PostHttpConfig('/resource/v2/namespaces/:namespace/file', exports.metricsMethodKeys.requestFile, 25000),
    requestRedis: new config_1.PostHttpConfig('/resource/v2/namespaces/:namespace/cache', exports.metricsMethodKeys.requestRedis),
    requestGlobalVar: new config_1.GetHttpConfig('/global_var/v1/services/:serviceID/global_variables/keys/:key', exports.metricsMethodKeys.requestGlobalVar),
};
