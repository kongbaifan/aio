"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
class PropertiesStore {
    constructor() {
        this.map = new WeakMap();
    }
    properties(obj) {
        const properties = this.get(obj);
        if (!properties) {
            throw Error('Properties store error. ');
        }
        return properties;
    }
    get(key) {
        return this.map.get(key);
    }
    set(key, value) {
        return this.map.set(key, value);
    }
    has(key) {
        return this.map.has(key);
    }
    delete(key) {
        return this.map.delete(key);
    }
}
exports.default = PropertiesStore;
