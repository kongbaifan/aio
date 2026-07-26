"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Operator = exports.operates = void 0;
const server_common_node_1 = require("@byted-apaas/server-common-node");
const logic_1 = require("./logic");
exports.operates = {
    AND: 'and',
    OR: 'or',
    EMTPY: 'isEmpty',
    NOT_EMTPY: 'isNotEmpty',
    EQ: 'equals',
    NEQ: 'notEquals',
    LT: 'lessThan',
    LTE: 'lessThanOrEquals',
    GT: 'greaterThan',
    GTE: 'greaterThanOrEquals',
    CONTAIN: 'contains',
    NOT_CONTAIN: 'notContains',
    IN: 'isAnyOf',
    NIN: 'isNoneOf',
    HAS_ANY_OF: 'hasAnyOf',
    HAS_NONE_OF: 'hasNoneOf',
    isOnOrBefore: 'isOnOrBefore',
    isOnOrAfter: 'isOnOrAfter',
};
class Operator {
    /**
     * 逻辑且
     * @param conditions 多个条件，用逗号分隔
     * @example
     * ```
     * context.db.object('_user').where(kunlun.operator.and({
     *     age: '22'
     * },{
     *     gender: 'male'
     * }))
     * ```
     */
    and(...conditions) {
        if (conditions.length < 1) {
            return null;
        }
        return (0, logic_1.buildLogic)(conditions, exports.operates.AND);
    }
    ;
    /**
     * 逻辑或
     * @param conditions 多个条件，用逗号分隔
     * @example
     * ```
     * context.db.object('_user').where(kunlun.operator.or({
     *     age: '22'
     * },{
     *     age: '25'
     * }))
     * ```
     */
    or(...conditions) {
        if (conditions.length < 1) {
            return null;
        }
        return (0, logic_1.buildLogic)(conditions, exports.operates.OR);
    }
    ;
    /**
     * 包含
     * @param value 判定是否包含的文本值
     * @example
     * ```
     * context.db.object('_user').where({_name: kunlun.operator.contain('a')})
     * ```
     */
    contain(value) {
        return new logic_1.Condition(null, value, exports.operates.CONTAIN);
    }
    ;
    /**
     * 不包含
     * @param value 判定是否不包含的文本值
     * @example
     * ```
     * context.db.object('_user').where({_name: kunlun.operator.notContain('a')})
     * ```
     */
    notContain(value) {
        return new logic_1.Condition(null, value, exports.operates.NOT_CONTAIN);
    }
    ;
    /**
     * 无需入参，判断是否为空
     * @example
     * ```
     * context.db.object('_user').where({employeeType: kunlun.operator.empty()})
     * ```
     */
    empty() {
        return new logic_1.Condition(null, null, exports.operates.EMTPY);
    }
    ;
    /**
     * 无需入参，判断是否为空
     * @example
     * ```
     * context.db.object('_user').where({employeeType: kunlun.operator.notEmpty()})
     * ```
     */
    notEmpty() {
        return new logic_1.Condition(null, null, exports.operates.NOT_EMTPY);
    }
    ;
    /**
     * 等于
     * @param value 判定是否相等的值
     * @example
     * ```
     * context.db.object('_user').where({age: kunlun.operator.eq(20)})
     * ```
     */
    eq(value) {
        return new logic_1.Condition(null, value, exports.operates.EQ);
    }
    ;
    /**
     * 不等于
     * @param value 判定是否不相等的值
     * @example
     * ```
     * context.db.object('_user').where({age: kunlun.operator.neq(20)})
     * ```
     */
    neq(value) {
        return new logic_1.Condition(null, value, exports.operates.NEQ);
    }
    ;
    /**
     * 大于或晚于
     * @param value 判定是否大于或晚于的值
     * @example
     * ```
     * kunlun.operator.gt(new Date('2020-11-26').getTime())
     * ```
     */
    gt(value) {
        return new logic_1.Condition(null, value, exports.operates.GT);
    }
    ;
    /**
     * 大于等于或晚于等于
     * @param value 判定是否大于等于或晚于等于的值
     * @example
     * ```
     * kunlun.operator.gte(new Date('2020-11-26').getTime())
     * ```
     */
    gte(value) {
        return new logic_1.Condition(null, value, exports.operates.GTE);
    }
    ;
    /**
     * 小于或早于
     * @param value 判定是否小于或早于的值
     * @example
     * ```
     * kunlun.operator.lt(new Date('2020-11-26').getTime())
     * ```
     */
    lt(value) {
        return new logic_1.Condition(null, value, exports.operates.LT);
    }
    ;
    /**
     * 小于等于或早于等于
     * @param value 判定是否小于等于或早于等于的值
     * @example
     * ```
     * kunlun.operator.lte(new Date('2020-11-26').getTime())
     * ```
     */
    lte(value) {
        return new logic_1.Condition(null, value, exports.operates.LTE);
    }
    ;
    in(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not IN empty list');
        }
        return new logic_1.Condition(null, argList, exports.operates.IN);
    }
    ;
    notIn(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not NOT_IN empty list');
        }
        return new logic_1.Condition(null, argList, exports.operates.NIN);
    }
    ;
    hasAnyOf(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not HAS_ANY_OF empty list');
        }
        return new logic_1.Condition(null, argList, exports.operates.HAS_ANY_OF);
    }
    ;
    hasNoneOf(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not HAS_NONE_OF empty list');
        }
        return new logic_1.Condition(null, argList, exports.operates.HAS_NONE_OF);
    }
    ;
}
exports.Operator = Operator;
