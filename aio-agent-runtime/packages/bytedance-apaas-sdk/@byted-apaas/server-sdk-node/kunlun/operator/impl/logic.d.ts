import { Expression, UserDataType, ExpressionV3 } from './expression';
export declare class Condition {
    left: string;
    right: Condition | UserDataType;
    op: string;
    /**
     *
     * @param objectApiName 对象的ApiName
     * @param fieldApiName  字段的ApiName，指左值，即key
     * @param index         条件的排序
     * @returns {Expression}
     */
    toExpression(objectApiName: string, fieldApiName: string, index: number): Expression;
    constructor(left: string, right: Condition | UserDataType, op?: string);
}
export type Criterion = {
    conditions: Expression[];
    logic: string;
};
export type CriterionV3 = {
    conditions: ExpressionV3[];
    expression: string;
};
/**
 * 构造 criterion
 *
 * @param logic
 * @param objectApiName
 * @param maxId 添加 _id>maxId 条件，为 -1 表示不使用该参数
 */
export declare function buildCriterion(logic: Logic, objectApiName: string): Criterion;
export declare function buildExpression(objectApiName: string, left: string, right: Condition | UserDataType, index?: number): Expression;
/**
 * 在 criterion 中添加 _id>maxId 的判断条件
 *
 * @param criterion
 * @param apiName
 * @param maxId 添加 _id>maxId 条件
 */
export declare function addIDCriterion(criterion: Criterion, apiName: string, maxId: number): Criterion;
/**
 * 构造 convertCriterionToCriterionV3
 *
 * @param criterion v1 版本的条件
 */
export declare function convertCriterionToCriterionV3(criterion: Criterion): CriterionV3;
export declare class Logic {
    value: string;
    expressions: {
        [index: string]: any;
    };
    logics: Logic[];
    constructor(expressions?: {
        [index: string]: any;
    }, logicValue?: string);
    /**
     * 处理：右值包含逻辑表达式and|or的情况
     *
     * @param expressions
     * @param lookupField
     */
    handleRightLogic(expressions: {
        [index: string]: any;
    }, lookupField?: string): void;
    addLogic(logic: Logic): void;
}
export declare function buildLogic(param: (Logic | object)[], logicValue?: string): Logic;
export declare function handleCriterion(criterion: Criterion): Promise<Criterion>;
