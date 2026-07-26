"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Message = exports._NotifyCenter = void 0;
const Request = require("../../request/interface");
class _NotifyCenter {
    /**
     * 消息中心推送消息
     * @param msg 消息
     */
    async create(msg) {
        return await Request.GetInstance().createMessage(msg);
    }
    ;
    /**
     * 消息中心更新消息
     * @param msgId 消息 ID
     * @param msg 消息
     */
    async update(msgId, msg) {
        return await Request.GetInstance().updateMessage(msgId, msg);
    }
    ;
}
exports._NotifyCenter = _NotifyCenter;
/**
 * 消息类
 */
class Message {
    constructor() {
        this.notifyCenter = new _NotifyCenter();
    }
}
exports.Message = Message;
