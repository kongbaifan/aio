import { _IOpenSDKResources } from '../context/resources/IResources';
import { ITool, IToolsExtra } from '@byted-apaas/server-common-node/kunlun/tool/Itool';
import { AppCredential } from '@byted-apaas/server-common-node/credential/credential';
import { IDBSync } from '../context/db/db';
import { IFunction } from './function/function';
import { PlatformEnvType } from '@byted-apaas/server-common-node/constants/constants';
import { _IIntegration } from '../context/integration/IIntegration';
/**
 * IApplication 为 OpenSDK 能力的核心接口
 *   - data:     元数据相关能力
 *   - resource: 资源相关能力
 *   - tools:    工具相关能力
 */
export interface IApplication {
    data: IDBSync;
    resources: _IOpenSDKResources;
    tools: ITool & IToolsExtra;
    integration: _IIntegration;
    cloudfunction(funcName: string): IFunction;
    env(platformEnvType: PlatformEnvType): IApplication;
    localDebugMode(): IApplication;
    setLaneName(laneName: string): IApplication;
}
export type AppMode = 'openSDK' | 'faasSDK';
export type DataVersion = 'v1' | 'v2' | 'v3';
export interface AppCtx {
    mode?: AppMode;
    env?: PlatformEnvType;
    credential?: AppCredential;
    debugType?: '0' | '2';
    x_tt_env?: string;
    dataVersion?: DataVersion;
}
