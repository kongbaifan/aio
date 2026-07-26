"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildCriterionV2 = exports.logical = exports.QueryV2 = exports.LogicalExpression = exports.ArithmeticExpression = exports.NewConstantExpressionField = exports.NewMetadataExpressionField = void 0;
const operator_1 = require("./operator");
function NewMetadataExpressionField(objectApiName, fieldApiName) {
    return {
        type: 'metadataVariable',
        settings: {
            fieldPath: [{
                    objectApiName: objectApiName,
                    fieldApiName: fieldApiName,
                    extendLogicTags: []
                }]
        }
    };
}
exports.NewMetadataExpressionField = NewMetadataExpressionField;
function NewConstantExpressionField(data) {
    return {
        type: 'constant',
        settings: {
            data: data
        }
    };
}
exports.NewConstantExpressionField = NewConstantExpressionField;
class ArithmeticExpression {
    constructor(leftValue, op, rightValue) {
        let fieldPaths = [];
        leftValue.split('.').forEach((fieldApiName) => {
            fieldPaths.push({
                fieldApiName: fieldApiName,
                objectApiName: '',
                extendLogicTags: []
            });
        });
        const left = {
            type: 'metadataVariable',
            settings: {
                fieldPath: fieldPaths,
                data: null
            }
        };
        let right = {
            type: 'constant',
            settings: {
                fieldPath: [],
                data: rightValue
            }
        };
        if (op === 'isEmpty' || op === 'isNotEmpty') {
            right = null;
        }
        this.operator = op;
        this.left = left;
        this.right = right;
        this.expr = {
            leftValue: leftValue,
            operator: op,
            rightValue: rightValue
        };
    }
}
exports.ArithmeticExpression = ArithmeticExpression;
class LogicalExpression {
    constructor(logicType, expressions, logics) {
        this.type = logicType;
        this.arithmeticExpressions = expressions;
        this.logicalExpressions = logics;
    }
}
exports.LogicalExpression = LogicalExpression;
class QueryV2 {
    buildCriterion(filter) {
        if (!filter || filter.arithmeticExpressions.length == 0 && filter.logicalExpressions.length == 0) {
            return null;
        }
        var conditions = [];
        filter.logicalExpressions.forEach((logicalExpression) => {
            conditions.push({
                [logicalExpression.type]: this.buildCriterion(logicalExpression),
            });
        });
        filter.arithmeticExpressions.forEach((arithmeticExpression) => {
            conditions.push(arithmeticExpression.expr);
        });
        return conditions;
    }
    where(condition) {
        if (!condition) {
            return this;
        }
        const { logicalExps, arithmeticExps } = logical([condition]);
        logicalExps.forEach((logicalExpression) => {
            if (this.filter) {
                this.filter.logicalExpressions.push(logicalExpression);
            }
        });
        const logicalExpBuiltByArithmeticExps = new LogicalExpression(operator_1.operates.AND, arithmeticExps, []);
        this.filter.logicalExpressions.push(logicalExpBuiltByArithmeticExps);
        return this;
    }
    offset(offset) {
        if (offset < 0) {
            throw new Error('offset must be greater than or equal to 0');
        }
        this._offset = offset;
        return this;
    }
    limit(limit) {
        this._limit = limit;
        this.isSetLimit = true;
        return this;
    }
    orderBy(fieldApiNames) {
        fieldApiNames.forEach((fieldApiName) => {
            this._order.push({
                field: fieldApiName,
                direction: 'asc',
                type: '',
            });
        });
        return this;
    }
    orderByDesc(fieldApiNames) {
        fieldApiNames.forEach((fieldApiName) => {
            this._order.push({
                field: fieldApiName,
                direction: 'desc',
                type: '',
            });
        });
        return this;
    }
    select(fieldApiNames) {
        fieldApiNames.forEach((fieldApiName) => {
            this.fields.push(fieldApiName);
        });
        return this;
    }
    constructor(objectApiName) {
        this.objectApiName = objectApiName;
        this._limit = 200;
        this._offset = 0;
        this.fields = [];
        this._order = [];
        this.filter = {
            type: 'and',
            arithmeticExpressions: [],
            logicalExpressions: [],
        };
    }
}
exports.QueryV2 = QueryV2;
function logical(exps) {
    if (!exps || exps.length == 0) {
        return null;
    }
    var logicalExps = [];
    var arithmeticExps = [];
    exps.forEach((exp) => {
        if (!exp) {
            return;
        }
        if (exp instanceof LogicalExpression) {
            logicalExps.push(exp);
        }
        else {
            for (var key in exp) {
                if (exp[key]) {
                    arithmeticExps.push(new ArithmeticExpression(key, exp[key].operator, exp[key].right));
                }
            }
        }
    });
    return {
        logicalExps: logicalExps,
        arithmeticExps: arithmeticExps,
    };
}
exports.logical = logical;
function buildCriterionV2(filter) {
    if (!filter || filter.logicalExpressions.length == 0 && filter.arithmeticExpressions.length == 0) {
        return null;
    }
    var conditions = [];
    filter.logicalExpressions.forEach((logicalExp) => {
        conditions.push({
            [logicalExp.type]: buildCriterionV2(logicalExp),
        });
    });
    filter.arithmeticExpressions.forEach((arithmeticExp) => {
        conditions.push(arithmeticExp.expr);
    });
    return conditions;
}
exports.buildCriterionV2 = buildCriterionV2;
