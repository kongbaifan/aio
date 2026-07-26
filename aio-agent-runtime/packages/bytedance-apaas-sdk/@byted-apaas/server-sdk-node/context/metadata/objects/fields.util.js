"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getSettingsFilterV3 = exports.getOptionListV3 = exports.getRecordPosition = exports.getSettingsSort = exports.getSettingsFilter = exports.getCompositeTypeSubFields = exports.getCompositeTypeApiName = exports.getSettingsMultiple = exports.getBackLookupFieldApiName = exports.getBackLookupObjectApiName = exports.getFileTypes = exports.getFileMultiple = exports.getReferenceFieldApiName = exports.getReferenceObjectApiName = exports.getSuffix = exports.getPrefix = exports.getDigitsNumber = exports.getGenerateMethod = exports.getFormula = exports.getReturnType = exports.getLookupDisplayStyle = exports.getLookupIsHierarchy = exports.getLookupRefObjectApiName = exports.getDisplayStyle = exports.getDefaultValue = exports.getDescriptionWhenFalse = exports.getDescriptionWhenTrue = exports.getOptionList = exports.getGlobalOptionApiName = exports.getOptionSource = exports.getMultiple = exports.getDecimalPlaces = exports.getDisplayAsPercentage = exports.getRegexpErrMsg = exports.getRegexpExpression = exports.getMaxLength = exports.getMultiline = exports.getCaseSensitive = exports.getUnique = exports.getRollupFilter = exports.getRegionStrictLeve = exports.getRegionOptionLevel = exports.getRollupLookupFieldApiName = exports.getRollupFieldApiName = exports.getRollupObjectApiName = exports.getRollupType = exports.getRegionSettingsFilterV3 = exports.getRegionSettingsFilter = void 0;
const common = require("@byted-apaas/server-common-node");
const common_1 = require("../types/common");
const commonConstants = common.constants;
const commonUtils = common.utils;
/*
UniqueEnumNone                              = 1
UniqueEnumMultilingualCaseSensitive         = 2
UniqueEnumMultilingualCaseInsensitive       = 3
UniqueEnumTextCaseSensitive                 = 4
UniqueEnumTextCaseInsensitive               = 5
UniqueEnumUniqueEmail                       = 6
UniqueEnumUniquePhoneNumber                 = 7
UniqueEnumUniqueNumber                      = 8
UniqueEnumUniqueAutoNumberCaseSensitive     = 9
UniqueEnumUniqueAutoNumberCaseInsensitive   = 10
 */
