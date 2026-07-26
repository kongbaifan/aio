"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.p = void 0;
exports.p = new Proxy({}, {
    get(target, key) {
        target[key] = target[key] || Symbol(key);
        return target[key];
    }
});
