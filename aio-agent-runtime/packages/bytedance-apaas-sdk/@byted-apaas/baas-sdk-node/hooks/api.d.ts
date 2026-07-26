import { IMongodb } from '../mongodb/mongodb';
import { IRedis } from '../redis/IRedis';
import { IFile } from '../file/IFile';
import * as common from '@byted-apaas/server-common-node';
import { IGlobalVar } from "../global_var/global_var";
export declare const mongodb: IMongodb;
export declare const redis: IRedis;
export declare const oss: IFile;
export declare const globalVar: IGlobalVar;
export declare function getFunctionSync(context?: any, logger?: common.Logger): (funcName: string) => {
    invoke: (params?: any) => Promise<any>;
};
