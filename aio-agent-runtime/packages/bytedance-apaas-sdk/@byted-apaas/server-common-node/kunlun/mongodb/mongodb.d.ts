export declare class MongoDB {
    /**
     * 获取 tableName 对应的 table 实例
     * @param tableName 表名
     */
    table(tableName: string): _MongoTable;
    /**
     * 一种随机生成的 id 类型，其能保证全局唯一且晚生成的 id 永远比早生成的 id 大
     */
    ObjectId: typeof _MongoObjectID;
}
interface _MongoRecord {
    id: number;
    [key: string]: any;
}
declare interface _MongoTable {
    /**
     * 空查询，无作用
     */
    where(): _MongoWhere & _MongoQuery;
    /**
     * 接收 null 或 undefined，无作用
     */
    where(arg: null | undefined): _MongoWhere & _MongoQuery;
    /**
     * 接收 string, 代表指定 key, 后接其他查询操作
     * @param key 指定的 key
     */
    where(key: string): _MongoWhere & _MongoQuery;
    /**
     * 接收 ObjectId, 代表按相应的 id 查询 _id 属性
     * @param id ObjectId
     */
    where(id: number): _MongoWhere & _MongoQuery;
    /**
     * 接收 ObjectId 数组, 代表按相应的 id 数组查询 _id 属性
     * @param ids ObjectId 数组
     */
    where(ids: number[]): _MongoWhere & _MongoQuery;
    /**
     * 指定数据库对象或数组，代表依据对象的 _id 查询
     * @param arg 数据库对象或数组
     */
    where(arg: _MongoRecord | _MongoRecord[]): _MongoWhere & _MongoQuery;
    /**
     * 指定键值对，代表相等查询的简写法
     * @param cond 相等查询条件
     */
    where(cond: object): _MongoWhere & _MongoQuery;
    /**
     * 指定查询函数，按照函数执行查询；该函数使用 this 代表用于判断条件的记录，返回真值代表通过查询条件，同时不可以使用闭包变量，也不可以抛出异常。
     * @param f
     * @paramExample function() {return this.a>10 || this.b instanceof Date}
     */
    where(f: () => boolean): _MongoWhere & _MongoQuery;
    /**
     * 生成一条数据库对象，并为之生成 _id 字段，返回该对象
     * @param obj 用于创建的原始对象，若传入数组，将会创建多个并返回数组
     */
    create(obj: object): any;
    /**
     * 执行将对象存入数据库的操作，返回数据库对象
     * @param obj 用于保存的数据库对象，若传入数组，将会执行批量操作
     */
    save(obj: object): any;
    /**
     * 执行将对象从数据库中删除的操作
     * @param obj 用于删除的数据库对象，若传入数组，将会执行批量操作
     */
    delete(obj: object): any;
}
declare interface _MongoQuery {
    /**
     * 执行查询操作，返回包含结果的数组，即使没有数据，也会返回一个空数组
     */
    find(): Promise<Record<string, any>[]>;
    /**
     * 执行查询操作，返回结果的第一条数据，若没有数据，返回 null
     */
    findOne(): Promise<Record<string, any>>;
    /**
     * 执行查询操作，返回结果的数据总条数
     */
    count(): Promise<number>;
    /**
     * 执行查询操作，返回结果的数据总条数
     */
    delete(): Promise<number>;
    /**
     * 执行查询并更新操作，返回更新的数据总条数
     */
    save(): Promise<number>;
    /**
     * 空查询，无作用
     */
    where(): _MongoWhere & _MongoQuery;
    /**
     * 接收 null 或 undefined，无作用
     */
    where(arg: null | undefined): _MongoWhere & _MongoQuery;
    /**
     * 接收 string, 代表指定 key, 后接其他查询操作
     * @param key 指定的 key
     */
    where(key: string): _MongoWhere & _MongoQuery;
    /**
     * 接收 ObjectId, 代表按相应的 id 查询 _id 属性
     * @param id ObjectId
     */
    where(id: number): _MongoWhere & _MongoQuery;
    /**
     * 接收 ObjectId 数组, 代表按相应的 id 数组查询 _id 属性
     * @param ids ObjectId 数组
     */
    where(ids: number[]): _MongoWhere & _MongoQuery;
    /**
     * 指定数据库对象或数组，代表依据对象的 _id 查询
     * @param arg 数据库对象或数组
     */
    where(arg: _MongoRecord | _MongoRecord[]): _MongoWhere & _MongoQuery;
    /**
     * 指定键值对，代表相等查询的简写法
     * @param cond 相等查询条件
     */
    where(cond: object): _MongoWhere & _MongoQuery;
    /**
     * 指定查询函数，按照函数执行查询；该函数使用 this 代表用于判断条件的记录，返回真值代表通过查询条件，同时不可以使用闭包变量，也不可以抛出异常。
     * @param f
     * @paramExample function() {return this.a>10 || this.b instanceof Date}
     */
    where(f: () => boolean): _MongoWhere & _MongoQuery;
    /**
     * 指定要更新的 key，后接其他操作
     * @param key 接收 string, 指定要更新的 key
     */
    set(key: string): _MongoSet & _MongoQuery;
    /**
     * 接收键值对, 是赋值更新的简写法
     * @param arg 赋值更新规则
     */
    set(arg: object): _MongoSet & _MongoQuery;
    /**
     * 特殊形式的 set，使用它将会保留记录 _id，其余字段全部删除，替换为 arg 指定的内容。使用后仍可以使用 upsert 模式，也可以指定setOnInsert，但其余 set 支持的链式操作全部无效。
     * @param arg 将替换为的新数据对象
     */
    replace(arg: object): _MongoReplace & _MongoQuery;
    /**
     * 所有数据分为一组进行聚合
     */
    groupBy(): _MongoGroupBy & _MongoQuery;
    /**
     * 指定字段名，根据该字段进行分组，并输出一个分组结果字段
     * @param field 字段名
     */
    groupBy(field: string): _MongoGroupBy & _MongoQuery;
    /**
     * 接收对象，根据一个包含表达式操作符的表达式进行聚合，并输出一个分组结果字段；输出结果字段为参数 JSON.stringify() 后的结果
     * @param expr 包含表达式操作符的表达式
     * @paramExample {$multiple: ['$a', '$b']}
     */
    groupBy(expr: object): _MongoGroupBy & _MongoQuery;
    /**
     * 对指定字段进行关联查询，等价于传入对象的形式，但仅指定 ref 属性
     * @param field 字段名
     */
    populate(field: string): _MongoQuery;
    /**
     * 对指定字段进行关联查询，接收对象，代表选项
     * @param opt 包含 ref, populate, table, projection 字段的字段
     * @paramExample
     */
    populate(opt: object): _MongoQuery;
}
declare interface _MongoWhere {
    /**
     * 指定查询的排序选项
     */
    sort(arg: object): _MongoWhere & _MongoQuery;
    /**
     * 指定查询的跳过前 n 项
     */
    skip(n: number): _MongoWhere & _MongoQuery;
    /**
     * 指定查询选择前 n 项
     */
    limit(n: number): _MongoWhere & _MongoQuery;
    /**
     * 指定查询选择某个索引，可以传入索引名或索引定义
     */
    hint(arg: object): _MongoWhere & _MongoQuery;
    /**
     * 指定查询结果返回筛选的字段
     */
    projection(arg: object): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值等于 value
     */
    equals(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值等于 value
     */
    eq(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值不等于 value
     */
    notEquals(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值不等于 value
     */
    ne(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值小于 value
     */
    lessThan(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值小于 value
     */
    lt(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值小于或等于 value
     */
    lessThanOrEquals(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值小于或等于 value
     */
    lte(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值大于 value
     */
    greaterThan(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值大于 value
     */
    gt(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值大于或等于 value
     */
    greaterThanOrEquals(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 的值大于或等于 value
     */
    gte(value: any): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 等于 array 中的一项
     */
    in(array: any[]): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 不等于 array 中的任何一项
     */
    notIn(array: any[]): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 不等于 array 中的任何一项
     */
    nin(array: any[]): _MongoWhere & _MongoQuery;
    /**
     * 判断当前指定的 key 匹配正则表达式 regexp
     */
    regex(regexp: string): _MongoWhere & _MongoQuery;
}
declare interface _MongoSet {
    /**
     * 声明此次更新为 upsert 模式，假如查询到的结果为空集，那么进行一次插入，此次插入以查询条件的所有相等条件构造基础对象，再以更新规则对基础对象进行更新，完成后插入数据库，查询条件的其余条件将被无视。另外，setOnInsert 的规则将在此时起作用
     */
    upsert(): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 的值赋值为 value
     */
    to(value: any): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 的值自增 value
     */
    increment(value: number): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 的值自增 value
     */
    inc(value: number): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 的值自乘 value
     */
    multiply(value: number): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 的值自乘 value
     */
    mul(value: number): _MongoSet & _MongoQuery;
    /**
     * 将 key 赋值为 min(originValue, value)，也就是，若原值大于 value，就赋值为 value
     */
    min(value: any): _MongoSet & _MongoQuery;
    /**
     * 将 key 赋值为 max(originValue, value)，也就是，若原值小于 value，就赋值为 value
     */
    max(value: any): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 重命名为 name
     */
    rename(name: string): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 从记录中删除
     */
    unset(): _MongoSet & _MongoQuery;
    /**
     * 将当前指定的 key 指定为当前的时间
     */
    currentDate(): _MongoSet & _MongoQuery;
    /**
     * upsert 模式下，若发生插入，将当前指定的 key 赋值为 value
     */
    setOnInsert(value: any): _MongoSet & _MongoQuery;
}
declare interface _MongoReplace {
    /**
     * 声明此次更新为 upsert 模式，假如查询到的结果为空集，那么进行一次插入，此次插入以查询条件的所有相等条件构造基础对象，再以更新规则对基础对象进行更新，完成后插入数据库，查询条件的其余条件将被无视。另外，setOnInsert 的规则将在此时起作用
     */
    upsert(): _MongoReplace & _MongoQuery;
    /**
     * upsert 模式下，若发生插入，将当前指定的 key 赋值为 value
     */
    setOnInsert(value: any): _MongoReplace & _MongoQuery;
}
declare interface _MongoGroupBy {
    /**
     * 聚合计算 API，计算分组的总和
     */
    sum(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，计算分组的平均值
     */
    avg(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，计算分组的总体标准差
     */
    stdDevPop(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，计算分组的样本标准差
     */
    stdDevSamp(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，计算分组的最小值
     */
    min(arg: any): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，计算分组的最大值
     */
    max(arg: any): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，取分组的第一项
     */
    first(arg: any): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，取分组的最后一项
     */
    last(arg: any): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，分组的所有值整合为数组
     */
    mergeToArray(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，分组的所有值整合为数组，并去重
     */
    mergeToSet(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，分组的所有 Object 值整合为一个 Object
     */
    mergeToObject(arg: object): _MongoGroupBy & _MongoQuery;
    /**
     * 聚合计算 API，返回分组总共有几条数据
     */
    num(): number;
    /**
     * 将上一个 groupBy 或聚合计算 API 产生的新字段进行重命名
     */
    as(name: string): _MongoGroupBy & _MongoQuery;
}
declare class _MongoObjectID {
    /**
     * 生成新的 ObjectId
     */
    constructor();
    /**
     * 根据参数生成对应的 ObjectId
     * @param id 用于生成 ObjectId 的内容
     */
    constructor(id: string);
    /**
     * 比较 ObjectId 是否相等
     * @param id 用于比较的 ObjectId 或字符串内容
     */
    equals(id: string | _MongoObjectID): boolean;
}
export {};
