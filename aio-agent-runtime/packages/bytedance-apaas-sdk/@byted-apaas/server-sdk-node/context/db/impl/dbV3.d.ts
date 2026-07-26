import { ITransactionGetter } from './transaction';
import { IDBV3 } from '../db';
import { metadataMap } from '../../../data/index';
import { _IKAllEndpointV3, _IKQueryV3 } from './IObjectV3';
export declare class DBV3<T, mt = metadataMap> implements IDBV3<T, mt> {
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
    object<K extends keyof mt>(objectApiName: K): _IKAllEndpointV3<mt[K]> & _IKQueryV3<mt[K]>;
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
}