function getUnique(field) {
    if (field && !(0, common_1.isNullOrUndefined)(field.unique_type)) {
        return field.unique_type > 1;
    }
    return false;
}
exports.getUnique = getUnique;
function getCaseSensitive(field) {
    if (field && !(0, common_1.isNullOrUndefined)(field.unique_type)) {
        return [2, 4, 9].includes(field.unique_type);
    }
    return true;
}
exports.getCaseSensitive = getCaseSensitive;
function getMultiline(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.multiline)) {
        return field.type.settings.multiline;
    }
    return false;
}
exports.getMultiline = getMultiline;
function getMaxLength(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.max_length)) {
        return field.type.settings.max_length;
    }
    return 255;
}
exports.getMaxLength = getMaxLength;
function getRegexpExpression(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.regexp_expression)) {
        return field.type.settings.regexp_expression;
    }
    return null;
}
exports.getRegexpExpression = getRegexpExpression;
function getRegexpErrMsg(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.regexp_err_msg)) {
        return field.type.settings.regexp_err_msg;
    }
    return null;
}
exports.getRegexpErrMsg = getRegexpErrMsg;
function getDisplayAsPercentage(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.display_as_percentage)) {
        return field.type.settings.display_as_percentage;
    }
    return false;
}
exports.getDisplayAsPercentage = getDisplayAsPercentage;
function getDecimalPlaces(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.decimal_places)) {
        return field.type.settings.decimal_places;
    }
    return 0;
}
exports.getDecimalPlaces = getDecimalPlaces;
function getMultiple(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.is_array)) {
        return field.type.settings.is_array;
    }
    return false;
}
exports.getMultiple = getMultiple;
// 开发者感知 custom, global
// 底层存储  local, global
function getOptionSource(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.option_type)) {
        if (field.type.settings.option_type === 'local') {
            return 'custom';
        }
        else if (field.type.settings.option_type === 'global') {
            return 'global';
        }
    }
    return 'custom';
}
exports.getOptionSource = getOptionSource;
function getGlobalOptionApiName(field) {
    if (field && field.type && field.type.settings && field.type.settings.related_to_global_option && !(0, common_1.isNullOrUndefined)(field.type.settings.related_to_global_option.apiName)) {
        return field.type.settings.related_to_global_option.apiName;
    }
    return '';
}
exports.getGlobalOptionApiName = getGlobalOptionApiName;
function getOptionList(field) {
    if (!field || !field.type || !field.type.settings || !field.type.settings.options || !Array.isArray(field.type.settings.options)) {
        return [];
    }
    let options = [];
    for (let option of field.type.settings.options) {
        options.push({
            label: option.name,
            apiName: option.api_name,
            description: option.description,
            color: commonUtils.getColorNameById(option.color_id),
            active: Number(option.active) === 1,
        });
    }
    return options;
}
exports.getOptionList = getOptionList;
function getOptionListV3(field) {
    if (!field || !field.type || !field.type.settings || !field.type.settings.options || !Array.isArray(field.type.settings.options)) {
        return [];
    }
    let options = [];
    for (let option of field.type.settings.options) {
        options.push({
            label: (0, common_1.transI18nsToMultilingualV3)(option.name),
            apiName: option.api_name,
            description: (0, common_1.transI18nsToMultilingualV3)(option.description),
            color: commonUtils.getColorNameById(option.color_id),
            active: Number(option.active) === 1,
        });
    }
    return options;
}
exports.getOptionListV3 = getOptionListV3;
function getDescriptionWhenTrue(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.description_if_true)) {
        return field.type.settings.description_if_true;
    }
    return [];
}
exports.getDescriptionWhenTrue = getDescriptionWhenTrue;
function getDescriptionWhenFalse(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.description_if_false)) {
        return field.type.settings.description_if_false;
    }
    return [];
}
exports.getDescriptionWhenFalse = getDescriptionWhenFalse;
function getDefaultValue(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.default_value)) {
        return field.type.settings.default_value;
    }
    return false;
}
exports.getDefaultValue = getDefaultValue;
function getDisplayStyle(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.display_style)) {
        return field.type.settings.display_style;
    }
    return 'square';
}
exports.getDisplayStyle = getDisplayStyle;
function getLookupRefObjectApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.referenced_object_api_name)) {
        return field.type.settings.referenced_object_api_name;
    }
    return '';
}
exports.getLookupRefObjectApiName = getLookupRefObjectApiName;
function getLookupIsHierarchy(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.is_hierarchy)) {
        return field.type.settings.is_hierarchy;
    }
    return false;
}
exports.getLookupIsHierarchy = getLookupIsHierarchy;
// 'search'|'dropDown'|'tree'
function getLookupDisplayStyle(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.display_style)) {
        return field.type.settings.display_style;
    }
    return 'dropDown';
}
exports.getLookupDisplayStyle = getLookupDisplayStyle;
function getReturnType(field) {
    // TODO: check returnType to return_type
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.return_type)) {
        return field.type.settings.return_type;
    }
    return '';
}
exports.getReturnType = getReturnType;
function getFormula(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.formulas)) {
        return field.type.settings.formulas;
    }
    return [];
}
exports.getFormula = getFormula;
// 'random'|'incremental'
function getGenerateMethod(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.generation_method)) {
        return field.type.settings.generation_method;
    }
    return 'random';
}
exports.getGenerateMethod = getGenerateMethod;
function getDigitsNumber(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.digits)) {
        return field.type.settings.digits;
    }
    return 6;
}
exports.getDigitsNumber = getDigitsNumber;
function getPrefix(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.prefix)) {
        return field.type.settings.prefix;
    }
    return '';
}
exports.getPrefix = getPrefix;
function getSuffix(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.suffix)) {
        return field.type.settings.suffix;
    }
    return '';
}
exports.getSuffix = getSuffix;
function getReferenceObjectApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.target_referenced_object_api_name)) {
        return field.type.settings.target_referenced_object_api_name;
    }
    return '';
}
exports.getReferenceObjectApiName = getReferenceObjectApiName;
function getReferenceFieldApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.target_reference_field_api_name)) {
        return field.type.settings.target_reference_field_api_name;
    }
    return '';
}
exports.getReferenceFieldApiName = getReferenceFieldApiName;
function getFileMultiple(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.multiple)) {
        return field.type.settings.multiple;
    }
    return false;
}
exports.getFileMultiple = getFileMultiple;
function getFileTypes(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.mime_types)) {
        return field.type.settings.mime_types;
    }
    return [];
}
exports.getFileTypes = getFileTypes;
function getBackLookupObjectApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.related_to_object_api_name)) {
        return field.type.settings.related_to_object_api_name;
    }
    return '';
}
exports.getBackLookupObjectApiName = getBackLookupObjectApiName;
function getBackLookupFieldApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.related_to_field_api_name)) {
        return field.type.settings.related_to_field_api_name;
    }
    return '';
}
exports.getBackLookupFieldApiName = getBackLookupFieldApiName;
function getSettingsMultiple(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.multiple)) {
        return field.type.settings.multiple;
    }
    return false;
}
exports.getSettingsMultiple = getSettingsMultiple;
function getCompositeTypeApiName(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.related_to_api_name)) {
        return field.type.settings.related_to_api_name;
    }
    return '';
}
exports.getCompositeTypeApiName = getCompositeTypeApiName;
function getCompositeTypeSubFields(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.related_to_fields)) {
        return field.type.settings.related_to_fields;
    }
    return [];
}
exports.getCompositeTypeSubFields = getCompositeTypeSubFields;
// TODO 结构转换
function getSettingsFilter(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.filter)) {
        return field.type.settings.filter;
    }
    return [];
}
exports.getSettingsFilter = getSettingsFilter;
function getSettingsFilterV3(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.filter)) {
        return field.type.settings.filter;
    }
    return [];
}
exports.getSettingsFilterV3 = getSettingsFilterV3;
function getRegionSettingsFilter(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.filter)) {
        return field.type.settings.filter;
    }
    return [];
}
exports.getRegionSettingsFilter = getRegionSettingsFilter;
function getRegionSettingsFilterV3(field) {
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.filter)) {
        const res = field.type.settings.filter.map(s => {
            let f = s;
            const tmp = {
                id: f.id,
                label: f.label,
                errorMessage: (0, common_1.transI18nsToMultilingualV3)(f.errorMessage),
                recordFilter: f.recordFilter,
                precondition: f.precondition,
            };
            return tmp;
        });
        return res;
    }
    return [];
}
exports.getRegionSettingsFilterV3 = getRegionSettingsFilterV3;
// TODO 结构转换
function getSettingsSort(field) {
    let res = [];
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.sort)) {
        for (const s of field.type.settings.sort) {
            res.push(({
                fieldApiName: s.field,
                sort: s.direction,
            }));
        }
        return res;
    }
    return [];
}
exports.getSettingsSort = getSettingsSort;
function getRecordPosition(field) {
    let pos = 1;
    if (field && field.type && field.type.settings && !(0, common_1.isNullOrUndefined)(field.type.settings.filter_record)) {
        // first, last, specified
        switch (field.type.settings.filter_record.type) {
            case 'first':
                pos = 1;
                break;
            case 'last':
                pos = -1;
                break;
            case 'specified':
                pos = field.type.settings.filter_record.index;
                break;
        }
    }
    return pos;
}
exports.getRecordPosition = getRecordPosition;
function getRollupType(field) {
    if (field && field.type && field.type.settings && field.type.settings.rollup_function_type) {
        return field.type.settings.rollup_function_type;
    }
    return "";
}
exports.getRollupType = getRollupType;
function getRollupObjectApiName(field) {
    if (field && field.type && field.type.settings && field.type.settings.rolluped_object && field.type.settings.rolluped_object.api_alias) {
        return field.type.settings.rolluped_object.api_alias;
    }
    return "";
}
exports.getRollupObjectApiName = getRollupObjectApiName;
function getRollupFieldApiName(field) {
    if (field && field.type && field.type.settings && field.type.settings.rolluped_field && field.type.settings.rolluped_field.api_alias) {
        return field.type.settings.rolluped_field.api_alias;
    }
    return "";
}
exports.getRollupFieldApiName = getRollupFieldApiName;
function getRollupLookupFieldApiName(field) {
    if (field && field.type && field.type.settings && field.type.settings.rolluped_lookup_field && field.type.settings.rolluped_lookup_field.api_alias) {
        return field.type.settings.rolluped_lookup_field.api_alias;
    }
    return "";
}
exports.getRollupLookupFieldApiName = getRollupLookupFieldApiName;
function getRegionOptionLevel(field) {
    if (field && field.type && field.type.settings && field.type.settings.hasLevelStrict) {
        return field.type.settings.hasLevelStrict;
    }
    return undefined;
}
exports.getRegionOptionLevel = getRegionOptionLevel;
function getRegionStrictLeve(field) {
    if (field && field.type && field.type.settings && field.type.settings.strictLevel) {
        return field.type.settings.strictLevel;
    }
    return undefined;
}
exports.getRegionStrictLeve = getRegionStrictLeve;
function getRollupFilter(field) {
    if (field && field.type && field.type.settings && field.type.settings.rollup_range_filter) {
        return {
            conditions: field.type.settings.rollup_range_filter.conditions,
            logic: field.type.settings.rollup_range_filter.logic
        };
    }
    return undefined;
}
exports.getRollupFilter = getRollupFilter;
