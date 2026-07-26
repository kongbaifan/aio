"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_MESH_DEST_REQ_TIMEOUT = exports.TLBEnvOAPILGWGray = exports.TLBEnvHTTPHeader = exports.EnvKeys = exports.CtxKeyEnvType = exports.CtxKeyEnvID = exports.CtxKeyLaneID = exports.CtxKeyEnv = exports.SPEED_DOWN_LOG_TYPE = exports.RATE_LIMIT_LOG_TYPE = exports.USER_LOG_TYPE = exports.APaaSLogSuffix = exports.APaaSLogPrefix = exports.AuthTypeMixUserSystem = exports.AuthTypeUser = exports.AuthTypeSystem = exports.GlobalAuthTypeKey = exports.AuthTypeHttpHeader = exports.OpenAPIRoutingType = exports.FaaSType = exports.APaaSPersistKey = exports.DefaultDebugType = exports.kunlunOrgID = exports.FuncMsgKey = exports.netApi = exports.TypeofValue = exports.functionTriggerType = exports.functionSources = exports.faaSAccessType = exports.ctxBlackLists = exports.logLimitTip = exports.logLimit = exports.languageCode = exports.headers = exports.ctxKey = exports.connTimeoutDefaultValue = exports.connTimeoutTccKey = exports.ApiTimeoutDefaultMap = exports.nodeClsKey = exports.AppTokenRefreshTime = exports.innerCtxKey = exports.IPVersion = exports.WfVarType = void 0;
const ctxMustHaveKeys = ['headers', 'tenant', 'user', 'source', 'triggerType', 'db',
    'deployedGlobalFuncNames', 'deployedGlobalFuncMap', 'loggerInfo', 'resources',
    'tasks', 'function', 'globalVariables', 'method', 'setResponseHeader', 'setRedirectLocation',
    'sysHeaders', 'metrics', 'msg', 'metadata'];
