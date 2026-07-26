import { IQuery, Population } from '../mongodb';
export declare class Query implements IQuery {
    private readonly tableName;
    private args;
    private wherePath;
    private updatePath;
    constructor(tableName: string);
    private buildRequestParam;
    /**
     * 查询记录，最大 1000 条
     */
    find(): Promise<Array<any>>;
    /**
     * 查询单条记录
     */
    findOne(): Promise<any>;
    count(): Promise<number>;
    delete(): Promise<any>;
    save(): Promise<any>;
    projection(value: any): IQuery;
    sort(value: any): IQuery;
    skip(value: number): IQuery;
    limit(value: number): IQuery;
    groupBy(field?: string | any): IQuery;
    as(alias: string): IQuery;
    sum(field: any): IQuery;
    avg(field: any): IQuery;
    min(field: any): IQuery;
    max(field: any): IQuery;
    num(): IQuery;
    first(field: any): IQuery;
    last(field: any): IQuery;
    stdDevPop(field: any): IQuery;
    stdDevSamp(field: any): IQuery;
    mergeToArray(field: any): IQuery;
    mergeToObject(field: any): IQuery;
    mergeToSet(field: any): IQuery;
    private whereOp;
    equals(value: any): IQuery;
    eq(value: any): IQuery;
    notEquals(value: any): IQuery;
    ne(value: any): IQuery;
    greaterThan(value: any): IQuery;
    gt(value: any): IQuery;
    greaterThanOrEquals(value: any): IQuery;
    gte(value: any): IQuery;
    lessThan(value: any): IQuery;
    lt(value: any): IQuery;
    lessThanOrEquals(value: any): IQuery;
    lte(value: any): IQuery;
    in(value: Array<any>): IQuery;
    notIn(value: Array<any>): IQuery;
    nin(value: Array<any>): IQuery;
    regex(value: any): IQuery;
    near(geo: any, max: number, min?: number): IQuery;
    set(value: any): IQuery;
    private updateSetOp;
    to(value: any): IQuery;
    increment(value: any): IQuery;
    inc(value: any): IQuery;
    multiply(value: any): IQuery;
    mul(value: any): IQuery;
    currentDate(): IQuery;
    rename(value: string): IQuery;
    unset(): IQuery;
    setOnInsert(value: any): IQuery;
    /**
     * 关联查询 TODO 暂不支持
     *
     * @param value 关联查询规则，类型为字符串、对象或数组
     */
    populate(value: string | Population | string[] | Population[]): IQuery;
    replace(value: any): IQuery;
    upsert(): IQuery;
    /**
     * 指定查询选择某个索引
     *
     * @param value 索引名或索引定义
     */
    hint(value: any): IQuery;
    where(condition?: any): IQuery;
    and(...conditions: any[]): IQuery;
    or(...conditions: any[]): IQuery;
    nor(...conditions: any[]): IQuery;
    private handleCondition;
    private convertFilter;
}
