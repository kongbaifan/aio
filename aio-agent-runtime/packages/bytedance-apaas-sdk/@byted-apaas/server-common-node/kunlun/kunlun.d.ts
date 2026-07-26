import { GMTOffset as GMT } from '../constants/timeZone';
import { area2code } from '../constants/countryCode';
import { MongoDB } from './mongodb/mongodb';
import { Redis } from './redis/redis';
import { ITool } from './tool/Itool';
import * as fieldType from './type/type';
declare global {
    export namespace kunlun {
        /**
         * 引用时区信息
         */
        const GMTOffset: typeof GMT;
        /**
         * 引用国际区号
         */
        const countryCode: typeof area2code;
        /**
         * 调用 mongodb
         */
        let mongodb: MongoDB;
        /**
         * 调用 redis
         */
        let redis: Redis;
        /**
         * 工具方法
         */
        let tool: ITool;
        /**
         * 生成复杂数据结构
         */
        namespace type {
            export import Multilingual = fieldType.Multilingual;
            export import Phone = fieldType.Phone;
            export import Date = fieldType.Date;
            export import DateTime = fieldType.DateTime;
        }
        /**
         * 错误码
         */
        const errorCode: {
            RATE_LIMIT_ERROR: string;
            Flows_NoPermission: string;
            Flows_NotExist: string;
            Flows_ExecutionNotExist: string;
            Flows_NotSupportCallFlowType: string;
            Flows_NotSupportRevokeFlow: string;
            Flows_NoReqInputParamErr: string;
            Flows_InvalidParamErr: string;
        };
    }
}
export declare namespace kunlun {
    /**
     * 生成复杂数据结构
     */
    namespace type {
        export import Multilingual = fieldType.Multilingual;
        export import Phone = fieldType.Phone;
        export import Date = fieldType.Date;
        export import DateTime = fieldType.DateTime;
    }
    /**
     * 错误码
     */
    const errorCode: {
        RATE_LIMIT_ERROR: any;
        Flows_NoPermission: any;
        Flows_NotExist: any;
        Flows_ExecutionNotExist: any;
        Flows_NotSupportCallFlowType: any;
        Flows_NotSupportRevokeFlow: any;
        Flows_NoReqInputParamErr: any;
        Flows_InvalidParamErr: any;
    };
}
