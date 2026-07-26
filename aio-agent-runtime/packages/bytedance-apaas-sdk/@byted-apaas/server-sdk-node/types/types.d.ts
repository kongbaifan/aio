export type _BooleanCond<T> = {};
export type _LogicalCond<T> = {};
type _LookupCond = number | {
    _id: number;
};
type _MultiLookupCond = _LookupCond[];
type PartialCompositeType<T> = Partial<{
    [K in keyof T]: T[K] extends _LookupField[] ? _MultiLookupCond : T[K] extends _LookupField ? _LookupCond : Partial<T[K]>;
}>;
type _FieldCond<T> = T extends _LookupField[] ? _MultiLookupCond : T extends _LookupField ? _LookupCond : PartialCompositeType<T>;
type _FirstLevelFieldCond<T> = Partial<{
    [K in keyof T]: T[K] extends _LookupField ? _FieldCond<T[K]> : T[K];
}>;
type _KCond<T> = Partial<{
    [K in keyof T]: _FieldCond<T[K]> | _BooleanCond<T[K]> | _LogicalCond<T[K]>;
}>;
type _WhereKCond<T> = Partial<{
    [K in keyof T]: _FirstLevelFieldCond<T[K]> | _BooleanCond<T[K]> | _LogicalCond<T[K]>;
}>;
export type _Cond<T> = _KCond<T> | _LogicalCond<Partial<T>>;
export type _WhereCond<T> = _WhereKCond<T> | _LogicalCond<Partial<T>>;
export type _Record<T> = {
    [K in keyof T]: T[K] extends _LookupField ? _LookupFieldRet : T[K];
};
export type _CondRequireID<T> = _Cond<T> & {
    _id: number | string;
};
interface _LookupFieldRet {
    /**
     * 名称：_id
     *
     * 类型：数字 / Number
     *
     * 格式：number
     */
    _id: number;
    /**
     * 名称：角色名 / _name
     *
     * 类型：文本 / Text | 多语 / Multilingual
     *
     * 格式：string | {language_code: 1033|2052, text: string}[]
     */
    _name: string | {
        language_code: 1033 | 2052;
        text: string;
    }[];
    is_deleted: boolean;
}
interface _LookupField {
    _id: number;
}
import { metadataMap, currentObjApiName } from '../data/index';
/**
 * target record 被使用于 workflow 场景下
 */
export interface TargetRecord {
    /**
     * workflow 被触发时，原始的记录信息
     */
    original: metadataMap[currentObjApiName];
    /**
     * workflow 运行到当前位置的记录信息
     */
    proposed: metadataMap[currentObjApiName];
}
export interface TriggerOld {
    /**
     * 更新前的记录数据
     */
    old: metadataMap[currentObjApiName];
}
export interface TriggerNew {
    /**
     * 创建或更新后的记录数据
     */
    new: metadataMap[currentObjApiName];
}
export {};
