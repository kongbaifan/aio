"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.componentTypes = exports.Component = void 0;
const componentTypes = {
    desktopList: 'desktopList',
    desktopRecordDetail: 'desktopRecordDetail',
    mobileList: 'mobileList',
};
exports.componentTypes = componentTypes;
class Component {
    constructor(type) {
        this.type = type;
    }
}
exports.Component = Component;
