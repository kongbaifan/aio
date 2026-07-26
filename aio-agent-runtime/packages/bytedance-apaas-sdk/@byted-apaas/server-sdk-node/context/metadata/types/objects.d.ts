import { I18ns } from './common';
export interface BaseFieldType {
    type: string;
    apiName: string;
    label: I18ns;
}
export interface KTextFieldType extends BaseFieldType {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
    validationRegex: string;
    errorMsg: I18ns;
}
export interface RichTextType extends BaseFieldType {
    required: boolean;
    maxLength: number;
}
export interface MultilingualType extends BaseFieldType {
    required: boolean;
    unique: boolean;
    caseSensitive: boolean;
    multiline: boolean;
    maxLength: number;
}
export interface NumberType extends BaseFieldType {
    required: boolean;
    unique: boolean;
    displayAsPercentage: boolean;
    decimalPlacesNumber: number;
}
export interface KDateType extends BaseFieldType {
    required: boolean;
}
export interface DateTimeType extends BaseFieldType {
    required: boolean;
}
export type SubOptionType = {
    label: I18ns;
    apiName: string;
    description: I18ns;
    color: ('grey' | 'blue' | 'cyan' | 'green' | 'yellow' | 'orange' | 'red' | 'magenta' | 'purple' | 'blueMagenta');
    active: boolean;
};
export interface OptionType extends BaseFieldType {
    required: boolean;
    multiple: boolean;
    optionSource: ('custom' | 'global');
    globalOptionApiName: string;
    optionList: SubOptionType[];
}
export interface Email extends BaseFieldType {
    required: boolean;
    unique: boolean;
}
export interface MobileNumber extends BaseFieldType {
    required: boolean;
    unique: boolean;
}
export interface Boolean extends BaseFieldType {
    descriptionWhenTrue: I18ns;
    descriptionWhenFalse: I18ns;
    defaultValue: boolean;
}
export interface AvatarOrLogo extends BaseFieldType {
    displayStyle: ('square' | 'round');
}
export interface SortConditionType {
    fieldApiName: string;
    sort: ('asc' | 'desc');
}
type ConditionType = {
    left: {
        objectApiName: string;
        fieldApiName: string;
    };
    operator: ('eq' | 'neq' | 'in' | 'notIn' | 'empty' | 'notEmpty' | 'lte' | 'gte' | 'hasAllOf' | 'hasNoneOf' | 'hasAnyOf');
    valueType: ('reference' | 'specified');
    right: (object | string);
};
export type CriterionType = {
    conditions: ConditionType[];
    logic: string;
};
export type FilterType = {
    label: string;
    needTriggerCriterion: boolean;
    triggerCriterion: CriterionType;
    criterion: CriterionType;
    errorMsg: I18ns;
};
export type RegionFilterType = {
    id: string;
    label: string;
    errorMessage: I18ns;
    recordFilter: CriterionType;
    precondition: object;
};
export interface Lookup extends BaseFieldType {
    required: boolean;
    multiple: boolean;
    objectApiName: string;
    hierarchy: boolean;
    displayStyle: ('search' | 'dropDown' | 'tree');
    sortConditions: SortConditionType[];
    filter: FilterType[];
}
export interface FormulaType extends BaseFieldType {
    returnType: string;
    formula: I18ns;
}
export interface AutoIDType extends BaseFieldType {
    generateMethod: ('random' | 'incremental');
    digitsNumber: number;
    prefix: string;
    suffix: string;
}
export interface ReferenceFieldType extends BaseFieldType {
    guideFieldApiName: string;
    fieldApiName: string;
}
export interface FileType extends BaseFieldType {
    required: boolean;
    multiple: boolean;
    fileTypes: string[];
}
export interface BackLookuType extends BaseFieldType {
    objectApiName: string;
    fieldApiName: string;
}
export interface CompositeType extends BaseFieldType {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    required: boolean;
    multiple: boolean;
}
export interface ExtractSingleRecordType extends BaseFieldType {
    compositeTypeApiName: string;
    subFields: BaseFieldType[];
    filter: FilterType[];
    sortConditions: SortConditionType[];
    recordPosition: number;
}
export type FieldType = {
    'allow_search': boolean;
    'api_name': string;
    'calculated': boolean;
    'description': I18ns;
    'domain': number;
    'encryption_mode': string;
    'field_permission': number;
    'formula_id': number;
    'id': number;
    'indexed': number;
    'inherit_settings': object;
    'is_encrypted': boolean;
    'is_inherit': boolean;
    'is_progress_field': boolean;
    'label': I18ns;
    'namespace': string;
    'object_api_name': string;
    'object_id': number;
    'order': number;
    'required': boolean;
    'tenant_id': number;
    'type': {
        'name': string;
        'settings': {
            'multiline': boolean;
            'text_version': number;
            'decimal_places': number;
            'display_as_percentage': boolean;
            'placeholder': object;
            'max_length': number;
            'regexp_expression': string;
            'regexp_err_msg': I18ns;
            'is_array': boolean;
            'option_type': string;
            'related_to_global_option': {
                'apiName': string;
                'id': number;
                'name': string;
            };
            'options': {
                'name': I18ns;
                'api_name': string;
                'description': I18ns;
                'color_id': string;
                'active': boolean;
            }[];
            'description_if_true': I18ns;
            'description_if_false': I18ns;
            'display_style': string;
            'default_value': boolean;
            'referenced_object_api_name': string;
            'is_hierarchy': boolean;
            'return_type': string;
            'formulas': I18ns;
            'generation_method': string;
            'digits': number;
            'prefix': string;
            'suffix': string;
            'target_referenced_object_api_name': string;
            'target_reference_field_api_name': string;
            'multiple': boolean;
            'mime_types': string[];
            'related_to_object_api_name': string;
            'related_to_field_api_name': string;
            'related_to_api_name': string;
            'related_to_fields': object[];
            'filter': FilterType[];
            'sort': {
                'field': string;
                'type': 'string';
                'direction': ('asc' | 'desc');
            }[];
            'filter_record': {
                'index': number;
                'type': string;
            };
            'is_extract': boolean;
            'rollup_function_type': string;
            'rolluped_object': {
                'api_alias': string;
            };
            'rolluped_field': {
                'api_alias': string;
            };
            'rolluped_lookup_field': {
                'api_alias': string;
            };
            'rollup_range_filter': CriterionType;
            'hasLevelStrict': boolean;
            'strictLevel': number;
        };
    };
    'unique_type': number;
    'updated_at': number;
    'updated_by': {
        'avatar': object;
        'id': number;
        'name': string;
    };
};
export {};
