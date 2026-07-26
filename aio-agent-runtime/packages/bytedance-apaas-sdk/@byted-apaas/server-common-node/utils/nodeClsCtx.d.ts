import { AppCredential } from '../credential/credential';
import { App, Tenant, Event } from '../context/tenant';
import { User } from '../context/user';
import { Metrics } from '../context/metrics';
/**
 * 静态请求上下文
 */
export declare function getReqCtx(): any;
/**
 * 动态请求上下文
 */
export declare function getDynCtx(): any;
/**
 * 批量添加请求上下文
 * @param params
 */
export declare function addObject(params: any): void;
/**
 * 添加请求上下文
 * @param key
 * @param value
 */
export declare function add(key: string, value: any): void;
export declare function getTenant(): Tenant;
export declare function getApp(): App;
export declare function getEvent(): Event;
export declare function setTenant(tenant: any): void;
export declare function getUser(): User;
export declare function mockUserID(userID: number): void;
export declare function setBoe(boe: string): void;
export declare function getBoe(): string;
export declare function setEnv(env: string): void;
export declare function getEnv(): string;
export declare function getEnvKey(): string;
export declare function getLaneKey(): string;
export declare function setDebugType(debugType: string): void;
export declare function setLogID(logID: string): void;
export declare function setEnvKey(env: string): void;
export declare function setFlowVersion(flowVersion: string): void;
export declare function getFlowVersion(): string;
export declare function getLogID(): string;
export declare function getRateLimitFromHeader(): number;
export declare function getRateLimitDowngradeFromHeader(): string;
export declare function getExecuteID(): string;
export declare function getFunctionAPIID(): string;
declare class LoggerInfo {
    sourceID: number;
    sourceLabel: object[];
    objectLabel: object[];
    instanceID: number;
    functionVersionID: string;
    functionLabel: object[];
}
export declare function getLoggerInfo(): LoggerInfo;
export declare function getSource(): string;
export declare function getTriggerType(): string;
export declare function getDeployedGlobalFuncNames(): string[];
export declare function getDeployedGlobalFuncMap(): Record<string, string>;
export declare function getApiTimeoutFromTcc(): object;
export declare function getRetryTimesFromTcc(): number;
export declare function getDistributedHandleMask(): string;
export declare function isDebug(): boolean;
export declare function isLocalDebug(): boolean;
export declare function isOnlineDebug(): boolean;
export declare function getDebugCode(): string;
export declare function getFunctionsVersion(): number;
export declare function getServiceID(): string;
export declare function getTriggerTime(): number;
export declare function getInvokeFuncName(): string;
export declare function setInvokeFuncName(funcName: string): void;
export declare function isAsync(): boolean;
export declare function getTriggerTaskID(): number;
export declare function getTriggerTaskIDStr(): string;
export declare function getOpenapiToken(): string;
export declare function getFaasinfraToken(): string;
export declare function getFaasType(): string;
export declare function isCloseIntranetDomain(): boolean;
export declare function getHttpMethod(): string;
export declare function getSourceID(): number;
export declare function getSourceLabel(): object[];
export declare function getObjectLabel(): object[];
export declare function getInstanceID(): number;
export declare function getFuncVersionID(): string;
export declare function getFuncLabel(): object[];
export declare function getMetrics(): Metrics[];
export declare function addMetrics(metrics: Metrics): void;
export declare function getLoopMasks(): string[];
export declare function getGlobalVariables(): Record<string, string>;
export declare function setHttpHeaders(key: string, value: string): void;
export declare function getRequireFunc(): Function;
export declare function addCredential(credential: AppCredential): void;
export declare function getCredential(): AppCredential;
export type OpenSDKKey = {
    envType?: string;
    mode?: string;
};
export declare function getOpenSDKKeys(): OpenSDKKey;
export declare function addPlatformEnvTypeForOpenSDK(envType: string): void;
export declare function getPlatformEnvTypeForOpenSDK(): string;
export declare function addModeForOpenSDK(mode: string): void;
export declare function getModeForOpenSDK(): string;
export declare function getLaneID(): string;
export declare function getEnvID(): string;
export declare function getEnvType(): Number;
export declare function getHttpHeaders(): Record<string, string>;
export declare function getUnauthFieldMap(): Record<string, Record<number, string[]>>;
export declare function setUnauthFieldMap(unauthFields: Record<string, Record<number, string[]>>): void;
export declare function getFuncMetaConf(apiName: string): any;
export declare function getFuncAPIName(): string;
interface SDKConf {
    transientConf: SDKTransientConf;
}
interface SDKTransientConf {
    isCloseMesh: boolean;
    meshDestReqTimeout: number;
}
export declare function getSDKConf(): SDKConf;
export declare function getSDKTransientConf(): SDKTransientConf;
export declare function setSDKInfo(fromSDK: string, fromVersion: string): void;
export declare function getAPaaSPersistFaaSPressureSignalId(): string;
export declare function getPressureNeedDecelerate(): boolean;
export declare function getPressureConfig(): string;
export {};
