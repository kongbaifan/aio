import { App, Event, Tenant, TenantType } from '../context/tenant';
import { User } from '../context/user';
import { Metrics } from '../context/metrics';
import { TypeofValue } from '../constants/constants';
import { AppCredential } from '../credential/credential';
import { HttpOptions } from '../http/request';
/**
 * logId和requestId用的同一个值
 */
export declare function getLogID(): string;
export declare function getRateLimitFromHeader(): number;
export declare function getRateLimitDowngradeFromHeader(): string;
export declare function getExecuteID(): string;
export declare function getFunctionAPIID(): string;
export declare function setLogID(logID: string): void;
export declare function getDeployedGlobalFuncNames(): string[];
export declare function getDeployedGlobalFuncMap(): Record<string, string>;
export declare function getLoggerInfo(): Record<string, any>;
export declare function getApiTimeoutFromTcc(): object;
export declare function getRetryTimesFromTcc(): number;
export declare function handleErrorMsg(e: Error): void;
export declare function getTriggerTime(): number;
export declare function getSourceID(): number;
export declare function getSourceLabel(): object[];
export declare function getObjectLabel(): object[];
export declare function getInstanceID(): number;
export declare function isAsync(): boolean;
export declare function getFuncVersionID(): string;
export declare function getFuncLabel(): object[];
export declare function isDeployedGlobalFuncNames(context: any, funcName: string): boolean;
export declare function printInfoLog(msg: any): void;
export declare function printDebugLog(msg: any): void;
export declare function printErrorLog(msg: any): void;
export declare function getTenant(): Tenant;
export declare function getApp(): App;
export declare function getEvent(): Event;
export declare function setTenant(tenant: any): void;
export declare function getTenantIDFromCtx(): number;
export declare function getTenantNameFromCtx(): string;
export declare function getTenantTypeFromCtx(): TenantType;
export declare function getNamespaceFromCtx(): string;
export declare function getDomainFromCtx(): string;
export declare function getUser(): User;
export declare function getUserIDFromCtx(): number;
export declare function mockUserID(userID: number): void;
/**
 * 仅仅是Object，不是Array
 *
 * @param value
 * @returns {boolean}
 */
export declare function isObject(value: unknown): boolean;
export declare function isRegex(value: unknown): boolean;
export declare function getArrayLength<T>(arr: Array<T>): number;
/**
 * source表示函数的类型，目前支持2种source
 * 1: 表示 workflow
 * 2: 表示 global_function
 * 3: 表示 automation
 * 4: 表示 schedule-automation
 *
 * @returns {string|*}
 */
export declare function getSource(): string;
export declare function getTriggerType(): string;
export declare function getDistributedHandleMask(): string;
export declare function isDebug(): boolean;
export declare function setDebugType(debugType: '0' | '1' | '2'): void;
export declare function isLocalDebug(): boolean;
export declare function isOnlineDebug(): boolean;
export declare function getFunctionsType(): number;
export declare function isOnlineDev(): boolean;
export declare function isOpenSDKMode(): boolean;
export declare function getDebugCode(): string;
type FlowVersion = '-' | 'v1' | 'v2' | 'v3';
export declare function getOrSetFlowVersion(context: {
    flow: any;
    workflow: any;
}): FlowVersion;
/**
 * 处理循环引用
 *
 * @param value
 * @param cutCircle
 * @param replacer
 * @param space
 * @returns {string}
 */
export declare function stringify(value: any, cutCircle?: boolean, replacer?: (this: any, key: string, value: any) => any, space?: string | number): string;
export declare function getColorNameById(id: string): string;
/**
 * 场景：传参a、b、c、d、e，以下方式等效
 * 方式一：(a, b, c, d, e)
 * 方式二：([a, b, c, d, e])
 * 方式三：(a, [b, c], d, e)
 *
 * @param args
 * @returns {[]}
 */
export declare function argsToList(...args: any[]): any[];
export declare function getGlobalFunc(context: any, funcName: string, requireFunc?: Function): any;
export declare function requireFunction(apiName: string): any;
export declare function mkdirs(dirpath: string): void;
export declare function getTriggerTaskID(): number;
export declare function getTriggerTaskIDStr(): string;
/**
 * 兼容有无namespace的场景
 *
 * @param context
 * @param funcName
 * @returns {string|*}
 */
