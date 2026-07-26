import * as common from '@byted-apaas/server-common-node';
import Multilingual = common.fieldType.Multilingual;
export type _IconType = 'success' | 'error' | 'progress' | 'info';
export declare class _NotifyCenter {
    /**
     * 消息中心推送消息
     * @param msg 消息
     */
    create(msg: {
        icon: _IconType;
        percent: Number;
        target_users: number[];
        title: Multilingual;
        detail: Multilingual;
    }): Promise<number>;
    /**
     * 消息中心更新消息
     * @param msgId 消息 ID
     * @param msg 消息
     */
    update(msgId: number, msg: {
        icon?: _IconType;
        percent?: Number;
        target_users?: number[];
        title?: Multilingual;
        detail?: Multilingual;
    }): Promise<void>;
}
/**
 * 消息类
 */
export declare class Message {
    /**
     * 消息中心
     */
    notifyCenter: _NotifyCenter;
    constructor();
}
