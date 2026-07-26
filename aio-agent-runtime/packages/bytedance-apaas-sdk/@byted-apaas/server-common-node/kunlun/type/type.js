"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.isKFieldTypeDate = exports.isKFieldTypeMultilingual = exports.isKFieldType = exports.isKunlunType = exports.type2fieldType = exports.DateTime = exports.Date = exports.Phone = exports.Multilingual = exports.Email = exports.Boolean = exports.Number = exports.Text = exports.KunlunFieldType = void 0;
function getUtils() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../utils/utils');
}
function getCheckUtils() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../utils/checkUtils');
}
function getConstants() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../constants/constants');
}
function getExceptions() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../../utils/exceptions');
}
const dayjs = require("dayjs");
const timeZone_1 = require("../../constants/timeZone");
const countryCode_1 = require("../../constants/countryCode");
function checkArrayNumber(...params) {
    params.forEach((param, i) => {
        if (typeof (param) !== 'number') {
            throw new (getExceptions()).InvalidParamError(`params[${i}] is not number, but ${typeof (param)}`);
        }
    });
}
class KunlunFieldType {
    constructor(type) {
        this.baseType = 'KunlunFieldType';
        this.type = type;
    }
    toString() {
        let json = this.toJSON();
        if (typeof (json) === 'string') {
            return json;
        }
        return getUtils().stringify(json);
    }
    toJSON() {
        return null;
    }
    checkVariables(variables, key) {
        if (!variables) {
            throw new (getExceptions()).InvalidParamError('context.workflow.variables is empty');
        }
        if (!key) {
            throw new (getExceptions()).InvalidParamError('key is empty');
        }
        if (!variables.hasOwnProperty(key)) {
            throw new (getExceptions()).InvalidParamError(`context.workflow.variables do not have key(${key})`);
        }
    }
}
exports.KunlunFieldType = KunlunFieldType;
class Text extends KunlunFieldType {
    constructor(param) {
        super('text');
        if (typeof (param) !== 'string') {
            throw new (getExceptions()).InvalidParamError(`Text's param is not string, but ${typeof (param)}`);
        }
        this.value = param;
    }
    toJSON() {
        return this.value;
    }
}
exports.Text = Text;
class Number extends KunlunFieldType {
    constructor(param) {
        super('float');
        if (typeof (param) !== 'number') {
            throw new (getExceptions()).InvalidParamError(`Number's param is not number, but ${typeof (param)}`);
        }
        this.value = param;
    }
    toJSON() {
        return this.value;
    }
}
exports.Number = Number;
class Boolean extends KunlunFieldType {
    constructor(param) {
        super('boolean');
        if (typeof (param) !== 'boolean') {
            throw new (getExceptions()).InvalidParamError(`Boolean's param is not boolean, but ${typeof (param)}`);
        }
        this.value = param;
    }
    toJSON() {
        return this.value;
    }
}
exports.Boolean = Boolean;
class Email extends KunlunFieldType {
    constructor(param) {
        super('email');
        if (typeof (param) !== 'string') {
            throw new (getExceptions()).InvalidParamError(`Email's param is not string, but ${typeof (param)}`);
        }
        this.value = param;
    }
    toJSON() {
        return this.value;
    }
}
exports.Email = Email;
//------------------------------kunlun暴露的类 start------------------------------------------------------------------------------------
/**
 * 多语文本类
 * 构造方法：
 * ```
 * constructor(valueMap)
 * ```
 */
class Multilingual extends KunlunFieldType {
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
    constructor(valueMap) {
        super('multilingual');
        if (getCheckUtils().isNotObject(valueMap)) {
            if (valueMap instanceof Array) {
                throw new (getExceptions()).InvalidParamError("Multilingual's param is not object, but array");
            }
            throw new (getExceptions()).InvalidParamError(`Multilingual's param is not object, but ${typeof (valueMap)}`);
        }
        this.valueList = [];
        let hasZh = false;
        let hasCn = false;
        let hasEn = false;
        let zhValue = null;
        let cnValue = null;
        let enValue = null;
        for (let code of Object.keys(valueMap)) {
            if (!(code in getConstants().languageCode)) {
                throw new (getExceptions()).InvalidParamError(`LanguageCode can not support this code(${code})`);
            }
            if (code === 'zh') {
                hasZh = true;
                zhValue = { language_code: getConstants().languageCode[code], text: valueMap[code] };
            }
            // cn 兼容逻辑: 兼容老版本用户传入 cn 的情况
            if (code === 'cn') {
                hasCn = true;
                cnValue = { language_code: getConstants().languageCode[code], text: valueMap[code] };
            }
            if (code === 'en') {
                hasEn = true;
                enValue = { language_code: getConstants().languageCode[code], text: valueMap[code] };
            }
        }
        if (hasZh) {
            this.valueList.push(zhValue);
        }
        if (hasCn && !hasZh) {
            this.valueList.push(cnValue);
        }
        if (hasEn) {
            this.valueList.push(enValue);
        }
        this.value = valueMap;
    }
    toJSON() {
        return this.valueList;
    }
    toString() {
        return getUtils().stringify(this);
    }
}
exports.Multilingual = Multilingual;
/**
 * 电话类
 * 构造方法：
 * ```
 * constructor(phoneNumber)
 * constructor(phoneNumber, countryCode)
 * ```
 */
