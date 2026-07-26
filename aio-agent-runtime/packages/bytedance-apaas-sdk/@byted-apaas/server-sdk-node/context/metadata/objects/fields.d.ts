import { BaseFieldType, CriterionType, FieldType, FilterType, RegionFilterType, SortConditionType, SubOptionType } from '../types/objects';
import { I18ns } from '../types/common';
declare class MetadataField {
    type: string;
    apiName: string;
    label: I18ns;
    constructor(type: string, field: FieldType);
}
declare class KText extends MetadataField {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    validationRegex: string;
    errorMsg: I18ns;
    constructor(field: FieldType);
}
declare class RichText extends MetadataField {
    maxLength: number;
    required: boolean;
    constructor(field: FieldType);
}
declare class Multilingual extends MetadataField {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    constructor(field: FieldType);
}
declare class Number extends MetadataField {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
    constructor(field: FieldType);
}
declare class Bigint extends MetadataField {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class Decimal extends MetadataField {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
    constructor(field: FieldType);
}
declare class KDate extends MetadataField {
    required: boolean;
    constructor(field: FieldType);
}
declare class DateTime extends MetadataField {
    required: boolean;
    constructor(field: FieldType);
}
declare class Option extends MetadataField {
    required: boolean;
    multiple: boolean;
    optionSource: ('custom' | 'global');
    globalOptionApiName: string;
    optionList: SubOptionType[];
    constructor(field: FieldType);
}
declare class Email extends MetadataField {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class MobileNumber extends MetadataField {
    required: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class Boolean extends MetadataField {
    descriptionWhenTrue: I18ns;
    descriptionWhenFalse: I18ns;
    defaultValue: boolean;
    unique: boolean;
    constructor(field: FieldType);
}
declare class AvatarOrLogo extends MetadataField {
    displayStyle: ('square' | 'round');
    constructor(field: FieldType);
}
declare class Lookup extends MetadataField {
    required: boolean;
    multiple: boolean;
    objectApiName: string;
    hierarchy: boolean;
    displayStyle: ('search' | 'dropDown' | 'tree');
    sortConditions: SortConditionType[];
    filter: FilterType[];
    constructor(field: FieldType);
}
declare class Formula extends MetadataField {
    returnType: string;
    formula: I18ns;
    constructor(field: FieldType);
}
declare class AutoID extends MetadataField {
    generateMethod: ('random' | 'incremental');
    digitsNumber: number;
    prefix: string;
    suffix: string;
    constructor(field: FieldType);
}
declare class ReferenceField extends MetadataField {
    guideFieldApiName: string;
    fieldApiName: string;
    constructor(field: FieldType);
}
declare class Rollup extends MetadataField {
    rollupType: string;
    rollupObjectApiName: string;
    rollupFieldApiName: string;
    rollupLookupFieldApiName: string;
    filter: CriterionType;
    constructor(field: FieldType);
}
declare class Region extends MetadataField {
    required: boolean;
    multiple: boolean;
    optionLevel: boolean;
    strictLevel: number;
    filter: RegionFilterType[];
    constructor(field: FieldType);
}
declare class File extends MetadataField {
    required: boolean;
    multiple: boolean;
    fileTypes: string[];
    constructor(field: FieldType);
}
declare class BackLookup extends MetadataField {
    constructor(field: FieldType);
}
declare class CompositeType extends MetadataField {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    required: boolean;
    multiple: boolean;
    constructor(field: FieldType);
}
declare class ExtractSingleRecord extends MetadataField {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    filter: FilterType[];
    sortConditions: SortConditionType[];
    recordPosition: number;
    constructor(field: FieldType);
}
declare function parseFields(inputFields: Record<string, any>): BaseFieldType[];
declare function parseField(field: FieldType): BaseFieldType;
declare function getFieldClass(field: FieldType): any;
export { KText as Text, Multilingual, Number, KDate as Date, DateTime, Option, Email, MobileNumber, Boolean, AvatarOrLogo, Lookup, Formula, AutoID, ReferenceField, File, BackLookup, CompositeType, ExtractSingleRecord, RichText, Bigint, Decimal, Region, Rollup, parseFields, parseField, getFieldClass, };
