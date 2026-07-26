import { BaseFieldType, CriterionType, FieldType, FilterType, SortConditionType } from '../types/objects';
import { MultilingualTypeV3 } from '../types/common';
import { FilterTypeV3, RegionFilterTypeV3, SubOptionTypeV3 } from '../types/objectsV3';
declare class MetadataFieldV3 {
    type: string;
    apiName: string;
    label: MultilingualTypeV3;
    constructor(type: string, field: FieldType);
}
declare class KTextV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    validationRegex: string;
    errorMsg: MultilingualTypeV3;
    constructor(field: FieldType);
}
declare class RichTextV3 extends MetadataFieldV3 {
    maxLength: number;
    required: boolean;
    constructor(field: FieldType);
}
declare class MultilingualV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    constructor(field: FieldType);
}
declare class NumberV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
    constructor(field: FieldType);
}
declare class BigintV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class DecimalV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
    constructor(field: FieldType);
}
declare class KDateV3 extends MetadataFieldV3 {
    required: boolean;
    constructor(field: FieldType);
}
declare class DateTimeV3 extends MetadataFieldV3 {
    required: boolean;
    constructor(field: FieldType);
}
declare class OptionV3 extends MetadataFieldV3 {
    required: boolean;
    multiple: boolean;
    optionSource: ('custom' | 'global');
    globalOptionApiName: string;
    optionList: SubOptionTypeV3[];
    constructor(field: FieldType);
}
declare class EmailV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class MobileNumberV3 extends MetadataFieldV3 {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class BooleanV3 extends MetadataFieldV3 {
    descriptionWhenTrue: MultilingualTypeV3;
    descriptionWhenFalse: MultilingualTypeV3;
    defaultValue: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class AvatarOrLogoV3 extends MetadataFieldV3 {
    displayStyle: ('square' | 'round');
    constructor(field: FieldType);
}
declare class LookupV3 extends MetadataFieldV3 {
    required: boolean;
    multiple: boolean;
    objectApiName: string;
    hierarchy: boolean;
    displayStyle: ('search' | 'dropDown' | 'tree');
    sortConditions: SortConditionType[];
    filter: FilterType[];
    constructor(field: FieldType);
}
declare class FormulaV3 extends MetadataFieldV3 {
    returnType: string;
    formula: MultilingualTypeV3;
    constructor(field: FieldType);
}
declare class AutoIDV3 extends MetadataFieldV3 {
    generateMethod: ('random' | 'incremental');
    digitsNumber: number;
    prefix: string;
    suffix: string;
    constructor(field: FieldType);
}
declare class ReferenceFieldV3 extends MetadataFieldV3 {
    guideFieldApiName: string;
    fieldApiName: string;
    constructor(field: FieldType);
}
declare class RollupV3 extends MetadataFieldV3 {
    rollupType: string;
    rollupObjectApiName: string;
    rollupFieldApiName: string;
    rollupLookupFieldApiName: string;
    filter: CriterionType;
    constructor(field: FieldType);
}
declare class RegionV3 extends MetadataFieldV3 {
    required: boolean;
    multiple: boolean;
    optionLevel: boolean;
    strictLevel: number;
    filter: RegionFilterTypeV3[];
    constructor(field: FieldType);
}
declare class FileV3 extends MetadataFieldV3 {
    required: boolean;
    multiple: boolean;
    fileTypes: string[];
    constructor(field: FieldType);
}
declare class BackLookupV3 extends MetadataFieldV3 {
    constructor(field: FieldType);
}
declare class CompositeTypeV3 extends MetadataFieldV3 {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    required: boolean;
    multiple: boolean;
    constructor(field: FieldType);
}
declare class ExtractSingleRecordV3 extends MetadataFieldV3 {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    filter: FilterTypeV3[];
    sortConditions: SortConditionType[];
    recordPosition: number;
    constructor(field: FieldType);
}
declare function parseFieldsV3(inputFields: Record<string, any>): BaseFieldType[];
declare function parseFieldV3(field: FieldType): BaseFieldType;
declare function getFieldClassV3(field: FieldType): any;
export { KTextV3 as TextV3, MultilingualV3, NumberV3, KDateV3 as DateV3, DateTimeV3, OptionV3, EmailV3, MobileNumberV3, BooleanV3, AvatarOrLogoV3, LookupV3, FormulaV3, AutoIDV3, ReferenceFieldV3, FileV3, BackLookupV3, CompositeTypeV3, ExtractSingleRecordV3, RichTextV3, BigintV3, DecimalV3, RegionV3, RollupV3, parseFieldsV3, parseFieldV3, getFieldClassV3, };
