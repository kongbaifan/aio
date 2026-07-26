import { _Cond } from '../../../types/types';
export type ITransactionGetter<T, mt> = T extends {
    'objectApiName': string;
} ? ITransaction<mt> : ITransaction<mt> & ITransactionWithCurrentObject<mt>;
export interface ITransaction<mt> {
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     */
    object<T extends keyof mt>(objectApiName: T): TransactionObject<mt[T]>;
    /**
     * 提交事务
     */
    commit(): Promise<void>;
    /**
     * 用户级鉴权
     */
    useUserAuth(): this;
    /**
     * 系统级鉴权
     */
    useSystemAuth(): this;
}
export interface ITransactionWithCurrentObject<mt> {
}
export interface TransactionObject<T> {
    /**
     * 注册创建单条记录，返回仅在事务中生效的临时记录 ID，该 ID 将在事务执行完毕后更新为实际记录 ID
     * @param recordMap 用于创建的一条记录
     */
    registerCreate(recordMap: _Cond<T>): {
        _id: string | number;
    };
    /**
     * 注册删除单条记录
     * @param recordID 用于删除的一条记录的 ID
     */
    registerDelete(recordID: (string | number)): void;
    /**
     * 注册删除单条记录
     * @param record 用于删除的一条完整记录
     */
    registerDelete(record: _Cond<T>): void;
    /**
     * 注册更新单条记录
     * @param recordMap 用于更新的一条记录，需对 _id 赋值
     */
    registerUpdate(recordMap: _Cond<T>): void;
    /**
     * 注册更新单条记录
     * @param _id 主键
     * @param recordMap 用于更新的一条记录
     */
    registerUpdate(_id: (string | number), recordMap: _Cond<T>): void;
    /**
     * 注册批量创建记录，返回仅在事务中生效的临时记录 ID 数组，该 ID 将在事务执行完毕后更新为实际记录 ID
     * @param recordMaps 用于批量创建的一批记录
     */
    registerBatchCreate(recordMaps: _Cond<T>[]): (string | number)[];
    /**
     * 注册批量删除记录
     * @param recordIDs 用于删除的一批记录的 ID or 完整记录
     */
    registerBatchDelete(recordIDs: (string | number | _Cond<T>)[]): void;
    /**
     * 注册批量更新记录
     * @param recordMaps 用于更新的一批记录，需对每个记录的 _id 赋值
     */
    registerBatchUpdate(recordMaps: _Cond<T>[]): void;
}
