export interface IMongodb {
    /**
     * Create a new ObjectId instance
     * @param _id Can be a 24 byte hex string, 12 byte binary string or a Number.
     */
    ObjectId(_id?: number | string): any;
    /**
     * Create a new Table instance
     * @param tableName tableName
     */
    table(tableName: string): ITable;
    and(...data: any[]): ICondition;
    or(...data: any[]): ICondition;
    nor(...data: any[]): ICondition;
    eq(data: any): ICondition;
    ne(data: any): ICondition;
    gt(data: any): ICondition;
    gte(data: any): ICondition;
    lt(data: any): ICondition;
    lte(data: any): ICondition;
    in(data: any[]): ICondition;
    nin(data: any[]): ICondition;
    not(data: any): ICondition;
    exists(existance: boolean): ICondition;
    mod(modExpr: [number, number]): ICondition;
    regex(reg: RegExp): ICondition;
    all(elements: any[]): ICondition;
    elemMatch(expr: any): ICondition;
    size(n: number): ICondition;
    bitsAllClear(bitPos: number[]): ICondition;
    bitsAllSet(bitPos: number[]): ICondition;
    bitsAnyClear(bitPos: number[]): ICondition;
    bitsAnySet(bitPos: number[]): ICondition;
    geoIntersects(geoObjExpr: any): ICondition;
    geoWithin(geoObjExpr: any): ICondition;
    near(geoObjExpr: any): ICondition;
    nearSphere(geoObjExpr: any): ICondition;
    literal(constant: any): ICondition;
    abs(expr: any): ICondition;
    add(exprs: any[]): ICondition;
    cmp(expr: [any, any]): ICondition;
    ceil(expr: any): ICondition;
    divide(expr: [any, any]): ICondition;
    exp(expr: any): ICondition;
    floor(expr: any): ICondition;
    ln(expr: any): ICondition;
    log(expr: [any, any]): ICondition;
    log10(expr: any): ICondition;
    mod(expr: [any, any]): ICondition;
    multiply(expr: any[]): ICondition;
    pow(expr: [any, any]): ICondition;
    round(expr: any): ICondition;
    sqrt(expr: any): ICondition;
    subtract(expr: [any, any]): ICondition;
    cond(condIfElse: [any, any, any]): ICondition;
    ifNull(condIfNull: [any, any]): ICondition;
    switch(branches: {
        cases: {
            case: any;
            then: any;
        }[];
        default: any;
    }): ICondition;
    dayOfMonth(expr: any): ICondition;
    dayOfWeek(expr: any): ICondition;
    dayOfYear(expr: any): ICondition;
    hour(expr: any): ICondition;
    millisecond(expr: any): ICondition;
    minute(expr: any): ICondition;
    month(expr: any): ICondition;
    second(expr: any): ICondition;
    week(expr: any): ICondition;
    year(expr: any): ICondition;
    concat(expr: any[]): ICondition;
    dateFromString(expr: {
        dateString: string;
        format: string;
        timezone: string;
        onError: any;
        onNull: any;
    }): ICondition;
    dateToString(expr: {
        format: string;
        date: string;
        timezone: string;
        onError: any;
    }): ICondition;
    indexOfBytes(expr: [any, any, number, number]): ICondition;
    indexOfCP(expr: [any, any, number, number]): ICondition;
    ltrim(expr: any): ICondition;
    rtrim(expr: any): ICondition;
    split(expr: [any, string]): ICondition;
    strLenBytes(expr: any): ICondition;
    strLenCP(expr: any): ICondition;
    strcasecmp(expr: any[]): ICondition;
    substrBytes(expr: [any, number, number]): ICondition;
    substrCP(expr: [any, number, number]): ICondition;
    toLower(expr: any): ICondition;
    toString(expr: any): ICondition;
    toUpper(expr: any): ICondition;
    trim(expr: any): ICondition;
}
export interface ITable {
    /**
     * 创建，不会真正入库
     * @param record 记录数据
     */
    create(record: any): any;
    /**
     * 创建或更新
     * @param record 记录数据
     */
    save(record: any): Promise<any>;
    /**
     * 删除
     * @param record 记录数据
     */
    delete(record: Record<string, any> | Record<string, any>[]): Promise<any>;
    where(): IQuery;
    where(value: any): IQuery;
}
export interface IQuery {
    count(): Promise<number>;
    find(): Promise<Array<any>>;
    findOne(): Promise<any>;
    save(): Promise<any>;
    delete(): Promise<any>;
    currentDate(): IQuery;
    eq(value: any): IQuery;
    equals(value: any): IQuery;
    greaterThan(value: any): IQuery;
    greaterThanOrEquals(value: any): IQuery;
    gt(value: any): IQuery;
    gte(value: any): IQuery;
    /**
     * 指定查询选择某个索引
     *
     * @param value 索引名或索引定义
     */
    hint(value: any): IQuery;
    in(array: Array<any>): IQuery;
    inc(value: any): IQuery;
    increment(value: any): IQuery;
    lessThan(value: any): IQuery;
    lessThanOrEquals(value: any): IQuery;
    limit(value: number): IQuery;
    lt(value: any): IQuery;
    lte(value: any): IQuery;
    max(value: any): IQuery;
    min(value: any): IQuery;
    mul(value: any): IQuery;
    multiply(value: any): IQuery;
    ne(value: any): IQuery;
    near(geo: any, max: number, min: number): IQuery;
    nin(array: Array<any>): IQuery;
    notEquals(value: any): IQuery;
    notIn(array: Array<any>): IQuery;
    projection(value: any): IQuery;
    regex(value: any): IQuery;
    rename(value: string): IQuery;
    replace(value: any): IQuery;
    set(value: any): IQuery;
    setOnInsert(value: any): IQuery;
    skip(value: number): IQuery;
    sort(value: any): IQuery;
    to(value: any): IQuery;
    unset(): IQuery;
    upsert(): IQuery;
    where(value?: any): IQuery;
    and(value: any): IQuery;
    or(value: any): IQuery;
    nor(value: any): IQuery;
    groupBy(field?: string | any): IQuery;
    as(alias: string): IQuery;
    sum(field: string | any): IQuery;
    avg(field: string | any): IQuery;
    stdDevPop(field: string | any): IQuery;
    stdDevSamp(field: string | any): IQuery;
    first(field: string | any): IQuery;
    last(field: string | any): IQuery;
    mergeToArray(field: string | any): IQuery;
    mergeToSet(field: string | any): IQuery;
    mergeToObject(field: string | any): IQuery;
    num(): IQuery;
    /**
     * 关联查询
     *
     * @param value 关联查询规则，类型为字符串、对象或数组
     */
    populate(value: string | Population | string[] | Population[]): IQuery;
}
export declare class Population {
    from: string;
    localField: string;
    foreignField: string;
    as?: string;
}
export interface ICondition {
    eq(data: any): ICondition;
    ne(data: any): ICondition;
    gt(data: any): ICondition;
    gte(data: any): ICondition;
    lt(data: any): ICondition;
    lte(data: any): ICondition;
    in(data: any[]): ICondition;
    nin(data: any[]): ICondition;
    not(data: any): ICondition;
    exists(existance: boolean): ICondition;
    mod(modExpr: [number, number]): ICondition;
    regex(reg: RegExp): ICondition;
    all(elements: any[]): ICondition;
    elemMatch(expr: any): ICondition;
    size(n: number): ICondition;
    bitsAllClear(bitPos: number[]): ICondition;
    bitsAllSet(bitPos: number[]): ICondition;
    bitsAnyClear(bitPos: number[]): ICondition;
    bitsAnySet(bitPos: number[]): ICondition;
    geoIntersects(geoObjExpr: any): ICondition;
    geoWithin(geoObjExpr: any): ICondition;
    near(geoObjExpr: any): ICondition;
    nearSphere(geoObjExpr: any): ICondition;
    literal(constant: any): ICondition;
    abs(expr: any): ICondition;
    add(exprs: any[]): ICondition;
    cmp(expr: [any, any]): ICondition;
    ceil(expr: any): ICondition;
    divide(expr: [any, any]): ICondition;
    exp(expr: any): ICondition;
    floor(expr: any): ICondition;
    ln(expr: any): ICondition;
    log(expr: [any, any]): ICondition;
    log10(expr: any): ICondition;
    mod(expr: [any, any]): ICondition;
    multiply(expr: any[]): ICondition;
    pow(expr: [any, any]): ICondition;
    round(expr: any): ICondition;
    sqrt(expr: any): ICondition;
    subtract(expr: [any, any]): ICondition;
    cond(condIfElse: [any, any, any]): ICondition;
    ifNull(condIfNull: [any, any]): ICondition;
    switch(branches: {
        cases: {
            case: any;
            then: any;
        }[];
        default: any;
    }): ICondition;
    dayOfMonth(expr: any): ICondition;
    dayOfWeek(expr: any): ICondition;
    dayOfYear(expr: any): ICondition;
    hour(expr: any): ICondition;
    millisecond(expr: any): ICondition;
    minute(expr: any): ICondition;
    month(expr: any): ICondition;
    second(expr: any): ICondition;
    week(expr: any): ICondition;
    year(expr: any): ICondition;
    concat(expr: any[]): ICondition;
    dateFromString(expr: {
        dateString: string;
        format: string;
        timezone: string;
        onError: any;
        onNull: any;
    }): ICondition;
    dateToString(expr: {
        format: string;
        date: string;
        timezone: string;
        onError: any;
    }): ICondition;
    indexOfBytes(expr: [any, any, number, number]): ICondition;
    indexOfCP(expr: [any, any, number, number]): ICondition;
    ltrim(expr: any): ICondition;
    rtrim(expr: any): ICondition;
    split(expr: [any, string]): ICondition;
    strLenBytes(expr: any): ICondition;
    strLenCP(expr: any): ICondition;
    strcasecmp(expr: any[]): ICondition;
    substrBytes(expr: [any, number, number]): ICondition;
    substrCP(expr: [any, number, number]): ICondition;
    toLower(expr: any): ICondition;
    toString(expr: any): ICondition;
    toUpper(expr: any): ICondition;
    trim(expr: any): ICondition;
}
