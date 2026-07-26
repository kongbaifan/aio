"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Http = void 0;
const exceptions_1 = require("../../../utils/exceptions");
const got_1 = require("got");
const url_1 = require("url");
const utils_1 = require("../../../utils/utils");
const constants_1 = require("../../../constants/constants");
// eslint-disable-next-line @typescript-eslint/no-require-imports
// @ts-ignore
const FormData = require("form-data"); //nolint:byted_s_ts_no_require_imports
const stream_1 = require("stream");
/**
 * Http 请求类
 */
class Http {
    static async httpTool(request) {
        (0, utils_1.checkRequiredParam)('request', request);
        let options = {};
        (0, utils_1.checkRequiredParam)('url', request.url);
        if (typeof request.url !== 'string' && !(request.url instanceof url_1.URL)) {
            throw new exceptions_1.InvalidParamError(`url is neither string nor URL`);
        }
        options.url = request.url;
        if (request.method) {
            let tmpMethod = request.method.toUpperCase();
            if (!constants_1.netApi.HttpMethods.includes(tmpMethod)) {
                throw new exceptions_1.InvalidParamError(`method is not correct for HttpMethod`);
            }
            options.method = tmpMethod;
        }
        if (request.headers) {
            (0, utils_1.checkTypeOfParams)('headers', [constants_1.TypeofValue.object], request.headers, false);
            options.headers = request.headers;
        }
        if (request.query) {
            (0, utils_1.checkTypeOfParams)('query', [constants_1.TypeofValue.string, constants_1.TypeofValue.object], request.query, false);
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
                throw new exceptions_1.InvalidParamError(`body is not string, Object, Buffer or Readable`);
            }
        }
        if (request.responseType) {
            (0, utils_1.checkTypeOfParams)('responseType', [constants_1.TypeofValue.string], request.responseType, false);
            if (!constants_1.netApi.ResponseTypes.includes(request.responseType)) {
                throw new exceptions_1.InvalidParamError(`responseType is not 'text' or 'json' or 'buffer'`);
            }
            options.responseType = request.responseType;
        }
        if (request.encoding) {
            (0, utils_1.checkTypeOfParams)('encoding', [constants_1.TypeofValue.string], request.encoding, false);
            options.encoding = request.encoding;
        }
        // 默认连接层重试兜底 2000ms
        options.timeout = {
            connect: constants_1.netApi.ConnectTimeout,
            secureConnect: constants_1.netApi.SecureConnectTimeout,
        };
        if (request.timeout) {
            (0, utils_1.checkTypeOfParams)('timeout', [constants_1.TypeofValue.number], request.timeout, false);
            options.timeout.request = request.timeout;
        }
        // 取消 got 的默认重试
        options.retry = 0;
        // 非 200&300 状态码，不抛异常
        options.throwHttpErrors = false;
        let response = await Http.requestWithHttpConnRetry(options);
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
                (0, utils_1.printErrorLog)(`netAPI request throw err times: ${times} time: ${new Date().getTime()}, err: ${err}`);
                if (times >= retryTimes || !(0, utils_1.isHttpConnectError)(err)) {
                    // 抛 Error 时，替换 GotError 不暴露 sdk 内部使用 http 库
                    (0, utils_1.replaceErrorStack)(err, 'GotError', 'HttpError');
                    throw err;
                }
            }
        } while (times++ <= retryTimes);
        return res;
    }
    static async getHttpResponse(response) {
        let res = {};
        res.statusCode = response.statusCode;
        res.headers = response.headers;
        res.body = response.body;
        return res;
    }
}
exports.Http = Http;
