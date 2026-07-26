"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Condition = void 0;
const operator_1 = require("./operator");
class Condition {
    toJSON() {
        return this.value;
    }
    toBSON() {
        return this.value;
    }
    mod(data) {
        this.addCondition(operator_1.Operator.MOD, data);
        return this;
    }
    eq(data) {
        this.addCondition(operator_1.Operator.EQ, data);
        return this;
    }
    ne(data) {
        this.addCondition(operator_1.Operator.NE, data);
        return this;
    }
    gt(data) {
        this.addCondition(operator_1.Operator.GT, data);
        return this;
    }
    gte(data) {
        this.addCondition(operator_1.Operator.GTE, data);
        return this;
    }
    lt(data) {
        this.addCondition(operator_1.Operator.LT, data);
        return this;
    }
    lte(data) {
        this.addCondition(operator_1.Operator.LTE, data);
        return this;
    }
    in(data) {
        this.addCondition(operator_1.Operator.IN, data);
        return this;
    }
    nin(data) {
        this.addCondition(operator_1.Operator.NIN, data);
        return this;
    }
    not(data) {
        this.addCondition(operator_1.Operator.NOT, data);
        return this;
    }
    exists(data) {
        this.addCondition(operator_1.Operator.EXISTS, data);
        return this;
    }
    regex(data) {
        this.addCondition(operator_1.Operator.REGEX, data);
        return this;
    }
    all(data) {
        this.addCondition(operator_1.Operator.ALL, data);
        return this;
    }
    elemMatch(data) {
        this.addCondition(operator_1.Operator.ELEM_MATCH, data);
        return this;
    }
    size(data) {
        this.addCondition(operator_1.Operator.SIZE, data);
        return this;
    }
    bitsAllClear(data) {
        this.addCondition(operator_1.Operator.BITS_ALL_CLEAR, data);
        return this;
    }
    bitsAllSet(data) {
        this.addCondition(operator_1.Operator.BITS_ALL_SET, data);
        return this;
    }
    bitsAnyClear(data) {
        this.addCondition(operator_1.Operator.BITS_ANY_CLEAR, data);
        return this;
    }
    bitsAnySet(data) {
        this.addCondition(operator_1.Operator.BITS_ANY_SET, data);
        return this;
    }
    geoIntersects(data) {
        this.addCondition(operator_1.Operator.GEO_INTERSECTS, data);
        return this;
    }
    geoWithin(data) {
        this.addCondition(operator_1.Operator.GEO_WITHIN, data);
        return this;
    }
    near(data) {
        this.addCondition(operator_1.Operator.NEAR, data);
        return this;
    }
    nearSphere(data) {
        this.addCondition(operator_1.Operator.NEAR_SPHERE, data);
        return this;
    }
    literal(data) {
        this.addCondition(operator_1.Operator.LITERAL, data);
        return this;
    }
    abs(data) {
        this.addCondition(operator_1.Operator.ABS, data);
        return this;
    }
    add(data) {
        this.addCondition(operator_1.Operator.ADD, data);
        return this;
    }
    ceil(data) {
        this.addCondition(operator_1.Operator.CEIL, data);
        return this;
    }
    divide(data) {
        this.addCondition(operator_1.Operator.DIVIDE, data);
        return this;
    }
    exp(data) {
        this.addCondition(operator_1.Operator.EXP, data);
        return this;
    }
    floor(data) {
        this.addCondition(operator_1.Operator.FLOOR, data);
        return this;
    }
    ln(data) {
        this.addCondition(operator_1.Operator.LN, data);
        return this;
    }
    log(data) {
        this.addCondition(operator_1.Operator.LOG, data);
        return this;
    }
    log10(data) {
        this.addCondition(operator_1.Operator.LOG10, data);
        return this;
    }
    multiply(data) {
        this.addCondition(operator_1.Operator.MULTIPLY, data);
        return this;
    }
    pow(data) {
        this.addCondition(operator_1.Operator.POW, data);
        return this;
    }
    round(data) {
        this.addCondition(operator_1.Operator.ROUND, data);
        return this;
    }
    sqrt(data) {
        this.addCondition(operator_1.Operator.SQRT, data);
        return this;
    }
    subtract(data) {
        this.addCondition(operator_1.Operator.SUBTRACT, data);
        return this;
    }
    trunc(data) {
        this.addCondition(operator_1.Operator.TRUNC, data);
        return this;
    }
    cmp(data) {
        this.addCondition(operator_1.Operator.CMP, data);
        return this;
    }
    cond(data) {
        this.addCondition(operator_1.Operator.COND, data);
        return this;
    }
    ifNull(data) {
        this.addCondition(operator_1.Operator.IF_NULL, data);
        return this;
    }
    switch(data) {
        this.addCondition(operator_1.Operator.SWITCH, data);
        return this;
    }
    dayOfMonth(data) {
        this.addCondition(operator_1.Operator.DAY_OF_MONTH, data);
        return this;
    }
    dayOfWeek(data) {
        this.addCondition(operator_1.Operator.DAY_OF_WEEK, data);
        return this;
    }
    dayOfYear(data) {
        this.addCondition(operator_1.Operator.DAY_OF_YEAR, data);
        return this;
    }
    hour(data) {
        this.addCondition(operator_1.Operator.HOUR, data);
        return this;
    }
    millisecond(data) {
        this.addCondition(operator_1.Operator.MILLISECOND, data);
        return this;
    }
    minute(data) {
        this.addCondition(operator_1.Operator.MINUTE, data);
        return this;
    }
    month(data) {
        this.addCondition(operator_1.Operator.MONTH, data);
        return this;
    }
    second(data) {
        this.addCondition(operator_1.Operator.SECOND, data);
        return this;
    }
    week(data) {
        this.addCondition(operator_1.Operator.WEEK, data);
        return this;
    }
    year(data) {
        this.addCondition(operator_1.Operator.YEAR, data);
        return this;
    }
    concat(data) {
        this.addCondition(operator_1.Operator.CONCAT, data);
        return this;
    }
    dateFromString(data) {
        this.addCondition(operator_1.Operator.DATE_FROM_STRING, data);
        return this;
    }
    dateToString(data) {
        this.addCondition(operator_1.Operator.DATE_TO_STRING, data);
        return this;
    }
    indexOfBytes(data) {
        this.addCondition(operator_1.Operator.INDEX_OF_BYTES, data);
        return this;
    }
    indexOfCP(data) {
        this.addCondition(operator_1.Operator.INDEX_OF_CP, data);
        return this;
    }
    ltrim(data) {
        this.addCondition(operator_1.Operator.LTRIM, data);
        return this;
    }
    rtrim(data) {
        this.addCondition(operator_1.Operator.RTRIM, data);
        return this;
    }
    split(data) {
        this.addCondition(operator_1.Operator.SPLIT, data);
        return this;
    }
    strLenBytes(data) {
        this.addCondition(operator_1.Operator.STR_LEN_BYTES, data);
        return this;
    }
    strLenCP(data) {
        this.addCondition(operator_1.Operator.STR_LEN_CP, data);
        return this;
    }
    strcasecmp(data) {
        this.addCondition(operator_1.Operator.STRCASECMP, data);
        return this;
    }
    substrBytes(data) {
        this.addCondition(operator_1.Operator.SUBSTR_BYTES, data);
        return this;
    }
    substrCP(data) {
        this.addCondition(operator_1.Operator.SUBSTR_CP, data);
        return this;
    }
    toLower(data) {
        this.addCondition(operator_1.Operator.TO_LOWER, data);
        return this;
    }
    toString(data) {
        this.addCondition(operator_1.Operator.TO_STRING, data);
        return this;
    }
    toUpper(data) {
        this.addCondition(operator_1.Operator.TO_UPPER, data);
        return this;
    }
    trim(data) {
        this.addCondition(operator_1.Operator.TRIM, data);
        return this;
    }
    handleCondition(condition) {
        if (condition instanceof Condition) {
            return condition.toJSON();
        }
        return condition;
    }
    logic(op, ...conditions) {
        if (conditions.length === 0) {
            return;
        }
        if (this.value !== undefined) {
            conditions = [this.value, ...conditions];
        }
        if (conditions.length === 0) {
            return;
        }
        else if (conditions.length === 1) {
            this.value = conditions[0];
        }
        else if (conditions.length > 1) {
            this.value = {};
            this.value[op] = conditions;
        }
    }
    and(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.logic(operator_1.Operator.AND, ...conditions);
        return this;
    }
    or(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.logic(operator_1.Operator.OR, ...conditions);
        return this;
    }
    nor(...conditions) {
        if (conditions.length === 0) {
            return this;
        }
        for (let i = 0; i < conditions.length; i++) {
            conditions[i] = this.handleCondition(conditions[i]);
        }
        this.logic(operator_1.Operator.NOR, ...conditions);
        return this;
    }
    addCondition(op, data) {
        if (this.value === undefined) {
            this.value = {};
        }
        if (this.value[op] !== undefined) {
            let datas = [this.value, data];
            this.value = {};
            this.value[op] = datas;
        }
        else {
            this.value[op] = data;
        }
    }
}
exports.Condition = Condition;
