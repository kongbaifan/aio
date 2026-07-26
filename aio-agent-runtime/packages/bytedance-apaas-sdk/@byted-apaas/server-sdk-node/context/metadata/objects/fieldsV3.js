"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFieldClassV3 = exports.parseFieldV3 = exports.parseFieldsV3 = exports.RollupV3 = exports.RegionV3 = exports.DecimalV3 = exports.BigintV3 = exports.RichTextV3 = exports.ExtractSingleRecordV3 = exports.CompositeTypeV3 = exports.BackLookupV3 = exports.FileV3 = exports.ReferenceFieldV3 = exports.AutoIDV3 = exports.FormulaV3 = exports.LookupV3 = exports.AvatarOrLogoV3 = exports.BooleanV3 = exports.MobileNumberV3 = exports.EmailV3 = exports.OptionV3 = exports.DateTimeV3 = exports.DateV3 = exports.NumberV3 = exports.MultilingualV3 = exports.TextV3 = void 0;
const fieldsUtil = require("./fields.util");
const common_1 = require("../types/common");
class MetadataFieldV3 {
    constructor(type, field) {
        this.type = type;
        this.apiName = field.api_name;
        this.label = (0, common_1.transI18nsToMultilingualV3)(field.label);
    }
}
class KTextV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('text', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
        this.caseSensitive = fieldsUtil.getCaseSensitive(field);
        this.multiline = fieldsUtil.getMultiline(field);
        this.maxLength = fieldsUtil.getMaxLength(field);
        this.validationRegex = fieldsUtil.getRegexpExpression(field);
        this.errorMsg = (0, common_1.transI18nsToMultilingualV3)(fieldsUtil.getRegexpErrMsg(field));
    }
}
exports.TextV3 = KTextV3;
class RichTextV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('richText', field);
        this.maxLength = fieldsUtil.getMaxLength(field);
        this.required = field.required;
    }
}
exports.RichTextV3 = RichTextV3;
class MultilingualV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('multilingual', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
        this.caseSensitive = fieldsUtil.getCaseSensitive(field);
        this.multiline = fieldsUtil.getMultiline(field);
        this.maxLength = fieldsUtil.getMaxLength(field);
    }
}
exports.MultilingualV3 = MultilingualV3;
class NumberV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('number', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
        this.displayAsPercentage = fieldsUtil.getDisplayAsPercentage(field);
        this.decimalPlacesNumber = fieldsUtil.getDecimalPlaces(field);
    }
}
exports.NumberV3 = NumberV3;
class BigintV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('bigint', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.BigintV3 = BigintV3;
class DecimalV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('decimal', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
        this.displayAsPercentage = fieldsUtil.getDisplayAsPercentage(field);
        this.decimalPlacesNumber = fieldsUtil.getDecimalPlaces(field);
    }
}
exports.DecimalV3 = DecimalV3;
class KDateV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('date', field);
        this.required = field.required;
    }
}
exports.DateV3 = KDateV3;
class DateTimeV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('dateTime', field);
        this.required = field.required;
    }
}
exports.DateTimeV3 = DateTimeV3;
class OptionV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('option', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getMultiple(field);
        this.optionSource = fieldsUtil.getOptionSource(field);
        this.globalOptionApiName = fieldsUtil.getGlobalOptionApiName(field);
        this.optionList = fieldsUtil.getOptionListV3(field);
    }
}
exports.OptionV3 = OptionV3;
class EmailV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('email', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.EmailV3 = EmailV3;
class MobileNumberV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('mobileNumber', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.MobileNumberV3 = MobileNumberV3;
class BooleanV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('boolean', field);
        this.unique = fieldsUtil.getUnique(field);
        this.descriptionWhenTrue = (0, common_1.transI18nsToMultilingualV3)(fieldsUtil.getDescriptionWhenTrue(field));
        this.descriptionWhenFalse = (0, common_1.transI18nsToMultilingualV3)(fieldsUtil.getDescriptionWhenFalse(field));
        this.defaultValue = fieldsUtil.getDefaultValue(field);
    }
}
exports.BooleanV3 = BooleanV3;
class AvatarOrLogoV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('avatarOrLogo', field);
        this.displayStyle = fieldsUtil.getDisplayStyle(field);
    }
}
exports.AvatarOrLogoV3 = AvatarOrLogoV3;
class LookupV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('lookup', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getMultiple(field);
        this.objectApiName = fieldsUtil.getLookupRefObjectApiName(field);
        this.hierarchy = fieldsUtil.getLookupIsHierarchy(field);
        this.displayStyle = fieldsUtil.getLookupDisplayStyle(field);
        // TODO
        this.sortConditions = fieldsUtil.getSettingsSort(field);
        this.filter = [];
    }
}
exports.LookupV3 = LookupV3;
class FormulaV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('formula', field);
        this.returnType = fieldsUtil.getReturnType(field);
        this.formula = (0, common_1.transI18nsToMultilingualV3)(fieldsUtil.getFormula(field));
    }
}
exports.FormulaV3 = FormulaV3;
class AutoIDV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('autoId', field);
        this.generateMethod = fieldsUtil.getGenerateMethod(field);
        this.digitsNumber = fieldsUtil.getDigitsNumber(field);
        this.prefix = fieldsUtil.getPrefix(field);
        this.suffix = fieldsUtil.getSuffix(field);
    }
}
exports.AutoIDV3 = AutoIDV3;
class ReferenceFieldV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('referenceField', field);
        // TODO: check objectApiName to guideFieldApiName
        this.guideFieldApiName = fieldsUtil.getReferenceObjectApiName(field);
        this.fieldApiName = fieldsUtil.getReferenceFieldApiName(field);
    }
}
exports.ReferenceFieldV3 = ReferenceFieldV3;
class RollupV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('rollup', field);
        this.rollupType = fieldsUtil.getRollupType(field);
        this.rollupObjectApiName = fieldsUtil.getRollupObjectApiName(field);
        this.rollupFieldApiName = fieldsUtil.getRollupFieldApiName(field);
        this.rollupLookupFieldApiName = fieldsUtil.getRollupLookupFieldApiName(field);
        this.filter = fieldsUtil.getRollupFilter(field);
    }
}
exports.RollupV3 = RollupV3;
class RegionV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('region', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getSettingsMultiple(field);
        this.optionLevel = fieldsUtil.getRegionOptionLevel(field);
        this.strictLevel = fieldsUtil.getRegionStrictLeve(field);
        this.filter = fieldsUtil.getRegionSettingsFilterV3(field);
    }
}
exports.RegionV3 = RegionV3;
class FileV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('file', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getFileMultiple(field);
        this.fileTypes = fieldsUtil.getFileTypes(field);
    }
}
exports.FileV3 = FileV3;
class BackLookupV3 extends MetadataFieldV3 {
    // objectApiName: string; // TODO 由于下游提供仍是 api ID 版本，因此禁用
    // fieldApiName: string; //  由于下游提供仍是 api ID 版本，因此禁用
    constructor(field) {
        if (!field) {
            return;
        }
        super('backLookup', field);
        // TODO 由于下游提供仍是 api ID 版本，因此禁用
        // this.objectApiName = fieldsUtil.getBackLookupObjectApiName(field);
        // this.fieldApiName = fieldsUtil.getBackLookupFieldApiName(field); // TODO metadata返回值为空
    }
}
exports.BackLookupV3 = BackLookupV3;
class CompositeTypeV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('compositeType', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getSettingsMultiple(field);
        this.compositeTypeApiName = fieldsUtil.getCompositeTypeApiName(field);
        // TODO 字段类型转换
        this.subFields = parseFieldsV3(fieldsUtil.getCompositeTypeSubFields(field));
    }
}
exports.CompositeTypeV3 = CompositeTypeV3;
class ExtractSingleRecordV3 extends MetadataFieldV3 {
    constructor(field) {
        if (!field) {
            return;
        }
        super('extractSingleRecord', field);
        this.compositeTypeApiName = fieldsUtil.getCompositeTypeApiName(field);
        // TODO 字段类型转换
        this.subFields = parseFieldsV3(fieldsUtil.getCompositeTypeSubFields(field));
        this.filter = fieldsUtil.getSettingsFilterV3(field);
        this.sortConditions = fieldsUtil.getSettingsSort(field);
        this.recordPosition = fieldsUtil.getRecordPosition(field);
    }
}
exports.ExtractSingleRecordV3 = ExtractSingleRecordV3;
function getCompositeTypeClass(field) {
    if (field && field.type && field.type.settings && field.type.settings.is_extract) {
        return ExtractSingleRecordV3;
    }
    return CompositeTypeV3;
}
function parseFieldsV3(inputFields) {
    if (!inputFields || !Array.isArray(inputFields)) {
        return [];
    }
    let fields = [];
    for (let field of inputFields) {
        const fieldClass = getFieldClassV3(field);
        if (!fieldClass) {
            continue;
        }
        fields.push(new fieldClass(field));
    }
    return fields;
}
exports.parseFieldsV3 = parseFieldsV3;
function parseFieldV3(field) {
    const fieldClass = getFieldClassV3(field);
    if (fieldClass) {
        return new fieldClass(field);
    }
    return null;
}
exports.parseFieldV3 = parseFieldV3;
function getFieldClassV3(field) {
    if (field && field.type && field.type.name) {
        if (field.type.name === 'compositeType') {
            return getCompositeTypeClass(field);
        }
        return type2fieldTypeV3[field.type.name];
    }
    return null;
}
exports.getFieldClassV3 = getFieldClassV3;
const type2fieldTypeV3 = {
    'text': KTextV3,
    'multilingual': MultilingualV3,
    'float': NumberV3,
    'date': KDateV3,
    'datetime': DateTimeV3,
    'enum': OptionV3,
    'email': EmailV3,
    'phone': MobileNumberV3,
    'boolean': BooleanV3,
    'avatar': AvatarOrLogoV3,
    'lookup': LookupV3,
    'formula': FormulaV3,
    'auto_number': AutoIDV3,
    'reference_field': ReferenceFieldV3,
    'attachment': FileV3,
    'back_lookup': BackLookupV3,
    'richText': RichTextV3,
    'bigint': BigintV3,
    'decimal': DecimalV3,
    'rollup': RollupV3,
    'region': RegionV3,
};
