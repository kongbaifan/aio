import { OrderV2 } from '../../../request/interface';
import { UserDataType } from './expression';
export type FieldPath = {
    objectApiName: string;
    fieldApiName: string;
    extendLogicTags: string[];
};
export type SettingType = {
    data?: any;
    fieldPath?: FieldPath[];
};
export type Expression = {
    type: string;
    settings: SettingType;
};
export declare function NewMetadataExpressionField(objectApiName: string, fieldApiName: string): Expression;
export declare function NewConstantExpressionField(data: UserDataType): Expression;
export type ExpressionV2 = {
    leftValue: string;
    operator: string;
    rightValue: any;
};
export declare class ArithmeticExpression {
    left: Expression;
    operator: string;
    right: Expression;
    expr: ExpressionV2;
    constructor(leftValue: string, op: string, rightValue: any);
}
export declare class LogicalExpression {
    type: string;
    arithmeticExpressions: ArithmeticExpression[];
    logicalExpressions: LogicalExpression[];
    constructor(logicType: string, expressions: ArithmeticExpression[], logics: LogicalExpression[]);
}
export declare class QueryV2 {
    objectApiName: string;
    _limit: number;
    isSetLimit: boolean;
    _offset: number;
    fields: string[];
    _order: OrderV2[];
    filter: LogicalExpression;
    buildCriterion(filter: LogicalExpression): any[];
    where(condition: LogicalExpression | Record<string, ArithmeticExpression>): QueryV2;
    offset(offset: number): QueryV2;
    limit(limit: number): QueryV2;
    orderBy(fieldApiNames: string[]): QueryV2;
    orderByDesc(fieldApiNames: string[]): QueryV2;
    select(fieldApiNames: string[]): QueryV2;
    constructor(objectApiName: string);
}
export type logicalRet = {
    logicalExps: LogicalExpression[];
    arithmeticExps: ArithmeticExpression[];
};
export declare function logical(exps: (LogicalExpression | Record<string, ArithmeticExpression>)[]): logicalRet;
export type CriterionV2 = (Record<string, CriterionV2> | ExpressionV2)[];
export declare function buildCriterionV2(filter: LogicalExpression): CriterionV2;
