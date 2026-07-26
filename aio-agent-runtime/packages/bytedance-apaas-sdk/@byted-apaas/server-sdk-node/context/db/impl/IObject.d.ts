import { _Cond, _Record, _WhereCond } from '../../../types/types';
import { BatchResult } from '../../../common/structs';
export interface _IKAllEndpoint<T> extends _IKSyncEndpoint<T>, _IKAsyncEndpoint<T> {
}
export interface _IKSyncEndpoint<T> {
    /**
     * 创建记录
     * @param recordMap 用于创建的一条记录
     * @paramExample {_name: 'John', age: 19, gender: 'male'}
     * @example
     * ```
     * application.data.object('_department').create({
     *     _name: new application.constants.type.Multilingual({ zh: '部门' }),
     *     _manager: { _id: 1660000000 },
     *     _status: '_active'
     * })
     * ```
     */
    create(recordMap: _Cond<T>): Promise<{
        _id: number | string;
    }>;
    /**
     * 删除记录
     * @param recordID 用于删除的一条记录的 ID
     * @example
     * ```
     * application.data.object('_user').delete(123456789123)
     * ```
     */
    delete(recordID: number): Promise<void>;
    /**
     * 删除记录
     * @param record 用于删除的一条完整记录
     * @example
     * ```
     * application.data.object('_user').delete(context.targetRecord.original)
     * ```
     */
    delete(record: _Cond<T>): Promise<void>;
    /**
     * 指定 _id 后，更新对应记录
     * @param _id 主键
     * @param recordMap 用于更新的一条记录
     * @paramExample {_name: 'John', age: 19, gender: 'male'}
     * @example
     * ```
     * application.data.object('_user').update(1660000000, {
     *     gender: 'male'
     * })
     * ```
     */
    update(_id: number, recordMap: _Cond<T>): Promise<void>;
    /**
     * 指定 _id 后，更新对应记录
     * @param recordMap 用于更新的一条记录，需对 _id 赋值
     * @paramExample {_id: 1660000000, _name: 'John', age: 19, gender: 'male'}
     * @example
     * ```
     * application.data.object('_user').update({
     *     _id: 1660000000,
     *     gender: 'male'
     * })
     * ```
     */
    update(recordMap: _Cond<T>): Promise<void>;
    /**
     * 批量创建记录
     * @param recordMapList 多条用于创建的记录数据组成的数组
     * @paramExample [{_name: 'John', age: 19, gender: 'male'}, {_name: 'Alis', age: 16, gender: 'female'}]
     */
    batchCreate(recordMapList: _Cond<T>[]): Promise<number[] | string[]>;
    /**
     * 批量删除记录
     * @param recordIdList 多个用于删除的记录 ID 组成的数组
     * @paramExample [1001, 1002, 1003]
     */
    batchDelete(recordIdList: number[]): Promise<BatchResult>;
    /**
     * 批量删除记录
     * @param recordList 多条用于删除的记录数据组成的数组，记录数据需对 _id 赋值
     * @paramExample [{_id: 1001, _name: 'John', gender: 'male'}, {_id: 1002, _name: 'Alis', gender: 'female'}]
     */
    batchDelete(recordList: _Cond<T>[]): Promise<BatchResult>;
    /**
     * 根据 _id 批量更新记录
     * @param recordMapList 多条用于更新的记录数据组成的数组，记录数据需对 _id 赋值
     * @paramExample [{_id: 1001, _name: 'John', gender: 'male'}, {_id: 1002, _name: 'Alis', gender: 'female'}]
     */
    batchUpdate(recordMapList: _Cond<T>[]): Promise<BatchResult>;
    /**
     * 用户级鉴权
     */
    useUserAuth(): this;
    /**
     * 系统级鉴权
     */
    useSystemAuth(): this;
}
export interface _IKAsyncEndpoint<T> {
    /**
     * 批量创建记录（为异步任务）
     * @param recordMapList 用于创建的多条记录
     * @paramExample [{_name: 'John', age: 19, gender: 'male'}, {_name: 'Alis', age: 16, gender: 'female'}]
     */
    batchCreateAsync(recordMapList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    /**
     * 批量删除记录（为异步任务）
     * @param recordIDList 用于删除的多条记录的 ID 列表
     */
    batchDeleteAsync(recordIDList: number[]): Promise<{
        taskID: number;
    }>;
    /**
     * 批量删除记录（为异步任务）
     * @param recordList 用于删除的多条完整记录的列表
     */
    batchDeleteAsync(recordList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    /**
     * 根据 _id 批量更新记录（为异步任务）
     * @param recordMapList 用于更新的多条记录，需对 _id 赋值
     * @paramExample [{_id: 1001, _name: 'John', gender: 'male'}, {_id: 1002, _name: 'Alis', gender: 'female'}]
     */
    batchUpdateAsync(recordMapList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    /**
     * 用户级鉴权
     */
    useUserAuth(): this;
    /**
     * 系统级鉴权
     */
    useSystemAuth(): this;
}
export interface _IKQuery<T> {
    /**
     * @Deprecated Use FindStream instead.
     *
     * 无需入参，返回全部符合条件的记录
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).findAll()
     * ```
     */
    findAll(): Promise<_Record<T>[]>;
    /**
     * 遍历全部符合条件的记录
     * 注：
     *   如果未设置排序字段，默认以 _id 增序查询；
     *   如果有设置排序字段，必须设置具有唯一属性的字段，否则会有数据重复的风险；
     * @param handler 业务处理函数
     * @param pageLimit 分页查询的数量，可选参数，默认值为 200，
     * @example
     * ```
     * await application.data.object('_user').findStream(async (records) => {
     *     // doSomething ...
     * }, 300);
     * ```
     */
    findStream: (handler: (records: object[]) => Promise<void>, pageLimit?: number) => Promise<void>;
    /**
     * 无需入参，返回符合条件的记录，单次返回 200 条
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    find(): Promise<_Record<T>[]>;
    /**
     * 无需入参，返回排在第一位的记录
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).findOne()
     * ```
     */
    findOne(): Promise<_Record<T>>;
    /**
     * 根据指定字段升序排序（a -> z, 0 -> 9）
     * @param fieldApiNames 排序依据的字段数组，按先后顺序确定优先级
     * @example
     * ```
     * application.data.object('_user').orderBy(['_email', '_phoneNumber']).find()
     * ```
     */
    orderBy<K extends keyof T>(fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 根据指定字段升序排序（a -> z, 0 -> 9）
     * @param fieldApiNames 排序依据的字段，按先后顺序确定优先级，用逗号分隔
     * @example
     * ```
     * application.data.object('_user').orderBy('_email', '_phoneNumber').find()
     * ```
     */
    orderBy<K extends keyof T>(...fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 根据指定字段降序排序（z -> a, 9 -> 0）
     * @param fieldApiNames 排序依据的字段数组，按先后顺序确定优先级
     * @example
     * ```
     * application.data.object('_user').orderByDesc('_email', '_phoneNumber').find()
     * ```
     */
    orderByDesc<K extends keyof T>(fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 根据指定字段降序排序（z -> a, 9 -> 0）
     * @param fieldApiNames 排序依据的字段，按先后顺序确定优先级，用逗号分隔
     * @example
     * ```
     * application.data.object('_user').orderByDesc('_email', '_phoneNumber').find()
     * ```
     */
    orderByDesc<K extends keyof T>(...fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 指定需返回的字段
     * @param fieldApiNames 需返回的字段数组
     * @example
     * ```
     * application.data.object('_user').select(['_name', '_email']).find()
     * ```
     */
    select<K extends keyof T>(fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 指定需返回的字段
     * @param fieldApiNames 需返回的字段，用逗号分隔
     * @example
     * ```
     * application.data.object('_user').select('_name', '_email').find()
     * ```
     */
    select<K extends keyof T>(...fieldApiNames: K[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 设置查询条件
     * @param conditionMap 对字段赋值以指定查询筛选条件
     * @paramExample {gender: 'male'}
     * @example
     * ```
     * application.data.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    where(conditionMap: _WhereCond<T>): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 设置查询条件
     */
    where(): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 模糊查询：与 where 之间是与关系
     * @param keyword 模糊查询的关键字，必填且不可以为空串
     * @param fieldAPINames 『可搜索字段』的字段列表，不可为空
     * @example
     * ```
     * application.data.object('_user').fuzzySearch('张三', ['_name']).find()
     * ```
     */
    fuzzySearch(keyword: string, fieldAPINames: string[]): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 指定分页查询的数量
     * @param limit 分页查询的数量
     * @paramExample 10
     * @example
     * ```
     * application.data.object('_user').limit(10)
     * ```
     */
    limit(limit: number): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 指定分页查询的偏移量
     * @param offset 分页查询的偏移量
     * @paramExample 0
     * @example
     * ```
     * application.data.object('_user').offset(0)
     * ```
     */
    offset(offset: number): Omit<_IKQuery<T>, 'findAll'>;
    /**
     * 指定条件的行数
     * @example
     * ```
     * application.data.object('_user').count()
     * ```
     */
    count(): Promise<number>;
    /**
     * 用户级鉴权
     */
    useUserAuth(): this;
    /**
     * 系统级鉴权
     */
    useSystemAuth(): this;
}
