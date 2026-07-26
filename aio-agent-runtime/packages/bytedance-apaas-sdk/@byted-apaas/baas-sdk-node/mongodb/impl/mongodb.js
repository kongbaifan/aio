"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Mongodb = void 0;
const table_1 = require("./table");
const condition_1 = require("./condition");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const bson = require('bson'); //nolint:byted_s_ts_no_require_imports
class Mongodb {
    constructor() {
        this.ObjectId = bson.ObjectId;
    }
    ObjectId(_id) { }
    table(tableName) {
        return new table_1.Table(tableName);
    }
    and(...data) {
        return new condition_1.Condition().and(...data);
    }
    or(...data) {
        return new condition_1.Condition().or(...data);
    }
    nor(...data) {
        return new condition_1.Condition().nor(...data);
    }
    mod(data) {
        return new condition_1.Condition().mod(data);
    }
    eq(data) {
        return new condition_1.Condition().eq(data);
    }
    ne(data) {
        return new condition_1.Condition().ne(data);
    }
    gt(data) {
        return new condition_1.Condition().gt(data);
    }
    gte(data) {
        return new condition_1.Condition().gte(data);
    }
    lt(data) {
        return new condition_1.Condition().lt(data);
    }
    lte(data) {
        return new condition_1.Condition().lte(data);
    }
    in(data) {
        return new condition_1.Condition().in(data);
    }
    nin(data) {
        return new condition_1.Condition().nin(data);
    }
    not(data) {
        return new condition_1.Condition().not(data);
    }
    exists(data) {
        return new condition_1.Condition().exists(data);
    }
    regex(data) {
        return new condition_1.Condition().regex(data);
    }
    all(data) {
        return new condition_1.Condition().all(data);
    }
    elemMatch(data) {
        return new condition_1.Condition().elemMatch(data);
    }
    size(data) {
        return new condition_1.Condition().size(data);
    }
    bitsAllClear(data) {
        return new condition_1.Condition().bitsAllClear(data);
    }
    bitsAllSet(data) {
        return new condition_1.Condition().bitsAllSet(data);
    }
    bitsAnyClear(data) {
        return new condition_1.Condition().bitsAnyClear(data);
    }
    bitsAnySet(data) {
        return new condition_1.Condition().bitsAnySet(data);
    }
    geoIntersects(data) {
        return new condition_1.Condition().geoIntersects(data);
    }
    geoWithin(data) {
        return new condition_1.Condition().geoWithin(data);
    }
    near(data) {
        return new condition_1.Condition().near(data);
    }
    nearSphere(data) {
        return new condition_1.Condition().nearSphere(data);
    }
    literal(data) {
        return new condition_1.Condition().literal(data);
    }
    abs(data) {
        return new condition_1.Condition().abs(data);
    }
    add(data) {
        return new condition_1.Condition().add(data);
    }
    ceil(data) {
        return new condition_1.Condition().ceil(data);
    }
    divide(data) {
        return new condition_1.Condition().divide(data);
    }
    exp(data) {
        return new condition_1.Condition().exp(data);
    }
    floor(data) {
        return new condition_1.Condition().floor(data);
    }
    ln(data) {
        return new condition_1.Condition().ln(data);
    }
    log(data) {
        return new condition_1.Condition().log(data);
    }
    log10(data) {
        return new condition_1.Condition().log10(data);
    }
    multiply(data) {
        return new condition_1.Condition().multiply(data);
    }
    pow(data) {
        return new condition_1.Condition().pow(data);
    }
    round(data) {
        return new condition_1.Condition().round(data);
    }
    sqrt(data) {
        return new condition_1.Condition().sqrt(data);
    }
    subtract(data) {
        return new condition_1.Condition().subtract(data);
    }
    cmp(data) {
        return new condition_1.Condition().cmp(data);
    }
    cond(data) {
        return new condition_1.Condition().cond(data);
    }
    ifNull(data) {
        return new condition_1.Condition().ifNull(data);
    }
    switch(data) {
        return new condition_1.Condition().switch(data);
    }
    dayOfMonth(data) {
        return new condition_1.Condition().dayOfMonth(data);
    }
    dayOfWeek(data) {
        return new condition_1.Condition().dayOfWeek(data);
    }
    dayOfYear(data) {
        return new condition_1.Condition().dayOfYear(data);
    }
    hour(data) {
        return new condition_1.Condition().hour(data);
    }
    millisecond(data) {
        return new condition_1.Condition().millisecond(data);
    }
    minute(data) {
        return new condition_1.Condition().minute(data);
    }
    month(data) {
        return new condition_1.Condition().month(data);
    }
    second(data) {
        return new condition_1.Condition().second(data);
    }
    week(data) {
        return new condition_1.Condition().week(data);
    }
    year(data) {
        return new condition_1.Condition().year(data);
    }
    concat(data) {
        return new condition_1.Condition().concat(data);
    }
    dateFromString(data) {
        return new condition_1.Condition().dateFromString(data);
    }
    dateToString(data) {
        return new condition_1.Condition().dateToString(data);
    }
    indexOfBytes(data) {
        return new condition_1.Condition().indexOfBytes(data);
    }
    indexOfCP(data) {
        return new condition_1.Condition().indexOfCP(data);
    }
    ltrim(data) {
        return new condition_1.Condition().ltrim(data);
    }
    rtrim(data) {
        return new condition_1.Condition().rtrim(data);
    }
    split(data) {
        return new condition_1.Condition().split(data);
    }
    strLenBytes(data) {
        return new condition_1.Condition().strLenBytes(data);
    }
    strLenCP(data) {
        return new condition_1.Condition().strLenCP(data);
    }
    strcasecmp(data) {
        return new condition_1.Condition().strcasecmp(data);
    }
    substrBytes(data) {
        return new condition_1.Condition().substrBytes(data);
    }
    substrCP(data) {
        return new condition_1.Condition().substrCP(data);
    }
    toLower(data) {
        return new condition_1.Condition().toLower(data);
    }
    toString(data) {
        return new condition_1.Condition().toString(data);
    }
    toUpper(data) {
        return new condition_1.Condition().toUpper(data);
    }
    trim(data) {
        return new condition_1.Condition().trim(data);
    }
}
exports.Mongodb = Mongodb;