export declare function handleFuncName(context: any, funcName: string): string;
export declare function getInvokeFuncName(): string;
export declare function setInvokeFuncName(funcName: string): void;
export declare function getInvokeFuncApiAlias(): string;
export declare function setHttpHeaders(key: string, value: string): void;
export declare function getCredential(): AppCredential;
export declare function getModeForOpenSDK(): string;
export declare function getPlatformEnvTypeForOpenSDK(): string;
export declare function setPlatformEnvTypeForOpenSDK(envType: string): void;
export declare function setModeForOpenSDK(mode: string): void;
export declare function setCredential(credential: any): void;
export declare function getFaasType(): string;
export declare function isBoe(): boolean;
export declare function setBoe(boe: string): void;
export declare function setEnv(env: string): void;
export declare function getBoe(): string;
export declare function getEnv(): string;
export declare function getEnvKey(): string;
export declare function getLaneKey(): string;
export declare function setXTTEnvOnlyDebug(xTTEnv: string): void;
export declare function getEnvWithBoe(): string;
export declare function getOpenapiToken(): string;
export declare function getFaasinfraToken(): string;
export declare function isCloseIntranetDomain(): boolean;
export declare function getHttpMethod(): string;
export declare function modifySource(ctx: any, source: string): any;
export declare function success(options: any, beginReqTime: number): void;
export declare function fail(options: any, beginReqTime: number): void;
export declare function getMetrics(): Metrics[];
export declare function getLoopMasks(): string[];
export declare function getGlobalVariable(): Record<string, string>;
export declare function getGlobalVariableByKey(key: string): string;
export declare function getRequireFunc(): Function;
export declare function isHttpConnectError(err: any): boolean;
/**
 * 检查参数本身或者其中元素的类型
 * @param name 参数名字，用来抛异常
 * @param typeValues 判断类型，TypeofValue 枚举
 * @param param 判断参数
 * @param checkUndefined 是否检查 undefined
 */
export declare function checkTypeOfParams(name: string, typeValues: TypeofValue[], param: unknown, checkUndefined?: boolean): void;
/**
 * 检查参数是否是 undefined
 * @param name 参数名字，用来抛异常
 * @param param 判断参数
 */
export declare function checkRequiredParam(name: string, param: unknown): void;
export declare function replaceErrorStack(err: Error, before: string, after: string): void;
export declare function getPkgVersion(pkgName: string): Record<string, string>;
export declare function getKldxVersions(): Record<string, string>;
export declare function getKldxVersionsStr(): string;
export declare function isMicroservice(): boolean;
export declare function getFaaSType(): string;
export declare function getAPaaSPersistFaaSMap(): Record<string, any>;
export declare function addPersistAPaaSValuetoHeader(options: HttpOptions): void;
export declare function getBizIDC(): string;
export declare function getServiceId(): string;
export declare function getServiceSecret(): string;
export declare function getOrgId(): string;
export declare function isKunlunOrg(): boolean;
export declare function getPrefixAPI(): string;
export declare function getClientId(): string;
export declare function getClientSecret(): string;
export declare function getOpenapiDomain(): string;
export declare function getFaasinfraDomain(): string;
export declare function decryptByTNameAndNS(encryptedText: string): string;
export declare function decryptBySvcIDAndNS(encryptedText: string): string;
export declare function paddingN(str: string, size: number): string;
export declare function aesDecryptText(fieldID: number, encryptedKey: string, encryptedText: string): string;
export declare function hexDecode(hex: string): string;
/**
 * 微服务环境变量解码
 * @param hexText 16进制文本
 * @param hexVector 16进制向量
 * @param utf8Key 解密秘钥
 */
export declare function aesCbcDecrypt(hexText: string, hexVector: string, utf8Key: string): string;
export declare function formatAuthType(authType: string): string;
export declare function getLaneID(): string;
export declare function getEnvID(): string;
export declare function getEnvType(): Number;
export declare function addLaneIDToHeader(options: HttpOptions): void;
export declare function addEnvIDToHeader(options: HttpOptions): void;
export declare function addFunctionAPIIDToHeader(options: HttpOptions): void;
export declare function addEnvTypeToHeader(options: HttpOptions): void;
export declare function getHttpHeaders(): Record<string, string>;
export declare function getFuncMetaConf(apiName: string): any;
export declare function getCurFuncMetaConf(): any;
export declare function getFuncAPIName(): string;
export declare function hasKeyPath(v: any, keyPath: string[]): boolean;
export declare function getValueByPath(v: any, keyPath: string[]): any;
export declare function delKeyPath(v: any, keyPath: string[]): void;
/**
 * 获取全局的鉴权类型，优先级低于接口级
 */
export declare function getGlobalAuthType(): string;
export declare function isCloseMesh(): boolean;
export declare function enableMesh(): boolean;
export declare function isTrueString(v: any): boolean;
export declare function getSocketAddr(): string;
export declare function isExternal(): boolean;
interface TraceHeader {
    traceparent?: string;
    tracestate?: string;
}
export declare function getTraceHeader(): TraceHeader;
export declare function setSDKInfo(fromSDK: string, fromVersion: string): void;
export declare function getInnerapiAPIPSM(): string;
export declare function getLGWPSM(): string;
export declare function getLGWCluster(): string;
export declare function getFaaSInfraPSM(): string;
export declare function isTmpUseLGW(): boolean;
export interface IServerInfo {
    psm: string;
    cluster: string;
}
export declare function getOpenAPIPSMAndCluster(): IServerInfo;
export declare function getFaaSInfraPSMAndCluster(): IServerInfo;
export declare function getServerInfo(server: string): IServerInfo;
export declare function getMeshDestReqTimeout(): number;
export declare function sleepMs(ms: number): Promise<void>;
export {};
