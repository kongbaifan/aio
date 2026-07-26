import { _IKAllEndpoint, _IKSyncEndpoint, _IKQuery } from './IObject';
import { ITransactionGetter } from './transaction';
import { IDB, IDBSync, IDBWithCurrentObject } from '../db';
import { currentObjApiName, metadataMap } from '../../../data/index';
import { IOql } from './oql/ioql';
import { AppCtx } from '../../../application/application';
export declare class DB<T, mt = metadataMap> implements IDB<T, mt> {
    objectApiName: string;
    constructor(objectApiName?: string);
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     * @example
     * ```
     * context.db.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    object<K extends keyof mt>(objectApiName: K): _IKAllEndpoint<mt[K]> & _IKQuery<mt[K]>;
    /**
     * 创建一个新的空事务
     * @example
     * ```
     * let tx = context.db.newTransaction();
     * let user = tx.object('_user').registerCreate({
     *     _name: new kunlun.type.Multilingual({ zh: '用户1', en: 'user1' }),
     * });
     * let contract = tx.object('contract').registerCreate({
     *     _name: new kunlun.type.Multilingual({ zh: '用户1的合同', en: 'user1's contract' }),
     *     user: {id: user._id}
     * });
     * await tx.commit();
     * ```
     */
    newTransaction(): ITransactionGetter<T, mt>;
    /**
     * OQL 操作
     * @param oql 指定 OQL 语句
     * @example
     * ```
     * let users = await context.db.oql('select _email from _user').execute();
     * ```
     */
    oql(oql: string): IOql;
    oql(oql: string, nameArgs: Record<string, any>): IOql;
}
export declare class DBWithCurrentObject<T, mt = metadataMap> extends DB<T, mt> implements IDB<T, mt>, IDBWithCurrentObject<T, mt> {
    /**
     * 无需入参，操作当前对象的记录数据
     */
    currentObject(): _IKAllEndpoint<mt[currentObjApiName]> & _IKQuery<mt[currentObjApiName]>;
    constructor(objectApiName: string);
}
/**
 * ApplicationDB: 用于支持 OpenSDK 相关能力的 DB 相关类，目前仅实现 DB 同步操作接口
 */
export declare class ApplicationDB implements IDBSync {
    appCtx: AppCtx;
    constructor(appCtx: AppCtx);
    object(objectApiName: string): _IKSyncEndpoint<{}> & _IKQuery<{}>;
}
