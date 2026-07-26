"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.MetadataExpressionFieldV3 = exports.ConstantExpressionFieldV3 = exports.ExpressionV3 = exports.MetadataExpressionField = exports.ConstantExpressionField = exports.Expression = void 0;
class Expression {
    constructor(left, operator, right, index) {
        this.index = index;
        this.left = left;
        this.operator = operator;
        this.right = right;
    }
}
exports.Expression = Expression;
/**
 * 总共有4种类型，当前仅支持constant，metadataVariable
 *
 * constant：不可为左值
 * metadataVariable
 * function
 * customizedVariable
 */
class ExpressionField {
    constructor(type, settings) {
        this.type = type;
        this.settings = settings;
    }
}
/**
 * 常量表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'bob' 将被构建为 ConstantExpressionField
 */
class ConstantExpressionField extends ExpressionField {
    constructor(data) {
        super('constant', { data });
    }
}
exports.ConstantExpressionField = ConstantExpressionField;
/**
 * 元数据表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'user.name' 将被构建为 MetadataExpressionField
 */
class MetadataExpressionField extends ExpressionField {
    constructor(objectApiName, fieldApiName) {
        super('metadataVariable', {
            'fieldPath': [{
                    objectApiName: objectApiName,
                    fieldApiName: fieldApiName,
                    extendLogicTags: [],
                }]
        });
    }
}
exports.MetadataExpressionField = MetadataExpressionField;
class ExpressionV3 {
    constructor(left, operator, right, index) {
        this.index = index;
        this.left = left;
        this.operator = operator;
        this.right = right;
    }
}
exports.ExpressionV3 = ExpressionV3;
class ExpressionFieldV3 {
    constructor(type, settings) {
        this.type = type;
        this.settings = settings;
    }
}
/**
 * 常量表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'bob' 将被构建为 ConstantExpressionField
 */
class ConstantExpressionFieldV3 extends ExpressionFieldV3 {
    constructor(data) {
        const d = { 'data': data };
        super('constant', JSON.stringify(d));
    }
}
exports.ConstantExpressionFieldV3 = ConstantExpressionFieldV3;
/**
 * 元数据表达式字段
 *
 * 比如在 condition: user.name equal 'bob' 中，'user.name' 将被构建为 MetadataExpressionField
 */
class MetadataExpressionFieldV3 extends ExpressionFieldV3 {
    constructor(filedPath) {
        const filedPathV3 = filedPath.map(({ extendLogicTags, ...item }) => item);
        const fp = { 'fieldPath': filedPathV3 };
        super('metadataVariable', JSON.stringify(fp));
    }
}
exports.MetadataExpressionFieldV3 = MetadataExpressionFieldV3;
