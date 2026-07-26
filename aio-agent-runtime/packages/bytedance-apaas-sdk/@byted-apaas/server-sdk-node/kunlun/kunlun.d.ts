import { IOperator } from './operator/IOperator';
import { GMTOffset as GMT } from '@byted-apaas/server-common-node/constants/timeZone';
import { area2code } from '@byted-apaas/server-common-node/constants/countryCode';
import { ITool, IToolsExtra } from '@byted-apaas/server-common-node/kunlun/tool/Itool';
import { errCodes } from '@byted-apaas/server-common-node/utils/exceptions';
import * as common from '@byted-apaas/server-common-node';
declare global {
    export namespace kunlun {
        /**
         * 指令操作符
         */
        let operator: IOperator;
    }
}
export declare namespace kunlun {
    /**
     * 引用时区信息
     */
    const GMTOffset: typeof GMT;
    /**
     * 引用国际区号
     */
    const countryCode: typeof area2code;
    /**
     * 工具方法
     */
    let tool: ITool & IToolsExtra;
    /**
     * 生成复杂数据结构
     */
    namespace type {
        export import Multilingual = common.fieldType.Multilingual;
        export import Phone = common.fieldType.Phone;
        export import Date = common.fieldType.Date;
        export import DateTime = common.fieldType.DateTime;
    }
    /**
     * 错误码
     */
    const errorCode: {
        /**
         * 限流错误码
         */
        RATE_LIMIT_ERROR: errCodes;
    };
    /**
     * 根据 key 获取对应的全局变量
     * @param key 全局变量的 key
     */
    function getVar(key: string): Promise<string>;
    /**
     * 指令操作符
     */
    const operator: IOperator;
}
