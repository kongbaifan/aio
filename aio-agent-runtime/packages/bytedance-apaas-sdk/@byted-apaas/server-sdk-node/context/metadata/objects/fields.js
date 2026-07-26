"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFieldClass = exports.parseField = exports.parseFields = exports.Rollup = exports.Region = exports.Decimal = exports.Bigint = exports.RichText = exports.ExtractSingleRecord = exports.CompositeType = exports.BackLookup = exports.File = exports.ReferenceField = exports.AutoID = exports.Formula = exports.Lookup = exports.AvatarOrLogo = exports.Boolean = exports.MobileNumber = exports.Email = exports.Option = exports.DateTime = exports.Date = exports.Number = exports.Multilingual = exports.Text = void 0;
const fieldsUtil = require("./fields.util");
class MetadataField {
    constructor(type, field) {
        this.type = type;
        this.apiName = field.api_name;
        this.label = field.label;
    }
}
class KText extends MetadataField {
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
        this.errorMsg = fieldsUtil.getRegexpErrMsg(field);
    }
}
exports.Text = KText;
class RichText extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('richText', field);
        this.maxLength = fieldsUtil.getMaxLength(field);
        this.required = field.required;
    }
}
exports.RichText = RichText;
class Multilingual extends MetadataField {
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
exports.Multilingual = Multilingual;
class Number extends MetadataField {
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
exports.Number = Number;
class Bigint extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('bigint', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.Bigint = Bigint;
class Decimal extends MetadataField {
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
exports.Decimal = Decimal;
class KDate extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('date', field);
        this.required = field.required;
    }
}
exports.Date = KDate;
class DateTime extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('dateTime', field);
        this.required = field.required;
    }
}
exports.DateTime = DateTime;
class Option extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('option', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getMultiple(field);
        this.optionSource = fieldsUtil.getOptionSource(field);
        this.globalOptionApiName = fieldsUtil.getGlobalOptionApiName(field);
        this.optionList = fieldsUtil.getOptionList(field);
    }
}
exports.Option = Option;
class Email extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('email', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.Email = Email;
class MobileNumber extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('mobileNumber', field);
        this.required = field.required;
        this.unique = fieldsUtil.getUnique(field);
    }
}
exports.MobileNumber = MobileNumber;
class Boolean extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('boolean', field);
        this.unique = fieldsUtil.getUnique(field);
        this.descriptionWhenTrue = fieldsUtil.getDescriptionWhenTrue(field);
        this.descriptionWhenFalse = fieldsUtil.getDescriptionWhenFalse(field);
        this.defaultValue = fieldsUtil.getDefaultValue(field);
    }
}
exports.Boolean = Boolean;
class AvatarOrLogo extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('avatarOrLogo', field);
        this.displayStyle = fieldsUtil.getDisplayStyle(field);
    }
}
exports.AvatarOrLogo = AvatarOrLogo;
class Lookup extends MetadataField {
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
exports.Lookup = Lookup;
class Formula extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('formula', field);
        this.returnType = fieldsUtil.getReturnType(field);
        // TODO 由于下游提供仍是 api ID 版本，因此禁用
        this.formula = null; //fieldsUtil.getFormula(field);
    }
}
exports.Formula = Formula;
class AutoID extends MetadataField {
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
exports.AutoID = AutoID;
class ReferenceField extends MetadataField {
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
exports.ReferenceField = ReferenceField;
class Rollup extends MetadataField {
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
exports.Rollup = Rollup;
class Region extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('region', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getSettingsMultiple(field);
        this.optionLevel = fieldsUtil.getRegionOptionLevel(field);
        this.strictLevel = fieldsUtil.getRegionStrictLeve(field);
        this.filter = fieldsUtil.getRegionSettingsFilter(field);
    }
}
exports.Region = Region;
class File extends MetadataField {
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
exports.File = File;
class BackLookup extends MetadataField {
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
exports.BackLookup = BackLookup;
class CompositeType extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('compositeType', field);
        this.required = field.required;
        this.multiple = fieldsUtil.getSettingsMultiple(field);
        this.compositeTypeApiName = fieldsUtil.getCompositeTypeApiName(field);
        // TODO 字段类型转换
        this.subFields = parseFields(fieldsUtil.getCompositeTypeSubFields(field));
    }
}
exports.CompositeType = CompositeType;
class ExtractSingleRecord extends MetadataField {
    constructor(field) {
        if (!field) {
            return;
        }
        super('extractSingleRecord', field);
        this.compositeTypeApiName = fieldsUtil.getCompositeTypeApiName(field);
        // TODO 字段类型转换
        this.subFields = parseFields(fieldsUtil.getCompositeTypeSubFields(field));
        this.filter = fieldsUtil.getSettingsFilter(field);
        this.sortConditions = fieldsUtil.getSettingsSort(field);
        this.recordPosition = fieldsUtil.getRecordPosition(field);
    }
}
exports.ExtractSingleRecord = ExtractSingleRecord;
function getCompositeTypeClass(field) {
    if (field && field.type && field.type.settings && field.type.settings.is_extract) {
        return ExtractSingleRecord;
    }
    return CompositeType;
}
function parseFields(inputFields) {
    if (!inputFields || !Array.isArray(inputFields)) {
        return [];
    }
    let fields = [];
    for (let field of inputFields) {
        let FieldClass = getFieldClass(field);
        if (!FieldClass) {
            continue;
        }
        fields.push(new FieldClass(field));
    }
    return fields;
}
exports.parseFields = parseFields;
function parseField(field) {
    let FieldClass = getFieldClass(field);
    if (FieldClass) {
        return new FieldClass(field);
    }
    return null;
}
exports.parseField = parseField;
function getFieldClass(field) {
    if (field && field.type && field.type.name) {
        if (field.type.name === 'compositeType') {
            return getCompositeTypeClass(field);
        }
        return type2fieldType[field.type.name];
    }
    return null;
}
exports.getFieldClass = getFieldClass;
const type2fieldType = {
    'text': KText,
    'multilingual': Multilingual,
    'float': Number,
    'date': KDate,
    'datetime': DateTime,
    'enum': Option,
    'email': Email,
    'phone': MobileNumber,
    'boolean': Boolean,
    'avatar': AvatarOrLogo,
    'lookup': Lookup,
    'formula': Formula,
    'auto_number': AutoID,
    'reference_field': ReferenceField,
    'attachment': File,
    'back_lookup': BackLookup,
    'richText': RichText,
    'bigint': Bigint,
    'decimal': Decimal,
    'rollup': Rollup,
    'region': Region,
};
