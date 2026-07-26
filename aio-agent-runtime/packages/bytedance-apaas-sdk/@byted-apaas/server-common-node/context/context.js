"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Context = void 0;
const workflowImpl_1 = require("./workflow/workflowImpl/workflowImpl");
const utils = require("../utils/utils");
class Context {
    constructor(ctx, tenant, app, user, event, method) {
        this.tenant = tenant;
        this.app = app;
        this.user = user;
        this.event = event;
        if (method) {
            this.method = method;
        }
        if (ctx) {
            if (ctx.initiator) {
                let initiator = ctx.initiator;
                if (utils.isDebug() && !ctx.initiator) {
                    // 针对调试：调试参数面板修改了结构，initiator 从 ctx.user 下才能取到
                    initiator = ctx.user.initiator;
                }
                // context.initiator 在 locale 需求后被迁移到 context.user.initiator, 为了兼容而保留
                this.initiator = initiator;
                // context.user.initiator 由上游传递的 user 的 locale 信息和 ctx 中的用户其他字段组合而成，冲突字段以 ctx 为准
                this.user.initiator = {
                    ...user.initiator,
                    ...initiator,
                };
                // 防止 initiator 被篡改
                Object.freeze(this.initiator);
                Object.freeze(this.user.initiator);
            }
            if (ctx.headers) {
                this.headers = ctx.headers;
            }
            if (ctx.targetRecord) {
                this.targetRecord = ctx.targetRecord;
            }
            if (ctx.objectApiName) {
                this.objectApiName = ctx.objectApiName;
            }
            this.workflow = new workflowImpl_1.WorkflowImpl(ctx.flow, ctx.workflow);
            this.flow = new workflowImpl_1.Flow(ctx.flow, ctx.workflow);
            if (utils.isDebug()) {
                this.trigger = ctx.trigger;
            }
            else {
                this.trigger = {
                    'new': (this.workflow && this.workflow.variables && this.workflow.variables._triggerRecord) || {},
                    'old': (this.workflow && this.workflow.variables && this.workflow.variables._triggerRecordBefore) || {},
                };
            }
        }
    }
}
exports.Context = Context;
