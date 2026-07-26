"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.User = void 0;
const common_1 = require("../../lib/common");
const openapi_1 = require("../../http/openapi");
class User {
    async getLocale(userIdOrList) {
        if (!userIdOrList) {
            throw new common_1.exceptions.InvalidParamError('userID or userIDList is empty. ');
        }
        let reqUserIDList = [];
        let isMultiGet = false;
        // 多个 UserID 的情况
        if (Array.isArray(userIdOrList)) {
            isMultiGet = true;
            if (userIdOrList.length > 200) {
                throw new common_1.exceptions.InvalidParamError('userIDList cannot longger than 200. ');
            }
            userIdOrList.forEach((userID) => {
                // 传递的 UserID List 中包含了非法的 ID
                if (!userID) {
                    throw new common_1.exceptions.InvalidParamError('userIDList contain invalid userID: ' + userID);
                }
                reqUserIDList.push(userID);
            });
        }
        else {
            reqUserIDList.push(userIdOrList);
        }
        // 组合好请求参数之后，请求 openAPI 获取结果
        let result = await (0, openapi_1.mGetUserLocaleInfo)(reqUserIDList);
        // result type is LocaleWithUID[]
        if (!isMultiGet) {
            // 如果不是 multiGet，则只返回其中第一个元素
            if (result.length >= 1) {
                return result[0];
            }
        }
        return result;
    }
    constructor(_id, locale) {
        this._id = Number(_id);
        this.initiator = {
            _locale: locale
        };
    }
}
exports.User = User;
