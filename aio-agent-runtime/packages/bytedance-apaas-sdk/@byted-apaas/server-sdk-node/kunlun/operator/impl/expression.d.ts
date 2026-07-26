export type UserDataType = null | string | boolean | number | Date | object;
export declare class Expression {
    index: number;
    left: ExpressionField;
    operator: string;
    right: ExpressionField;
    constructor(left: ExpressionField, operator: string, right: ExpressionField, index: number);
}
type SettingType = {
    data?: UserDataType;
    fieldPath?: PathType[];
};
export type PathType = {
    objectApiName: string;
    fieldApiName: string;
    extendLogicTags: string[];
};
/**
 * 总共有4种类型，当前仅支持constant，metadataVariable
 *
 * constant：不可为左值
 * metadataVariable
 * function
 * customizedVariable
 */
declare class ExpressionField {
    type: string;
    settings: SettingType;
    constructor(type: string, settings: SettingType);
}
/**
 * 常量表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'bob' 将被构建为 ConstantExpressionField
 */
export declare class ConstantExpressionField extends ExpressionField {
    constructor(data: UserDataType);
}
/**
 * 元数据表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'user.name' 将被构建为 MetadataExpressionField
 */
export declare class MetadataExpressionField extends ExpressionField {
    constructor(objectApiName: string, fieldApiName: string);
}
export declare class ExpressionV3 {
    index: number;
    left: ExpressionFieldV3;
    operator: string;
    right: ExpressionFieldV3;
    constructor(left: ExpressionFieldV3, operator: string, right: ExpressionFieldV3, index: number);
}
declare class ExpressionFieldV3 {
    type: string;
    settings: string;
    constructor(type: string, settings: string);
}
/**
 * 常量表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'bob' 将被构建为 ConstantExpressionField
 */
export declare class ConstantExpressionFieldV3 extends ExpressionFieldV3 {
    constructor(data?: UserDataType);
}
/**
 * 元数据表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'user.name' 将被构建为 MetadataExpressionField
 */
export declare class MetadataExpressionFieldV3 extends ExpressionFieldV3 {
    constructor(filedPath?: PathType[]);
}
export {};
