"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.kunlun = void 0;
const fieldType = require("./type/type");
function getErrCodes() {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('../utils/exceptions').errCodes;
}
var kunlun;
(function (kunlun) {
    /**
     * 生成复杂数据结构
     */
    let type;
    (function (type) {
        type.Multilingual = fieldType.Multilingual;
        type.Phone = fieldType.Phone;
        type.Date = fieldType.Date;
        type.DateTime = fieldType.DateTime;
    })(type = kunlun.type || (kunlun.type = {}));
    /**
     * 错误码
     */
    kunlun.errorCode = {
        // 限流错误码
        RATE_LIMIT_ERROR: getErrCodes().OPENAPI_RATE_LIMIT_ERROR,
        //  无权限操作流程
        Flows_NoPermission: getErrCodes().Flows_NoPermission,
        // 流程不存在
        Flows_NotExist: getErrCodes().Flows_NotExist,
        //  流程实例 ID 不存在
        Flows_ExecutionNotExist: getErrCodes().Flows_ExecutionNotExist,
        //  不支持调用此类型流程
        Flows_NotSupportCallFlowType: getErrCodes().Flows_NotSupportCallFlowType,
        //  不支持撤销该流程 (无人工任务)
        Flows_NotSupportRevokeFlow: getErrCodes().Flows_NotSupportRevokeFlow,
        //  缺少流程的必填参数
        Flows_NoReqInputParamErr: getErrCodes().Flows_NoReqInputParamErr,
        //  流程参数中 APIName 无效
        Flows_InvalidParamErr: getErrCodes().Flows_InvalidParamErr,
    };
})(kunlun = exports.kunlun || (exports.kunlun = {}));
