import { GMTOffset } from '../../constants/timeZone';
export declare interface _LangType {
    zh?: string;
    en?: string;
}
export type _LanguageType = {
    language_code: number;
    text: string;
};
export declare class KunlunFieldType {
    baseType: string;
    type: string;
    constructor(type: string);
    toString(): string;
    toJSON(): any;
    checkVariables(variables: any, key: string): void;
}
export declare class Text extends KunlunFieldType {
    value: string;
    constructor(param: string);
    toJSON(): string;
}
export declare class Number extends KunlunFieldType {
    value: number;
    constructor(param: number);
    toJSON(): number;
}
export declare class Boolean extends KunlunFieldType {
    value: boolean;
    constructor(param: boolean);
    toJSON(): boolean;
}
export declare class Email extends KunlunFieldType {
    value: string;
    constructor(param: string);
    toJSON(): string;
}
/**
 * 多语文本类
 * 构造方法：
 * ```
 * constructor(valueMap)
 * ```
 */
export declare class Multilingual extends KunlunFieldType {
    value: _LangType;
    valueList: _LanguageType[];
    /**
     * 生成多语文本
     * @param valueMap ISO3166-1 二位字母代码的赋值对象
     * @paramExample {zh: '你好', en: 'hello'}
     * @example
     * ```
     * new kunlun.type.Multilingual({
     *     zh: '你好',
     *     en: 'hello'
     * })
     * ```
     */
    constructor(valueMap: _LangType);
    toJSON(): _LanguageType[];
    toString(): string;
}
/**
 * 电话类
 * 构造方法：
 * ```
 * constructor(phoneNumber)
 * constructor(phoneNumber, countryCode)
 * ```
 */
export declare class Phone extends KunlunFieldType {
    key: string;
    number: string;
    /**
     * 生成电话
     * @param phoneNumber 文本格式电话号码，默认区号是'+86'
     * @example
     * ```
     * new kunlun.type.Phone('13800000000')
     * ```
     */
    constructor(phoneNumber: string);
    /**
     * 生成电话
     * @param phoneNumber 文本格式电话号码
     * @param countryCode 文本格式国家区号，默认为 '+86'
     * @example
     * ```
     * new kunlun.type.Phone('13800000000', '+86')
     * ```
     */
    constructor(phoneNumber: string, countryCode: string);
    toJSON(): object;
}
/**
 * 日期类：
 * 构造方法
 * ```
 * constructor(stringDate)
 * constructor(year, month, day)
 * ```
 */
declare class KDate extends KunlunFieldType {
    value: string;
    /**
     * 生成日期
     * @param stringDate 文本格式日期
     * @paramExample '2020-01-01'
     * @example
     * ```
     * new kunlun.type.Date('2020-01-01')
     * ```
     */
    constructor(stringDate: string);
    /**
     * 生成日期
     * @param year 年份
     * @param month 月份 1-12
     * @param day 日期 1-31
     * @example
     * ```
     * new kunlun.type.Date(2020, 1, 1)
     * ```
     */
    constructor(year: number, month: number, day: number);
    toJSON(): string;
}
export { KDate as Date, };
/**
 * 日期时间类
 * 构造方法：
 * ```
 * constructor()
 * constructor(stringDateTime)
 * constructor(year, month, day, hour, min, sec)
 * constructor(year, month, day, hour, min, sec, GMTOffset)
 * ```
 */
export declare class DateTime extends KunlunFieldType {
    value: number;
    /**
     * 生成现在的日期时间
     * @example
     * ```
     * new kunlun.type.DateTime()
     * ```
     */
    constructor();
    /**
     * 生成日期时间
     * @param stringDateTime 时间戳格式
     * @paramExample '2020-01-01 20:00:00 GMT+08'
     * @example
     * ```
     * new kunlun.type.DateTime('2020-01-01 20:00:00 GMT+08')
     * ```
     */
    constructor(stringDateTime: string);
    /**
     * 生成日期时间
     * @param year 年份
     * @param month 月份 1-12
     * @param day 日期 1-31
     * @param hour 小时 0-23
     * @param min 分钟 0-59
     * @param sec 秒 0-59
     * @example
     * ```
     * new kunlun.type.DateTime(2020, 1, 1, 20, 0, 0)
     * ```
     */
    constructor(year: number, month: number, day: number, hour: number, min: number, sec: number);
    /**
     * 生成日期时间
     * @param year 年份
     * @param month 月份 1-12
     * @param day 日期 1-31
     * @param hour 小时 0-23
     * @param min 分钟 0-59
     * @param sec 秒 0-59
     * @param GMTOffset GMT 偏移量，默认为 GMT+8 （东八区）
     * @example
     * ```
     * new kunlun.type.DateTime(2020, 1, 1, 20, 0, 0, kunlun.GMTOffset.GMT08)
     * ```
     */
    constructor(year: number, month: number, day: number, hour: number, min: number, sec: number, GMTOffset: GMTOffset);
    toJSON(): number;
}
export declare const type2fieldType: Record<string, any>;
export declare function isKunlunType(input: any): boolean;
/**
 * type2fieldType isKunlunType
 * 之前在 kunlun 下有，无智能提示
 */
export declare function isKFieldType(value: any): boolean;
export declare function isKFieldTypeMultilingual(value: any): boolean;
export declare function isKFieldTypeDate(value: any): boolean;
