"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.OperatorV2 = exports.operates = void 0;
const server_common_node_1 = require("@byted-apaas/server-common-node");
const logicV2_1 = require("./logicV2");
exports.operates = {
    AND: 'and',
    OR: 'or',
    EMPTY: 'isEmpty',
    NOT_EMPTY: 'isNotEmpty',
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
    isOnOrBefore: 'lt',
    isOnOrAfter: 'gt',
};
class OperatorV2 {
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
    and(...exps) {
        const { logicalExps, arithmeticExps } = (0, logicV2_1.logical)(exps);
        return new logicV2_1.LogicalExpression(exports.operates.AND, arithmeticExps, logicalExps);
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
    or(...exps) {
        const { logicalExps, arithmeticExps } = (0, logicV2_1.logical)(exps);
        return new logicV2_1.LogicalExpression(exports.operates.OR, arithmeticExps, logicalExps);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.CONTAIN, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.NOT_CONTAIN, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.EMPTY, null);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.NOT_EMPTY, null);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.EQ, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.NEQ, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.GT, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.GTE, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.LT, value);
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
        return new logicV2_1.ArithmeticExpression(null, exports.operates.LTE, value);
    }
    ;
    in(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not IN empty list');
        }
        return new logicV2_1.ArithmeticExpression(null, exports.operates.IN, argList);
    }
    ;
    notIn(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not NOT_IN empty list');
        }
        return new logicV2_1.ArithmeticExpression(null, exports.operates.NIN, argList);
    }
    ;
    hasAnyOf(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not HAS_ANY_OF empty list');
        }
        return new logicV2_1.ArithmeticExpression(null, exports.operates.HAS_ANY_OF, argList);
    }
    ;
    hasNoneOf(value, ...restValues) {
        value = !value ? [] : value;
        const argList = server_common_node_1.utils.argsToList(value, restValues);
        if (argList.length === 0) {
            throw new server_common_node_1.exceptions.InvalidParamError('can not HAS_NONE_OF empty list');
        }
        return new logicV2_1.ArithmeticExpression(null, exports.operates.HAS_NONE_OF, argList);
    }
    ;
}
exports.OperatorV2 = OperatorV2;