const functionSources = {
    workflow: '1',
    globalFunction: '2',
    recordAutomation: '3',
    scheduleAutomation: '4',
};
exports.functionSources = functionSources;
const functionTriggerType = {
    Action: 'workflow',
    RecordAutomation: 'automation',
    ScheduleAutomation: 'schedule-automation',
    DxComponent: 'dx-data-service',
    PublicAPI: 'public-api',
    DistributedTask: 'distributed-task',
    Microservice: 'microservice',
    CronJob: 'cronjob',
    Connector: 'connector',
    DefaultTrigger: 'default-trigger',
};
exports.functionTriggerType = functionTriggerType;
// 工作流变量类型
var WfVarType;
(function (WfVarType) {
    WfVarType["RECORD"] = "metadataVariable";
    WfVarType["LIST_RECORD"] = "listRecord";
})(WfVarType = exports.WfVarType || (exports.WfVarType = {}));
const faaSAccessType = {
    InspirecloudExternalAccessType: '1',
    InspirecloudIntranetAccessType: '2',
    ByteFaaSIntranetAccessType: '3',
    ByteFaaSExternalAccessType: '4',
    AliyunFcAccessType: '5',
};
exports.faaSAccessType = faaSAccessType;
// SDK IP 协议版本
var IPVersion;
(function (IPVersion) {
    IPVersion[IPVersion["V4"] = 4] = "V4";
    IPVersion[IPVersion["V6"] = 6] = "V6";
})(IPVersion = exports.IPVersion || (exports.IPVersion = {}));
// 业务相关的context key
const ctxBlackLists = {
    ctxKeyBlackList: new Array(),
    ctxHeadersKeyBlackList: [
        'host',
        'user-agent',
        'authorization',
        'accept',
        'accept-encoding',
        'transfer-encoding',
        'content-type',
        'content-length',
        'x-kunlun-sign',
        'x-kunlun-sign-v2',
        'x-kunlun-sign-salt',
        'x-kunlun-token-openapi',
        'x-kunlun-token-faasinfra',
        'x-bytefaas-app-env',
        'x-bytefaas-app-region',
        'x-bytefaas-app-zone',
        'x-bytefaas-revision-id',
        'x-bytefaas-event-type',
        'x-bytefaas-function-id',
        'x-bytefaas-request-id',
        'x-forwarded-for',
        'x-forwarded-host',
    ],
};
exports.ctxBlackLists = ctxBlackLists;
const logLimit = {
    len: 10000,
    count: 10000,
};
exports.logLimit = logLimit;
const logLimitTip = {
    lenTip: '\n... The log has been truncated because it exceeds the length limit.',
    countTip: `The log has been discarded because it exceeded the limit of  ${logLimit.count}`,
};
exports.logLimitTip = logLimitTip;
const connTimeoutTccKey = 'http_connect_timeout';
exports.connTimeoutTccKey = connTimeoutTccKey;
const connTimeoutDefaultValue = 2000;
exports.connTimeoutDefaultValue = connTimeoutDefaultValue;
const ctxKey = {
    mustHaveKeys: ctxMustHaveKeys,
    workflowHaveKeys: ctxMustHaveKeys.concat(['workflow', 'initiator', 'targetRecord', 'objectApiName']),
    globalFuncHaveKeys: ctxMustHaveKeys,
    automationHaveKeys: ctxMustHaveKeys.concat(['workflow', 'trigger', 'objectApiName']),
    scheduleHaveKeys: ctxMustHaveKeys.concat(['workflow']),
};
exports.ctxKey = ctxKey;
const languageCode = {
    // 中文可以用cn或zh，如果同时存在以zh为准
    cn: 2052,
    zh: 2052,
    en: 1033
};
exports.languageCode = languageCode;
const headers = {
    tenant: 'x-kunlun-tenant',
    app: 'x-apaas-app',
    event: 'event',
    initiator: 'x-kunlun-initiator',
    wfInitiator: 'initiator',
    triggerType: 'x-kunlun-trigger-type',
    source: 'x-kunlun-source',
    signV2: 'x-kunlun-sign-v2',
    signSalt: 'x-kunlun-sign-salt',
    kunlunLogid: 'x-kunlun-logid',
    ttLogid: 'x-tt-logid',
    debug: 'x-kunlun-debug',
    debugCodeUrl: 'x-debug-code-url',
    invokeFuncName: 'x-kunlun-invoke-func',
    deployedGlobalFunctions: 'deployed-global-func-names',
    deployedGlobalFunctionMap: 'deployed-global-func-map',
    loggerInfo: 'x-kunlun-logger-info',
    triggerTime: 'x-kunlun-trigger-time',
    asyncTrigger: 'x-kunlun-async-trigger',
    triggerTaskId: 'triggertaskid',
    triggerTaskIdStr: 'triggertaskidstr',
    asyncTask: 'x-kunlun-async-task',
    boe: 'x-kunlun-boe',
    serviceId: 'x-kunlun-service-id',
    openapiToken: 'x-kunlun-token-openapi',
    faasinfraToken: 'x-kunlun-token-faasinfra',
    apiTimeoutFromTcc: 'api-timeouts-from-tcc',
    globalVariablesKey: 'global-variables',
    faasAccessType: 'x-kunlun-faas-access-type',
    isCloseIntranetDomain: 'x-kunlun-sdk-close-intranet-domain',
    loopMasks: 'x-kunlun-loop-masks',
    loopMasksKey: 'loopMasks',
    loopCtxKey: 'loopCtx',
    retryTimesFromTcc: 'x-kunlun-faas-retry-times',
    envKey: 'x-tt-env',
    useKeyForPPE: 'x-use-ppe',
    useKeyForBOE: 'x-use-boe',
    distributedHandleMask: 'x-kunlun-distributed-mask',
    faasSdkFuncMsgKey: 'Rpc-Persist-Kunlun-Faassdk',
    laneCtxKey: 'APAAS_LANE',
    laneHttpHeader: 'Rpc-Persist-Lane-C-APAAS-LANE',
    orgIDKey: 'X-Kunlun-Org-Id',
    EnvIDHeaderKey: "x-ae-envid",
    EnvTypeHeaderKey: "x-ae-envtype",
    functionsVersion: 'x-kunlun-functions-version.ts',
    LaneIDHeaderKey: 'x-ae-lane',
    functionMetaConf: 'x-kunlun-invoke-func-meta-conf',
    functionAPIName: 'x-kunlun-invoke-func-api-name',
    sdkConfKey: 'x-apaas-sdk-conf',
    traceParentKey: 'traceparent',
    traceStateKey: 'tracestate',
    ExecuteID: 'x-serverless-execute-id',
    FunctionAPIID: 'x-serverless-function-api-id',
    EnvoyRespFlag: 'x-envoy-response-flags',
    SDKPodRateLimitQuota: 'x-serverless-sdk-pod-rate-limit-quota',
    SDKPodRateLimitDowngradeHeader: 'x-serverless-sdk-pod-rate-limit-downgrade',
    // 反压中心
    SdkPressureNeedDecelerateHeader: 'x-serverless-sdk-pressure-need-decelerate',
    SdkPressureConfigHeader: 'x-serverless-sdk-pressure-config',
};
exports.headers = headers;
const APaaSPersistKey = {
    APAAS_PERSIST_PREFIX: 'rpc-persist-',
    APAAS_PERSIST_FAAS_PREFIX: 'x-apaas-persist-faas-',
    PersistFaaSKeySummarized: 'x-apaas-persist-faas-summarized',
    PersistFaaSKeyFaaSType: 'x-apaas-persist-faas-type',
    PersistFaaSKeyFuncAPIName: 'x-apaas-persist-faas-func-api-name',
    PersistFaaSKeyOpenAPIRoutingType: 'x-apaas-persist-faas-openapi-routing-type',
    PersistFaaSKeyFromSDKName: 'x-apaas-persist-faas-from-sdk-name',
    PersistFaaSKeyFromSDKVersion: 'x-apaas-persist-faas-from-sdk-version',
    // 流量溯源
    PersistFaaSKeyRequestSource: 'x-apaas-persist-faas-request-source',
    RequestSourcePressureSignalId: 'pressureSignalId',
    RequestSourceIsAsync: 'isAsync',
};
exports.APaaSPersistKey = APaaSPersistKey;
exports.innerCtxKey = {
    responseHeaders: 'responseHeaders',
    sysHeaders: 'sysHeaders',
    headers: 'headers',
    method: 'method',
};
const FuncMsgKey = {
    funcApiName: 'funcApiName',
};
exports.FuncMsgKey = FuncMsgKey;
const FaaSType = {
    FaaSTypeFunction: 'function',
    FaaSTypeMicroService: 'microService',
    FaaSTypeOpenSDK: 'openSDK',
};
exports.FaaSType = FaaSType;
const OpenAPIRoutingType = {
    OpenAPIRoutingTypeToLGW: 'toLGW',
    OpenAPIRoutingTypeToInnerAPI: 'toInnerAPI',
};
exports.OpenAPIRoutingType = OpenAPIRoutingType;
var TypeofValue;
(function (TypeofValue) {
    TypeofValue["string"] = "string";
    TypeofValue["number"] = "number";
    TypeofValue["boolean"] = "boolean";
    TypeofValue["object"] = "object";
    TypeofValue["function"] = "function";
    TypeofValue["undefined"] = "undefined";
    TypeofValue["symbol"] = "symbol";
})(TypeofValue || (TypeofValue = {}));
exports.TypeofValue = TypeofValue;
const netApi = {
    HttpMethods: ['GET', 'POST', 'PUT', 'PATCH', 'HEAD', 'DELETE', 'OPTIONS', 'TRACE'],
    ResponseTypes: ['text', 'json', 'buffer'],
    ConnectTimeout: 3000,
    SecureConnectTimeout: 2000,
};
exports.netApi = netApi;
const kunlunOrgID = '1';
exports.kunlunOrgID = kunlunOrgID;
exports.AppTokenRefreshTime = 20 * 60 * 1000;
exports.nodeClsKey = {
    openSDKKey: 'openSDKKey',
    credential: 'credential',
    flowVersion: 'flowVersion',
};
exports.ApiTimeoutDefaultMap = {
    'openapi_uploadAttachment': 50 * 1000,
    'openapi_uploadAttachmentV2': 50 * 1000,
    'openapi_downloadAttachment': 50 * 1000,
    'openapi_downloadAttachmentV2': 50 * 1000,
    'openapi_downloadAvatar': 30 * 1000,
    'openapi_uploadAvatar': 30 * 1000,
    'openapi_executeFlow': 25 * 1000,
    'openapi_invokeFuncWithAuth': 16 * 60 * 1000,
    'openapi_invokeFuncSync': 16 * 60 * 1000,
    'faasinfra_invokeFuncSync': 16 * 60 * 1000,
    'faasinfra_invokeMicroserviceSync': 16 * 60 * 1000,
    'faasinfra_requestFile': 30 * 1000,
};
const DefaultDebugType = '2';
exports.DefaultDebugType = DefaultDebugType;
exports.AuthTypeHttpHeader = 'Rpc-Persist-AUTH-TYPE';
exports.GlobalAuthTypeKey = 'GlobalAuthType';
exports.AuthTypeSystem = 'system';
exports.AuthTypeUser = 'user';
exports.AuthTypeMixUserSystem = 'mix_user_system'; // OQL 场景需要，传该值时只有 select 过权限，where、orderBy 和 groupBy 不过权限
exports.APaaSLogPrefix = 'apaas-log-prefix'; //nolint:byted_s_ts_naming_convention
exports.APaaSLogSuffix = 'apaas-log-suffix'; //nolint:byted_s_ts_naming_convention
exports.USER_LOG_TYPE = 'user'; //nolint:byted_s_ts_naming_convention
exports.RATE_LIMIT_LOG_TYPE = 'rate_limit'; //nolint:byted_s_ts_naming_convention
exports.SPEED_DOWN_LOG_TYPE = 'speed_down'; //nolint:byted_s_ts_naming_convention
// rpc 泳道标识
// 平台泳道
exports.CtxKeyEnv = "K_ENV";
// 功能泳道（多分支）
exports.CtxKeyLaneID = "KUNLUN_LANE_ID";
// 环境标识（多线上/测试环境）
exports.CtxKeyEnvID = "KUNLUN_ENV_ID";
exports.CtxKeyEnvType = "KUNLUN_ENV_TYPE";
exports.EnvKeys = {
    EnvKMeshHttp: 'TCE_ENABLE_HTTP_SIDECAR_EGRESS',
    EnvKMeshUDS: 'WITH_HTTP_MESH_EGRESS_UDS',
    EnvKSocketAddr: 'SERVICE_MESH_HTTP_EGRESS_ADDR',
};
exports.TLBEnvHTTPHeader = 'X-Tlb-Env'; // TLB 分流标签
exports.TLBEnvOAPILGWGray = 'oapi_lgw_gray'; // 请求至 openapi 域名后，TLB 分流至 LGW
exports.DEFAULT_MESH_DEST_REQ_TIMEOUT = 60000;