class Phone extends KunlunFieldType {
    constructor(...params) {
        super('phone');
        if (params.length < 1 || params.length > 2) {
            throw new (getExceptions()).InvalidParamError(`the length of Phone's params is 1 or 2, but ${params.length}`);
        }
        if (params.length > 0) {
            if (typeof (params[0]) !== 'string') {
                throw new (getExceptions()).InvalidParamError(`Phone's params[0] is not string, but ${typeof (params[0])}`);
            }
            this.number = params[0];
        }
        if (params.length === 2) {
            if (typeof (params[1]) !== 'string') {
                throw new (getExceptions()).InvalidParamError(`Phone's params[1] is not string, but ${typeof (params[1])}`);
            }
            if (countryCode_1.code2area.hasOwnProperty(params[1])) {
                this.key = `${params[1]}(${countryCode_1.code2area[params[1]]})`;
            }
            else {
                this.key = params[1];
            }
        }
        if (!this.key) {
            this.key = '+86(CN)';
        }
    }
    toJSON() {
        return { 'key': this.key, 'number': this.number };
    }
}
exports.Phone = Phone;
/**
 * 日期类：
 * 构造方法
 * ```
 * constructor(stringDate)
 * constructor(year, month, day)
 * ```
 */
class KDate extends KunlunFieldType {
    constructor(...params) {
        super('date');
        if (params.length === 0) {
            dayjs();
            this.value = dayjs().format('YYYY-MM-DD');
            return;
        }
        if (params.length === 1) {
            if (typeof (params[0]) !== 'string') {
                throw new (getExceptions()).InvalidParamError(`while one params: Date's param is not string, but ${typeof (params[0])}`);
            }
            this.value = params[0];
            return;
        }
        if (params.length === 3) {
            checkArrayNumber(...params);
            this.value = dayjs(new Date(params[0], params[1] - 1, params[2])).format('YYYY-MM-DD');
            return;
        }
        throw new (getExceptions()).InvalidParamError(`the length of Date's params is 0, 1 or 3, but ${params.length}`);
    }
    toJSON() {
        return this.value;
    }
}
exports.Date = KDate;
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
class DateTime extends KunlunFieldType {
    constructor(...params) {
        super('datetime');
        if (params.length === 1) {
            this.value = new Date(params[0]).getTime();
            return;
        }
        if (params.length === 0) {
            this.value = new Date().getTime();
            return;
        }
        if (params.length === 6) {
            const dateTimeStr = params[0] + '-' + params[1] + '-' + params[2] + ' ' + params[3] + ':' + params[4] + ':' + params[5] + ' ' + timeZone_1.GMTOffset.GMT08;
            this.value = new Date(dateTimeStr).getTime();
            return;
        }
        if (params.length === 7) {
            const dateTimeStr = params[0] + '-' + params[1] + '-' + params[2] + ' ' + params[3] + ':' + params[4] + ':' + params[5] + ' ' + params[6];
            this.value = new Date(dateTimeStr).getTime();
            return;
        }
        throw new (getExceptions()).InvalidParamError(`the length of Datetime's params is 0, 1, 6 or 7, but ${params.length}`);
    }
    toJSON() {
        return this.value;
    }
}
exports.DateTime = DateTime;
//------------------------------kunlun暴露的类 end------------------------------------------------------------------------------------
exports.type2fieldType = {
    'text': Text,
    'float': Number,
    'boolean': Boolean,
    'email': Email,
    'multilingual': Multilingual,
    'date': KDate,
    'datetime': DateTime,
    'phone': Phone,
};
function isKunlunType(input) {
    for (let key of Object.keys(exports.type2fieldType)) {
        if (input instanceof exports.type2fieldType[key]) {
            return true;
        }
    }
    return false;
}
exports.isKunlunType = isKunlunType;
/**
 * type2fieldType isKunlunType
 * 之前在 kunlun 下有，无智能提示
 */
function isKFieldType(value) {
    return value && value.baseType === 'KunlunFieldType';
}
exports.isKFieldType = isKFieldType;
function isKFieldTypeMultilingual(value) {
    return value && value.baseType === 'KunlunFieldType' && value.type === 'multilingual';
}
exports.isKFieldTypeMultilingual = isKFieldTypeMultilingual;
function isKFieldTypeDate(value) {
    return value && value.baseType === 'KunlunFieldType' && value.type === 'date';
}
exports.isKFieldTypeDate = isKFieldTypeDate;
