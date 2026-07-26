import { IOql } from './ioql';
import { AppCtx } from '../../../../application/application';
export declare class Oql implements IOql {
    oql: string;
    params: any[];
    namedParams: Record<string, any>;
    authType: string;
    appCtx?: AppCtx;
    constructor(oql: string, appCtx?: AppCtx);
    constructor(oql: string, namedArgs: Record<string, any>, appCtx?: AppCtx);
    execute(): Promise<any[]>;
    useSystemAuth(): IOql;
    useUserAuth(): IOql;
}
