import { ITool, IToolsExtra } from '@byted-apaas/server-common-node/kunlun/tool/Itool';
import { IFunction } from '../function/function';
import { IApplication } from '../application';
import { _IOpenSDKResources } from '../../context/resources/IResources';
import { IDBSync } from '../../context/db/db';
import { PlatformEnvType } from '@byted-apaas/server-common-node/constants/constants';
import { _IIntegration } from '../../context/integration/IIntegration';
export declare class Application implements IApplication {
    private appCtx;
    data: IDBSync;
    resources: _IOpenSDKResources;
    tools: ITool & IToolsExtra;
    integration: _IIntegration;
    constructor(clientID: string, clientSecret: string);
    cloudfunction(funcName: string): IFunction;
    env(platformEnvType: PlatformEnvType): IApplication;
    localDebugMode(): IApplication;
    setLaneName(laneName: string): IApplication;
}
