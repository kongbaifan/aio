"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.SDKVersion = exports.SDKName = void 0;
const packageJson = require('.././package.json');
exports.SDKName = packageJson.name;
exports.SDKVersion = packageJson.version;
