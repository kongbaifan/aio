import { _Resources } from './resources/impl/resources';
import { Tasks } from './tasks/tasks';
import { Message } from './msg/msg';
import { IDBGetter } from './db/db';
import { Context as CommonContext } from '@byted-apaas/server-common-node';
import { IMetaData } from './metadata/metadata';
import { _IIntegration } from './integration/IIntegration';
export declare class Context<T, mt, cf, gv> extends CommonContext implements IContext<T, mt, cf, gv> {
    /**
     * 操作数据库中的记录数据
     */
    db: IDBGetter<T, mt>;
    /**
     * 元数据读写
     */
    metadata: IMetaData<mt>;
    /**
     * 静态资源类操作
     */
    resources: _Resources;
    /**
     * 全局函数
     * @param funcName 函数名
     */
    function(funcName: cf): {
        invoke: (params: any) => Promise<any>;
    };
    /**
     * 任务操作
     */
    tasks: Tasks<cf>;
    /**
     * 向消息中心推送及更新消息
     */
    msg: Message;
    /**
     * 根据 apiName 获取对应的全局变量
     * @param apiName 全局变量的 API Name
     */
    getVar<Key extends keyof gv>(apiName: Key): Promise<gv[Key]>;
    integration: _IIntegration;
}
export interface IContext<T, mt, cf, gv> {
}
