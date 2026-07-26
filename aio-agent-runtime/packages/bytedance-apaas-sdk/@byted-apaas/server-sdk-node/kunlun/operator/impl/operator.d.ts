import { _Cond, _BooleanCond, _LogicalCond } from '../../../types/types';
import { IOperator } from '../IOperator';
import { UserDataType } from './expression';
export declare const operates: {
    AND: string;
    OR: string;
    EMTPY: string;
    NOT_EMTPY: string;
    EQ: string;
    NEQ: string;
    LT: string;
    LTE: string;
    GT: string;
    GTE: string;
    CONTAIN: string;
    NOT_CONTAIN: string;
    IN: string;
    NIN: string;
    HAS_ANY_OF: string;
    HAS_NONE_OF: string;
    isOnOrBefore: string;
    isOnOrAfter: string;
};
export declare class Operator<T> implements IOperator {
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
    and<T>(...conditions: (_Cond<T> | _BooleanCond<T>)[]): _LogicalCond<T>;
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
    or<T>(...conditions: (_Cond<T> | _BooleanCond<T>)[]): _LogicalCond<T>;
    /**
     * 包含
     * @param value 判定是否包含的文本值
     * @example
     * ```
     * context.db.object('_user').where({_name: kunlun.operator.contain('a')})
     * ```
     */
    contain<T>(value: UserDataType): _BooleanCond<T>;
    /**
     * 不包含
     * @param value 判定是否不包含的文本值
     * @example
     * ```
     * context.db.object('_user').where({_name: kunlun.operator.notContain('a')})
     * ```
     */
    notContain<T>(value: UserDataType): _BooleanCond<T>;
    /**
     * 无需入参，判断是否为空
     * @example
     * ```
     * context.db.object('_user').where({employeeType: kunlun.operator.empty()})
     * ```
     */
    empty(): _BooleanCond<undefined>;
    /**
     * 无需入参，判断是否为空
     * @example
     * ```
     * context.db.object('_user').where({employeeType: kunlun.operator.notEmpty()})
     * ```
     */
    notEmpty(): _BooleanCond<undefined>;
    /**
     * 等于
     * @param value 判定是否相等的值
     * @example
     * ```
     * context.db.object('_user').where({age: kunlun.operator.eq(20)})
     * ```
     */
    eq<T>(value: UserDataType): _BooleanCond<T>;
    /**
     * 不等于
     * @param value 判定是否不相等的值
     * @example
     * ```
     * context.db.object('_user').where({age: kunlun.operator.neq(20)})
     * ```
     */
    neq<T>(value: UserDataType): _BooleanCond<T>;
    /**
     * 大于或晚于
     * @param value 判定是否大于或晚于的值
     * @example
     * ```
     * kunlun.operator.gt(new Date('2020-11-26').getTime())
     * ```
     */
    gt<T>(value: number | Date): _BooleanCond<T>;
    /**
     * 大于等于或晚于等于
     * @param value 判定是否大于等于或晚于等于的值
     * @example
     * ```
     * kunlun.operator.gte(new Date('2020-11-26').getTime())
     * ```
     */
    gte<T>(value: number | Date): _BooleanCond<T>;
    /**
     * 小于或早于
     * @param value 判定是否小于或早于的值
     * @example
     * ```
     * kunlun.operator.lt(new Date('2020-11-26').getTime())
     * ```
     */
    lt<T>(value: number | Date): _BooleanCond<T>;
    /**
     * 小于等于或早于等于
     * @param value 判定是否小于等于或早于等于的值
     * @example
     * ```
     * kunlun.operator.lte(new Date('2020-11-26').getTime())
     * ```
     */
    lte<T>(value: number | Date): _BooleanCond<T>;
    /**
     * 存在于给定的数组内
     * @param values 判定是否存在于的一组值，用数组传递
     */
    in<T>(values: T[]): _BooleanCond<T>;
    /**
     * 存在于给定的数组内
     * @param values 判定是否存在于的一组值，用逗号分隔
     */
    in<T>(...values: T[]): _BooleanCond<T>;
    /**
     * 不存在于给定的数组内
     * @param values 判定是否不存在于的一组值，用数组传递
     */
    notIn<T>(values: T[]): _BooleanCond<T>;
    /**
     * 不存在于给定的数组内
     * @param values 判定是否不存在于的一组值，用逗号分隔
     */
    notIn<T>(...values: T[]): _BooleanCond<T>;
    /**
     * 存在给定的多个值中的任何一个值
     * @param values 判定是否不存在于的一组值，用逗号分隔
     */
    hasAnyOf<T>(values: number[] | string[]): _BooleanCond<T>;
    /**
     * 存在给定的多个值中的任何一个值
     * @param values 判定是否不存在于的一组值，用逗号分隔
     */
    hasAnyOf<T>(...values: (number | string)[]): _BooleanCond<T>;
    /**
     * 不存在给定的多个值中的任何值
     * @param values 判定是否不存在于的一组值，用逗号分隔
     */
    hasNoneOf<T>(values: number[] | string[]): _BooleanCond<T>;
    /**
     * 不存在给定的多个值中的任何值
     * @param values 判定是否不存在于的一组值，用逗号分隔
     */
    hasNoneOf<T>(...values: (number | string)[]): _BooleanCond<T>;
}
