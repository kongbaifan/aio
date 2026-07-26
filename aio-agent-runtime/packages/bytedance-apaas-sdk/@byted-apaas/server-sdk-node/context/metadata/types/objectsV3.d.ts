import { MultilingualTypeV3 } from './common';
import { CriterionType, SortConditionType } from './objects';
export interface BaseFieldTypeV3 {
    type: string;
    apiName: string;
    label: MultilingualTypeV3;
}
export interface KTextFieldTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    validationRegex: string;
    errorMsg: MultilingualTypeV3;
}
export interface RichTextTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    maxLength: number;
}
export interface KMultilingualTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
}
export interface NumberTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
}
export interface KDateTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
}
export interface DateTimeTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
}
export interface SubOptionTypeV3 {
    label: MultilingualTypeV3;
    apiName: string;
    description: MultilingualTypeV3;
    color: ('grey' | 'blue' | 'cyan' | 'green' | 'yellow' | 'orange' | 'red' | 'magenta' | 'purple' | 'blueMagenta');
    active: boolean;
}
export interface OptionTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    multiple: boolean;
    optionSource: ('custom' | 'global');
    globalOptionApiName: string;
    optionList: SubOptionTypeV3[];
}
export interface EmailV3 extends BaseFieldTypeV3 {
    required: boolean;
    unique: boolean;
}
export interface MobileNumberV3 extends BaseFieldTypeV3 {
    required: boolean;
    unique: boolean;
}
export interface BooleanV3 extends BaseFieldTypeV3 {
    descriptionWhenTrue: MultilingualTypeV3;
    descriptionWhenFalse: MultilingualTypeV3;
    defaultValue: boolean;
}
export interface AvatarOrLogoV3 extends BaseFieldTypeV3 {
    displayStyle: ('square' | 'round');
}
export type FilterTypeV3 = {
    label: string;
    needTriggerCriterion: boolean;
    triggerCriterion: CriterionType;
    criterion: CriterionType;
    errorMsg: MultilingualTypeV3;
};
export interface RegionFilterTypeV3 {
    id: string;
    label: string;
    errorMessage: MultilingualTypeV3;
    recordFilter: CriterionType;
    precondition: object;
}
export interface LookupV3 extends BaseFieldTypeV3 {
    required: boolean;
    multiple: boolean;
    objectApiName: string;
    hierarchy: boolean;
    displayStyle: ('search' | 'dropDown' | 'tree');
    sortConditions: SortConditionType[];
    filter: FilterTypeV3[];
}
export interface FormulaTypeV3 extends BaseFieldTypeV3 {
    returnType: string;
    formula: MultilingualTypeV3;
}
export interface AutoIDTypeV3 extends BaseFieldTypeV3 {
    generateMethod: ('random' | 'incremental');
    digitsNumber: number;
    prefix: string;
    suffix: string;
}
export interface ReferenceFieldTypeV3 extends BaseFieldTypeV3 {
    guideFieldApiName: string;
    fieldApiName: string;
}
export interface FileTypeV3 extends BaseFieldTypeV3 {
    required: boolean;
    multiple: boolean;
    fileTypes: string[];
}
export interface BackLookuTypeV3 extends BaseFieldTypeV3 {
    objectApiName: string;
    fieldApiName: string;
}
export interface CompositeTypeV3 extends BaseFieldTypeV3 {
    compositeTypeApiName: string;
    subFields: BaseFieldTypeV3[];
    required: boolean;
    multiple: boolean;
}
export interface ExtractSingleRecordTypeV3 extends BaseFieldTypeV3 {
    compositeTypeApiName: string;
    subFields: BaseFieldTypeV3[];
    filter: FilterTypeV3[];
    sortConditions: SortConditionType[];
    recordPosition: number;
}
