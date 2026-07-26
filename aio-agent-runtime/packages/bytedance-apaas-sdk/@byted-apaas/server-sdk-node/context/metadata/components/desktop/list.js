"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.List = void 0;
const common = require("@byted-apaas/server-common-node");
const commonUtils = common.utils;
const common_1 = require("../common");
const common_2 = require("../../types/common");
/*
titleAreaText: i18n;
objectApiName: string;
isCompositeType: boolean;
titleFields: [{
    fieldApiName: string;
},...]
subtitleFields: [{
    type: 'field'|'concatText'
    fieldApiName: string;
    alias: i18n;
    concatText: {
        zh_CN: [{
            dataType: 'fieldApiName'|'text'
            fieldApiName: string;
            text: string;
        },...]
        en_US: [{
            dataType: 'fieldApiName'|'text'
            fieldApiName: string;
            text: string;
        },...]
    }
},...]
detailFields: [{
    fieldApiName: string;
    alias: i18n;
},...]
filter: {
    conditions: object[];
    logic: string;
};
sortConditions: object[];
 */
class List extends common_1.Component {
    constructor(params) {
        super(common_1.componentTypes.desktopList);
        // TODO check
        this.titleAreaText = params.titleAreaText;
        this.objectApiName = params.objectApiName;
        this.isCompositeType = params.isCompositeType;
        this.titleFields = params.titleFields;
        this.subtitleFields = params.subtitleFields;
        this.detailFields = params.detailFields;
        this.filter = params.filter;
        this.sortConditions = params.sortConditions;
    }
    static parse(input) {
        if (input.dataType === 'object') {
            return convertUIMetaListObject(input);
        }
        else if (input.dataType === 'compositeType') {
            return convertUIMetaListCompositeType(input);
        }
        return input;
    }
}
exports.List = List;
function convertUIMetaListObject(input) {
    return {
        isCompositeType: false,
        titleAreaText: input.titleLabel,
        objectApiName: input.objectApiName,
        titleFields: getListObjectTitleFields(input),
        subtitleFields: getListObjectSubtitleFields(input),
        detailFields: getListObjectDetailFields(input),
        filter: getListFilter(input),
        sortConditions: getListSort(input),
    };
}
function convertUIMetaListCompositeType(input) {
    return {
        isCompositeType: true,
        titleAreaText: input.titleLabel,
        objectApiName: getListCompositeTypeObjectApiName(input),
        titleFields: getListCompositeTypeTitleFields(input),
        subtitleFields: getListCompositeTypeSubtitleFields(input),
        detailFields: getListCompositeTypeDetailFields(input),
        filter: getListCompositeTypeFilter(input),
        sortConditions: getListSort(input),
    };
}
function getListObjectTitleFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.title)) {
        return [];
    }
    let titles = [];
    try {
        let inputTitles = JSON.parse(input.title);
        if (!inputTitles || !(inputTitles instanceof Array)) {
            return [];
        }
        for (let inputTitle of inputTitles) {
            titles.push({
                fieldApiName: inputTitle.columnApiName,
            });
        }
    }
    catch (err) {
        return [];
    }
    return titles;
}
function getListObjectSubtitleFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.subTitle)) {
        return [];
    }
    let subtitles = [];
    try {
        let inputSubtitles = JSON.parse(input.subTitle);
        if (!inputSubtitles || !Array.isArray(inputSubtitles)) {
            return [];
        }
        for (let inputSubtitle of inputSubtitles) {
            subtitles.push({
                fieldApiName: inputSubtitle.columnApiName,
                alias: inputSubtitle.alias,
            });
        }
    }
    catch (err) {
        return [];
    }
    return subtitles;
}
function getListObjectDetailFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.detail)) {
        return [];
    }
    let details = [];
    try {
        let inputDetails = JSON.parse(input.detail);
        if (!inputDetails || !Array.isArray(inputDetails)) {
            return [];
        }
        for (let inputDetail of inputDetails) {
            details.push({
                fieldApiName: inputDetail.columnApiName,
                alias: inputDetail.alias,
            });
        }
    }
    catch (err) {
        return [];
    }
    return details;
}
function getListFilter(input) {
    if (!input || !input.describeFilter || (0, common_2.isNullOrUndefined)(input.describeFilter.filter)) {
        return {};
    }
    try {
        let inputFilter = JSON.parse(input.describeFilter.filter);
        if (!inputFilter) {
            return {};
        }
        return {
            conditions: inputFilter.conditions,
            logic: inputFilter.logic,
        };
    }
    catch (err) {
        return {};
    }
}
function getListSort(input) {
    if (!input || !input.sort || !Array.isArray(input.sort)) {
        return [];
    }
    let sortFields = [];
    for (let field of input.sort) {
        sortFields.push({
            fieldApiName: field.field,
            sort: field.direction,
        });
    }
    return sortFields;
}
function getListCompositeTypeObjectApiName(input) {
    if ((0, common_2.isNullOrUndefined)(input)) {
        return '';
    }
    let objectApiName = getObjectApiNameFromTitle(input);
    if (objectApiName) {
        return objectApiName;
    }
    objectApiName = getObjectApiNameFromSubTitle(input);
    if (objectApiName) {
        return objectApiName;
    }
    objectApiName = getObjectApiNameFromDetail(input);
    if (objectApiName) {
        return objectApiName;
    }
    return '';
}
function getObjectApiNameFromTitle(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.title)) {
        return '';
    }
    try {
        return JSON.parse(input.title)[0].picker.fieldPath[0].objectApiName;
    }
    catch (err) {
        return '';
    }
}
function getObjectApiNameFromDetail(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.detail)) {
        return '';
    }
    try {
        return JSON.parse(input.detail)[0].picker.fieldPath[0].objectApiName;
    }
    catch (err) {
        return '';
    }
}
function getObjectApiNameFromSubTitle(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.subTitle)) {
        return '';
    }
    try {
        return JSON.parse(input.subTitle)[0].picker.fieldPath[0].objectApiName;
    }
    catch (err) {
        return '';
    }
}
function getListCompositeTypeTitleFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.title)) {
        return [];
    }
    let inputFields = [];
    try {
        let inputTitles = JSON.parse(input.title);
        if (!inputTitles || !(inputTitles instanceof Array)) {
            return [];
        }
        for (let title of inputTitles) {
            try {
                inputFields.push({
                    fieldApiName: title.picker.fieldPath[0].fieldApiName,
                });
            }
            catch (e) {
                continue;
            }
        }
    }
    catch (err) {
        return [];
    }
    return inputFields;
}
function parsePrimitive(element) {
    try {
        return {
            type: 'field',
            fieldApiName: element.picker.fieldPath[0].fieldApiName,
            alias: [],
            concatText: {
                zh_CN: [],
                en_US: [],
            }
        };
    }
    catch (e) {
        return null;
    }
}
function getListCompositeTypeSubtitleFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.subTitle)) {
        return [];
    }
    let fields = [], subTitle;
    try {
        subTitle = JSON.parse(input.subTitle);
    }
    catch (err) {
        return [];
    }
    if (!subTitle || !Array.isArray(subTitle)) {
        return [];
    }
    for (let element of subTitle) {
        let field = null;
        if (element.type === 'primitive') {
            field = parsePrimitive(element);
        }
        else if (element.type === 'concatenate') {
            field = parseConcatenate(element);
        }
        if (field) {
            fields.push(field);
        }
    }
    return fields;
}
function getListCompositeTypeDetailFields(input) {
    if (!input || (0, common_2.isNullOrUndefined)(input.detail)) {
        return [];
    }
    let fields = [];
    try {
        let detail = JSON.parse(input.detail);
        if (!detail || !(detail instanceof Array)) {
            return [];
        }
        for (let element of detail) {
            try {
                fields.push({
                    fieldApiName: element.picker.fieldPath[0].fieldApiName,
                    alias: [], // TODO
                });
            }
            catch (e) {
                continue;
            }
        }
    }
    catch (err) {
        return [];
    }
    return fields;
}
function getListCompositeTypeFilter(input) {
    if (!input || !input.describeFilter || (0, common_2.isNullOrUndefined)(input.describeFilter.filter)) {
        return {};
    }
    try {
        let inputFilter = JSON.parse(input.describeFilter.filter);
        if (!inputFilter) {
            return {};
        }
        return {
            conditions: inputFilter.conditions,
            logic: inputFilter.logic,
        };
    }
    catch (err) {
        return {};
    }
}
function parseLangValues(values) {
    let lang = [];
    for (let value of values) {
        if (value.type === 'text') {
            lang.push({
                dataType: 'text',
                fieldApiName: '',
                text: value.value,
            });
        }
        else if (value.type === 'field') {
            if (value && value.picker && commonUtils.getArrayLength(value.picker.fieldPath) > 0
                && value.picker.fieldPath[0].fieldApiName) {
                lang.push({
                    dataType: 'fieldApiName',
                    fieldApiName: value.picker.fieldPath[0].fieldApiName,
                    text: '',
                });
            }
        }
    }
    return lang;
}
function parseConcatenate(element) {
    if (!element || (0, common_2.isNullOrUndefined)(element.content)) {
        return null;
    }
    let concatEle = {
        type: 'concatText',
        fieldApiName: '',
        alias: [],
        concatText: {
            zh_CN: [],
            en_US: [],
        }
    };
    for (let code of Object.keys(element.content)) {
        let values = element.content[code];
        if (code === '2052') {
            concatEle.concatText.zh_CN = parseLangValues(values);
        }
        else if (code === '1033') {
            concatEle.concatText.en_US = parseLangValues(values);
        }
    }
    if (commonUtils.getArrayLength(concatEle.concatText.zh_CN) > 0 ||
        commonUtils.getArrayLength(concatEle.concatText.en_US) > 0) {
        return concatEle;
    }
    return null;
}
