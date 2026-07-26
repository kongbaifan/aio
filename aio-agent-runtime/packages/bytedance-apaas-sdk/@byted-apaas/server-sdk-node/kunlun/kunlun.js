"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.kunlun = void 0;
const timeZone_1 = require("@byted-apaas/server-common-node/constants/timeZone");
const countryCode_1 = require("@byted-apaas/server-common-node/constants/countryCode");
const tool_1 = require("@byted-apaas/server-common-node/kunlun/tool/impl/tool");
const exceptions_1 = require("@byted-apaas/server-common-node/utils/exceptions");
const operator_1 = require("./operator/impl/operator");
const common = require("@byted-apaas/server-common-node");
const Request = require("../request/interface");
var kunlun;
(function (kunlun) {
    /**
     * 引用时区信息
     */
    kunlun.GMTOffset = timeZone_1.GMTOffset;
    /**
     * 引用国际区号
     */
    kunlun.countryCode = countryCode_1.area2code;
    /**
     * 工具方法
     */
    kunlun.tool = new tool_1.Tool();
    /**
     * 生成复杂数据结构
     */
    let type;
    (function (type) {
        type.Multilingual = common.fieldType.Multilingual;
        type.Phone = common.fieldType.Phone;
        type.Date = common.fieldType.Date;
        type.DateTime = common.fieldType.DateTime;
    })(type = kunlun.type || (kunlun.type = {}));
    /**
     * 错误码
     */
    kunlun.errorCode = {
        /**
         * 限流错误码
         */
        RATE_LIMIT_ERROR: exceptions_1.errCodes.RATE_LIMIT_ERROR,
    };
    /**
     * 根据 key 获取对应的全局变量
     * @param key 全局变量的 key
     */
    async function getVar(key) {
        return await Request.GetInstance().getGlobalConfigByKey(key);
    }
    kunlun.getVar = getVar;
    /**
     * 指令操作符
     */
    kunlun.operator = new operator_1.Operator();
})(kunlun = exports.kunlun || (exports.kunlun = {}));
