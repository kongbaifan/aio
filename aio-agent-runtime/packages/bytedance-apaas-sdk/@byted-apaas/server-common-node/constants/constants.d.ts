declare const functionSources: {
    workflow: string;
    globalFunction: string;
    recordAutomation: string;
    scheduleAutomation: string;
};
declare const functionTriggerType: {
    Action: string;
    RecordAutomation: string;
    ScheduleAutomation: string;
    DxComponent: string;
    PublicAPI: string;
    DistributedTask: string;
    Microservice: string;
    CronJob: string;
    Connector: string;
    DefaultTrigger: string;
};
export declare enum WfVarType {
    RECORD = "metadataVariable",
    LIST_RECORD = "listRecord"
}
declare const faaSAccessType: {
    InspirecloudExternalAccessType: string;
    InspirecloudIntranetAccessType: string;
    ByteFaaSIntranetAccessType: string;
    ByteFaaSExternalAccessType: string;
    AliyunFcAccessType: string;
};
export declare enum IPVersion {
    V4 = 4,
    V6 = 6
}
declare const ctxBlackLists: {
    ctxKeyBlackList: string[];
    ctxHeadersKeyBlackList: string[];
};
declare const logLimit: {
    len: number;
    count: number;
};
declare const logLimitTip: {
    lenTip: string;
    countTip: string;
};
declare const connTimeoutTccKey = "http_connect_timeout";
declare const connTimeoutDefaultValue = 2000;
declare const ctxKey: {
    mustHaveKeys: string[];
    workflowHaveKeys: string[];
    globalFuncHaveKeys: string[];
    automationHaveKeys: string[];
    scheduleHaveKeys: string[];
};
declare const languageCode: {
    cn: number;
    zh: number;
    en: number;
};
declare const headers: {
    tenant: string;
    app: string;
    event: string;
    initiator: string;
    wfInitiator: string;
    triggerType: string;
    source: string;
    signV2: string;
    signSalt: string;
    kunlunLogid: string;
    ttLogid: string;
    debug: string;
    debugCodeUrl: string;
    invokeFuncName: string;
    deployedGlobalFunctions: string;
    deployedGlobalFunctionMap: string;
    loggerInfo: string;
    triggerTime: string;
    asyncTrigger: string;
    triggerTaskId: string;
    triggerTaskIdStr: string;
    asyncTask: string;
    boe: string;
    serviceId: string;
    openapiToken: string;
    faasinfraToken: string;
    apiTimeoutFromTcc: string;
    globalVariablesKey: string;
    faasAccessType: string;
    isCloseIntranetDomain: string;
    loopMasks: string;
    loopMasksKey: string;
    loopCtxKey: string;
    retryTimesFromTcc: string;
    envKey: string;
    useKeyForPPE: string;
    useKeyForBOE: string;
    distributedHandleMask: string;
    faasSdkFuncMsgKey: string;
    laneCtxKey: string;
    laneHttpHeader: string;
    orgIDKey: string;
    EnvIDHeaderKey: string;
    EnvTypeHeaderKey: string;
    functionsVersion: string;
    LaneIDHeaderKey: string;
    functionMetaConf: string;
    functionAPIName: string;
    sdkConfKey: string;
    traceParentKey: string;
    traceStateKey: string;
    ExecuteID: string;
    FunctionAPIID: string;
    EnvoyRespFlag: string;
    SDKPodRateLimitQuota: string;
    SDKPodRateLimitDowngradeHeader: string;
    SdkPressureNeedDecelerateHeader: string;
    SdkPressureConfigHeader: string;
};
declare const APaaSPersistKey: {
    APAAS_PERSIST_PREFIX: string;
    APAAS_PERSIST_FAAS_PREFIX: string;
    PersistFaaSKeySummarized: string;
    PersistFaaSKeyFaaSType: string;
    PersistFaaSKeyFuncAPIName: string;
    PersistFaaSKeyOpenAPIRoutingType: string;
    PersistFaaSKeyFromSDKName: string;
    PersistFaaSKeyFromSDKVersion: string;
    PersistFaaSKeyRequestSource: string;
    RequestSourcePressureSignalId: string;
    RequestSourceIsAsync: string;
};
export declare const innerCtxKey: {
    responseHeaders: string;
    sysHeaders: string;
    headers: string;
    method: string;
};
declare const FuncMsgKey: {
    funcApiName: string;
};
declare const FaaSType: {
    FaaSTypeFunction: string;
    FaaSTypeMicroService: string;
    FaaSTypeOpenSDK: string;
};
declare const OpenAPIRoutingType: {
    OpenAPIRoutingTypeToLGW: string;
    OpenAPIRoutingTypeToInnerAPI: string;
};
declare enum TypeofValue {
    string = "string",
    number = "number",
    boolean = "boolean",
    object = "object",
    function = "function",
    undefined = "undefined",
    symbol = "symbol"
}
declare const netApi: {
    HttpMethods: string[];
    ResponseTypes: string[];
    ConnectTimeout: number;
    SecureConnectTimeout: number;
};
declare const kunlunOrgID = "1";
export declare const AppTokenRefreshTime: number;
export declare const nodeClsKey: {
    openSDKKey: string;
    credential: string;
    flowVersion: string;
};
export declare const ApiTimeoutDefaultMap: {
    openapi_uploadAttachment: number;
    openapi_uploadAttachmentV2: number;
    openapi_downloadAttachment: number;
    openapi_downloadAttachmentV2: number;
    openapi_downloadAvatar: number;
    openapi_uploadAvatar: number;
    openapi_executeFlow: number;
    openapi_invokeFuncWithAuth: number;
    openapi_invokeFuncSync: number;
    faasinfra_invokeFuncSync: number;
    faasinfra_invokeMicroserviceSync: number;
    faasinfra_requestFile: number;
};
type PlatformEnvType = 'stagingboe' | 'staging' | 'gray' | 'online';
declare const DefaultDebugType = "2";
export { connTimeoutTccKey, connTimeoutDefaultValue, ctxKey, headers, languageCode, logLimit, logLimitTip, ctxBlackLists, faaSAccessType, functionSources, functionTriggerType, TypeofValue, netApi, FuncMsgKey, kunlunOrgID, PlatformEnvType, DefaultDebugType, APaaSPersistKey, FaaSType, OpenAPIRoutingType, };
export declare const AuthTypeHttpHeader = "Rpc-Persist-AUTH-TYPE";
export declare const GlobalAuthTypeKey = "GlobalAuthType";
export declare const AuthTypeSystem = "system";
export declare const AuthTypeUser = "user";
export declare const AuthTypeMixUserSystem = "mix_user_system";
export declare const APaaSLogPrefix = "apaas-log-prefix";
export declare const APaaSLogSuffix = "apaas-log-suffix";
export declare const USER_LOG_TYPE = "user";
export declare const RATE_LIMIT_LOG_TYPE = "rate_limit";
export declare const SPEED_DOWN_LOG_TYPE = "speed_down";
export declare const CtxKeyEnv = "K_ENV";
export declare const CtxKeyLaneID = "KUNLUN_LANE_ID";
export declare const CtxKeyEnvID = "KUNLUN_ENV_ID";
export declare const CtxKeyEnvType = "KUNLUN_ENV_TYPE";
export declare const EnvKeys: Record<string, string>;
export declare const TLBEnvHTTPHeader = "X-Tlb-Env";
export declare const TLBEnvOAPILGWGray = "oapi_lgw_gray";
export declare const DEFAULT_MESH_DEST_REQ_TIMEOUT = 60000;
