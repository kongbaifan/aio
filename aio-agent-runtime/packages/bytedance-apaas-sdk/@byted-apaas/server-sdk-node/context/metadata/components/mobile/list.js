"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.List = void 0;
const common_1 = require("../../types/common");
const common_2 = require("../common");
/*
titleAreaText: i18n;
objectApiName: string;
listItems: {
    avatar: {
        active: boolean;
        fieldApiName: string;
    },
    titleFields: [{
        fieldApiName: string;
    },...]
    tagFields: [{
        fieldApiName: string;
        color: 'grey'|'blue'|'cyan'|'green'|'yellow'|'orange'|'red'|'magenta'|'purple'|'blueMagenta';
    },...]
    subtitleFields: [{
        fieldApiName: string;
        hiddenWhenEmpty: boolean;
    },...],
    detailFields: [{
        fieldApiName: string;
        hiddenWhenEmpty: boolean;
    },...]
};
filter: {
    conditions: object[];
    logic: string;
};
sortConditions: object[];
 */
class List extends common_2.Component {
    constructor(params) {
        super(common_2.componentTypes.mobileList);
        // TODO prd缺少
        this.pageApiName = params.pageApiName;
        this.componentName = params.componentName;
        this.pageType = params.pageType; // app | record_page
        this.needPublish = true;
        // TODO check params
        this.titleAreaText = params.titleAreaText;
        this.objectApiName = params.objectApiName;
        this.listItems = params.listItems;
        this.filter = params.filter;
        this.sortConditions = params.sortConditions;
    }
    static parse(input) {
        return {
            pageApiName: input.appApiName,
            componentName: input.componentName,
            titleAreaText: [],
            objectApiName: input.objectApiName,
            listItems: {
                avatar: {},
                titleFields: [],
                tagFields: [],
                subtitleFields: [],
                detailFields: getDetailFields(input),
            },
            filter: getFilter(input),
            sortConditions: [], // TODO 下游缺少
        };
    }
    getReqParam() {
        let reqParam = {
            appApiName: this.pageApiName,
            componentName: this.componentName,
            objectApiName: this.objectApiName,
            tableColumn: this.getTableColumn(),
            describeFilter: this.getDescribeFilter(),
            pageType: this.pageType,
            needPublish: this.needPublish,
        };
        if (this.getDescribeFilter()) {
            reqParam.describeFilter = this.getDescribeFilter();
        }
        if (this.pageType) {
            reqParam.pageType = this.pageType;
        }
        if (this.needPublish) {
            reqParam.needPublish = this.needPublish;
        }
        return reqParam;
    }
    getTableColumn() {
        if (!this.listItems || !this.listItems.detailFields || !Array.isArray(this.listItems.detailFields)) {
            return [];
        }
        let values = [];
        for (let detailField of this.listItems.detailFields) {
            if (!detailField || !detailField.fieldApiName) {
                continue;
            }
            values.push({ apiName: detailField.fieldApiName });
        }
        return values;
    }
    getDescribeFilter() {
        if ((0, common_1.isNullOrUndefined)(this.filter)) {
            return null;
        }
        try {
            return { filter: JSON.stringify(this.filter) };
        }
        catch (e) {
            // TODO 抛出业务错误
            return null;
        }
    }
}
exports.List = List;
function getDetailFields(input) {
    if (!input || !input.tableColumn || !Array.isArray(input.tableColumn)) {
        return [];
    }
    let values = [];
    for (let col of input.tableColumn) {
        if (!col || !col.apiName) {
            continue;
        }
        values.push({ fieldApiName: col.apiName });
    }
    return values;
}
function getFilter(input) {
    if (!input || !input.describeFilter || (0, common_1.isNullOrUndefined)(input.describeFilter.filter)) {
        return {};
    }
    try {
        let inputFilter = JSON.parse(input.describeFilter.filter);
        return {
            conditions: inputFilter.conditions,
            logic: inputFilter.logic,
        };
    }
    catch (err) {
        return {};
    }
}
