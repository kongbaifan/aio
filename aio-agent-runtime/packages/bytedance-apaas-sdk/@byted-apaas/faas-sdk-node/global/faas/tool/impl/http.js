"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Http = void 0;
const common = require("@byted-apaas/server-common-node");
const got_1 = require("got");
const url_1 = require("url");
const FormData = require("form-data");
const stream_1 = require("stream");
const { InvalidParamError } = common.exceptions;
const { checkRequiredParam, checkTypeOfParams, isHttpConnectError, printErrorLog, replaceErrorStack, } = common.utils;
const { netApi, TypeofValue } = common.constants;
function checkHttpParam(request, options) {
    if (request.method) {
        const tmpMethod = request.method.toUpperCase();
        if (!netApi.HttpMethods.includes(tmpMethod)) {
            throw new InvalidParamError('method is not correct for HttpMethod');
        }
        options.method = tmpMethod;
    }
    if (request.headers) {
        checkTypeOfParams('headers', [TypeofValue.object], request.headers, false);
        options.headers = request.headers;
    }
    if (request.query) {
        checkTypeOfParams('query', [TypeofValue.string, TypeofValue.object], request.query, false);
        options.searchParams = request.query;
    }
    if (request.body) {
        if (typeof request.body === 'string') {
            options.body = request.body;
        }
        else if (request.body instanceof Buffer || request.body instanceof FormData || request.body instanceof stream_1.Readable) { // Buffer、 form-data 和 Readable
            options.body = request.body;
        }
        else if (typeof request.body === 'object') { // json 类型
            options.json = request.body;
        }
        else {
            throw new InvalidParamError('body is not string, Object, Buffer or Readable');
        }
    }
    if (request.responseType) {
        checkTypeOfParams('responseType', [TypeofValue.string], request.responseType, false);
        if (!netApi.ResponseTypes.includes(request.responseType)) {
            throw new InvalidParamError('responseType is not "text" or "json" or "buffer"');
        }
        options.responseType = request.responseType;
    }
    if (request.encoding) {
        checkTypeOfParams('encoding', [TypeofValue.string], request.encoding, false);
        options.encoding = request.encoding;
    }
}
/**
 * Http 请求类
 */
// eslint-disable-next-line unicorn/no-static-only-class,@typescript-eslint/no-extraneous-class
class Http {
    static async httpTool(request) {
        checkRequiredParam('request', request);
        const options = {};
        checkRequiredParam('url', request.url);
        if (typeof request.url !== 'string' && !(request.url instanceof url_1.URL)) {
            throw new InvalidParamError('url is neither string nor URL');
        }
        options.url = request.url;
        checkHttpParam(request, options);
        // 默认连接层重试兜底 2000ms
        options.timeout = {
            connect: netApi.ConnectTimeout,
            secureConnect: netApi.SecureConnectTimeout,
        };
        if (request.timeout) {
            checkTypeOfParams('timeout', [TypeofValue.number], request.timeout, false);
            options.timeout.request = request.timeout;
        }
        // 取消 got 的默认重试
        options.retry = 0;
        // 非 200&300 状态码，不抛异常
        options.throwHttpErrors = false;
        const response = await Http.requestWithHttpConnRetry(options);
        return await Http.getHttpResponse(response);
    }
    static async requestWithHttpConnRetry(options, retryTimes = 2) {
        let times = 0, res = null;
        do {
            try {
                res = await (0, got_1.default)(options);
                return res;
            }
            catch (err) {
                printErrorLog(`netAPI request throw err times: ${times} time: ${new Date().getTime()}, err: ${err}`);
                if (times >= retryTimes || !isHttpConnectError(err)) {
                    // 抛 Error 时，替换 GotError 不暴露 sdk 内部使用 http 库
                    replaceErrorStack(err, 'GotError', 'HttpError');
                    throw err;
                }
            }
        } while (times++ <= retryTimes);
        return res;
    }
    static async getHttpResponse(response) {
        const res = {};
        res.statusCode = response.statusCode;
        res.headers = response.headers;
        res.body = response.body;
        return res;
    }
}
exports.Http = Http;
