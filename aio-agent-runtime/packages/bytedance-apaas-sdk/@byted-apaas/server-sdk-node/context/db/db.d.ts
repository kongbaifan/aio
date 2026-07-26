import { _IKAllEndpoint, _IKSyncEndpoint, _IKQuery } from './impl/IObject';
import { ITransactionGetter } from './impl/transaction';
import { IOql } from './impl/oql/ioql';
import { _IKAllEndpointV3, _IKQueryV3 } from './impl/IObjectV3';
/**
 * IDBGetter 是声明 DB interface 的顶级入口
 */
export type IDBGetter<T, mt> = T extends {
    'objectApiName': string;
} ? IDB<T, mt> & IDBWithCurrentObject<{}, mt> : IDB<{}, mt>;
/**
 * IDB 经由 IDBGetter 返回，是 DB 的基础接口结构
 */
export interface IDB<T, mt> {
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    object<T extends keyof mt>(objectApiName: T): _IKAllEndpoint<mt[T]> & _IKQuery<mt[T]>;
    /**
     * 创建一个新的空事务
     * @example
     * ```
     * let tx = application.data.newTransaction();
     * let user = tx.object('_user').registerCreate({
     *     _name: new application.constants.type.Multilingual({ zh: '用户1', en: 'user1' }),
     * });
     * let contract = tx.object('contract').registerCreate({
     *     _name: new application.constants.type.Multilingual({ zh: '用户1的合同', en: 'user1's contract' }),
     *     user: {id: user._id}
     * });
     * await tx.commit();
     * ```
     */
    newTransaction(): ITransactionGetter<T, mt>;
    /**
     * OQL 操作
     * @param oql OQL 语句
     * @example
     * ```
     * let users = await application.data.oql('select _email from _user').execute();
     * ```
     */
    oql(oql: string): IOql;
    /**
     * OQL 操作
     * @param oql OQL 语句
     * @param nameArgs 用于替换 OQL 语句中的占位符
     * @example
     * ```
     * let employees = await application.data.oql('select _email from _user where _type = $user_type',{
     *     'user_type': '_employee',
     * }).execute();
     * ```
     */
    oql(oql: string, nameArgs: Record<string, any>): IOql;
}
/**
 * IDB3 经由 IDBGetter 返回，是 DBV3 的基础接口结构
 */
export interface IDBV3<T, mt> {
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    object: <T extends keyof mt>(objectApiName: T) => _IKAllEndpointV3<mt[T]> & _IKQueryV3<mt[T]>;
    /**
     * 创建一个新的空事务
     * @example
     * ```
     * let tx = application.data.newTransaction();
     * let user = tx.object('_user').registerCreate({
     *     _name: new application.constants.type.Multilingual({ zh: '用户1', en: 'user1' }),
     * });
     * let contract = tx.object('contract').registerCreate({
     *     _name: new application.constants.type.Multilingual({ zh: '用户1的合同', en: 'user1's contract' }),
     *     user: {id: user._id}
     * });
     * await tx.commit();
     * ```
     */
    newTransaction(): ITransactionGetter<T, mt>;
}
/**
 * IDBWithCurrentObject 经由 IDBGetter 返回，是 DB 的动态增加的接口结构
 */
export interface IDBWithCurrentObject<T, mt> {
}
/**
 * IDBSync 仅包含同步调用接口，当前应用场景为 OpenSDK
 */
export interface IDBSync<mt = Record<string, never>> {
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     */
    object(objectApiName: string): _IKSyncEndpoint<mt> & _IKQuery<mt>;
}
