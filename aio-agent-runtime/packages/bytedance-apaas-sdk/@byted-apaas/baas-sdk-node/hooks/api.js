"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFunctionSync = exports.globalVar = exports.oss = exports.redis = exports.mongodb = void 0;
const mongodb_1 = require("../mongodb/impl/mongodb");
const redis_1 = require("../redis/impl/redis");
const file_1 = require("../file/impl/file");
const common = require("@byted-apaas/server-common-node");
const request = require("../http/interface");
const global_var_1 = require("../global_var/impl/global_var");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const nodeCls = require('node-cls');
const nodeClsCtx = common.nodeClsCtx;
const exceptions = common.exceptions;
const utils = common.utils;
const checkUtils = common.checkUtils;
const functionSources = common.constants.functionSources;
exports.mongodb = new mongodb_1.Mongodb();
exports.redis = new redis_1.Redis();
exports.oss = new file_1.File();
exports.globalVar = new global_var_1.GlobalVar();
// 同步调用云函数
function getFunctionSync(context, logger) {
    return (funcName) => {
        return {
            invoke: async (params) => {
                let func = undefined;
                let requireFunc = utils.getRequireFunc();
                if (requireFunc) {
                    try {
                        func = requireFunc(funcName);
                    }
                    catch (e) {
                    }
                }
                if (func) {
                    // 本地调用
                    let loopMasks = [funcName];
                    const reqCtx = nodeCls.get('loopCtx');
                    if (reqCtx && reqCtx.loopMasks && Array.isArray(reqCtx.loopMasks)) {
                        if (reqCtx.loopMasks.includes(funcName)) {
                            throw new exceptions.InvalidParamError(`Task execution forms a loop.`);
                        }
                        loopMasks.push(...reqCtx.loopMasks);
                    }
                    // 修改 source 全局函数
                    const ctx = nodeCls.create('loopCtx');
                    ctx.loopMasks = loopMasks;
                    return await ctx.run(async () => {
                        const dynCtx = nodeClsCtx.getDynCtx();
                        dynCtx.source = functionSources.globalFunction;
                        return await dynCtx.run(async () => {
                            return await common.hooks.invoke(func, params, context, logger);
                        });
                    });
                }
                // 远程调用 微服务 | 函数找不到
                return await request.GetInstance().invokeFuncSync({
                    APIName: funcName,
                    isInvokeByAPIName: true
                }, params);
            }
        };
    };
}
exports.getFunctionSync = getFunctionSync;
