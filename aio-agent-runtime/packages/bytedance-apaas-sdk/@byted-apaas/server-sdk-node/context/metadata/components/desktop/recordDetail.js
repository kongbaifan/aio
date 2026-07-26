"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.RecordDetail = void 0;
const common_1 = require("../common");
/*
titleAreaText: i18n;
objectApiName: string;
selectedFields: [{
    fieldPath: [{
        objectApiName: string;
        fieldApiName: string;
    }, ...];
},...]
 */
class RecordDetail extends common_1.Component {
    constructor(params) {
        super(common_1.componentTypes.desktopRecordDetail);
        // TODO check
        this.titleAreaText = params.titleAreaText;
        this.objectApiName = params.objectApiName;
        this.selectedFields = params.selectedFields;
    }
    static parse(input) {
        return new RecordDetail({
            titleAreaText: input.titleLabel,
            objectApiName: input.objectApiName,
            selectedFields: getSelectedFields(input),
        });
    }
}
exports.RecordDetail = RecordDetail;
function getSelectedFields(input) {
    if (!input || !input.selectedFields || !Array.isArray(input.selectedFields)) {
        return [];
    }
    let selectedFields = [];
    for (let selectedField of input.selectedFields) {
        if (!selectedField || !selectedField.picker || !selectedField.picker.fieldPath) {
            continue;
        }
        let fieldPath = [];
        for (let field of selectedField.picker.fieldPath) {
            fieldPath.push({
                objectApiName: field.objectApiName,
                fieldApiName: field.fieldApiName,
            });
        }
        selectedFields.push({ fieldPath: fieldPath });
    }
    return selectedFields;
}
