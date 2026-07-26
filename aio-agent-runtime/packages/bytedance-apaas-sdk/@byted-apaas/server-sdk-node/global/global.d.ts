import { IOperator } from '../kunlun/operator/IOperator';
import { GMTOffset as GMT } from '@byted-apaas/server-common-node/constants/timeZone';
import { area2code } from '@byted-apaas/server-common-node/constants/countryCode';
import * as common from '@byted-apaas/server-common-node';
import { Flow } from './application/flow/flow';
import { _Resources } from '../context/resources/impl/resources';
import { Message } from '../context/msg/msg';
import { _IIntegration } from '../context/integration/IIntegration';
declare global {
    export namespace application {
        /**
         * 操作 flow
         */
        let flow: Flow;
        /**
         * 静态资源类操作
         */
        let resources: _Resources;
        /**
         * 向消息中心推送及更新消息
         */
        let msg: Message;
        /**
         * 指令操作符
         */
        let operator: IOperator;
        /**
         * dataV3 接口
         */
        /**
         * metadataV3 接口
         */
        /**
         * 常量
         */
        namespace constants {
            /**
             * 引用时区信息
             */
            let GMTOffset: typeof GMT;
            /**
             * 引用国际区号
             */
            let countryCode: typeof area2code;
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
            /**
             * 生成复杂数据结构
             */
            namespace type {
                export import Multilingual = common.fieldType.Multilingual;
                export import Phone = common.fieldType.Phone;
                export import Date = common.fieldType.Date;
                export import DateTime = common.fieldType.DateTime;
            }
        }
        const integration: _IIntegration;
    }
}
