"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.transI18nsToMultilingualV3 = exports.isNullOrUndefined = void 0;
function isNullOrUndefined(param) {
    return param === null || param === undefined;
}
exports.isNullOrUndefined = isNullOrUndefined;
function transI18nsToMultilingualV3(i18ns) {
    if (i18ns === null || i18ns === undefined) {
        return null;
    }
    let multilingual = { zh_CN: '', en_US: '' };
    for (const i18n of i18ns) {
        switch (i18n.language_code) {
            case languageCode.zh_CN:
                multilingual.zh_CN = i18n.text;
                break;
            case languageCode.en_US:
                multilingual.en_US = i18n.text;
                break;
            default:
                break;
        }
    }
    return multilingual;
}
exports.transI18nsToMultilingualV3 = transI18nsToMultilingualV3;
const languageCode = {
    zh_CN: 2052,
    en_US: 1033,
};
