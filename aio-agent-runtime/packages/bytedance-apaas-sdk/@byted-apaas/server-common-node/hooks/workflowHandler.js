"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.convertToKunlunFieldType = exports.handleResponse = exports.updateVariable = void 0;
const utils = require("../utils/utils");
const checkUtils = require("../utils/checkUtils");
const exceptions = require("../utils/exceptions");
const type_1 = require("../kunlun/type/type");
const constants = require("../constants/constants");
const NO_TYPE = 'notype';
function updateVariable(context, updateWorkflowVariables) {
    return async (...param) => {
        if (utils.isAsync()) {
            throw new exceptions.InvalidParamError('Cannot update workflow variables during asynchronous execution');
        }
        if (param.length === 1) {
            await updateVariableByMap(context, param[0], updateWorkflowVariables);
            return;
        }
        if (param.length === 2) {
            let m = {};
            m[param[0]] = param[1];
            await updateVariableByMap(context, m, updateWorkflowVariables);
            return;
        }
        throw new exceptions.InvalidParamError("the number of updateVariable's param is 1 or 2");
    };
}
exports.updateVariable = updateVariable;
async function updateVariableByMap(ctx, variableMap, updateWorkflowVariables) {
    if (checkUtils.isNotObject(variableMap)) {
        throw new exceptions.InvalidParamError(`variableMap's type is not object, but ${typeof (variableMap)}`);
    }
    let variables = {}, variableTypes = {};
    Object.keys(variableMap).forEach(key => {
        checkUtils.checkWorkflowAndFlowVariableTypes(ctx, key);
        let value = variableMap[key];
        const type = (ctx.flow ? ctx.flow : ctx.workflow).variableTypes[key].type;
        variables[key] = convertToKunlunFieldType(ctx, key, value);
        variableTypes[key] = type;
    });
    // 运行时才会调用workflow
    if (!utils.isDebug()) {
        await updateWorkflowVariables(ctx, (ctx.flow ? ctx.flow : ctx.workflow).instanceId, JSON.stringify(variables), JSON.stringify(variableTypes));
    }
}
/**
 * workflow 场景的return 表示调用updateVariable，因此要进行特殊处理
 * @param ctx
 * @param response
 */
function handleResponse(ctx, response) {
    for (let key of Object.keys(response)) {
        let value = response[key];
        response[key] = convertToKunlunFieldType(ctx, key, value);
    }
}
exports.handleResponse = handleResponse;
/**
 * 转成Kunlun需要的格式
 *
 * @param ctx
 * @param key
 * @param value：类型：
 *                  1.KunlunFieldType;
 *                  2.json -> KunlunFieldType;
 *                  3.record类型：metadataVariable
 *                  4.未知类型
 * @returns {*}
 */
function convertToKunlunFieldType(ctx, key, value) {
    checkUtils.checkWorkflowAndFlowVariableTypes(ctx, key);
    let type = (ctx.flow ? ctx.flow : ctx.workflow).variableTypes[key].type;
    // 1.对象实例 instanceof 改动1
    // if (value instanceof KunlunFieldType) {
    if ((0, type_1.isKFieldType)(value)) {
        if (type !== NO_TYPE && value.type !== type) {
            throw new exceptions.InvalidParamError(`value's type is ${value.type}, but expect ${type}`);
        }
        value = value.toJSON();
        ctx.workflow.variables[key] = value;
        ctx.flow.variables[key] = value;
        return value;
    }
    else if (type_1.type2fieldType[type]) {
        // 2.对象类型，需要构造对象实例
        value = new type_1.type2fieldType[type](value).toJSON();
        ctx.workflow.variables[key] = value;
        ctx.flow.variables[key] = value;
        return value;
    }
    else if (type === constants.WfVarType.RECORD) {
        // 3.记录变量
        // 3.1 新值为空直接返回
        if (!value) {
            return value;
        }
        // 3.2 旧值为空，赋值为{}
        let oldValue = (ctx.flow ? ctx.flow : ctx.workflow).variables[key];
        if (!oldValue) {
            ctx.workflow.variables[key] = {};
            ctx.flow.variables[key] = {};
            oldValue = {};
        }
        // 3.3 非对象类型，直接报错
        if (checkUtils.isNotObject(oldValue)) {
            throw new exceptions.InvalidParamError(`flow.variables.${key} is not object, but ${oldValue}(${typeof (oldValue)})`);
        }
        if (checkUtils.isNotObject(value)) {
            throw new exceptions.InvalidParamError(`${key}'s param is not object, but ${typeof (value)}`);
        }
        // 3.4 逐字段赋值
        for (let k of Object.keys(value)) {
            let v = value[k];
            // instanceof 改动2
            // if (v instanceof KunlunFieldType) {
            if ((0, type_1.isKFieldType)(v)) {
                value[k] = v.toJSON();
                oldValue[k] = value[k];
            }
            else {
                oldValue[k] = v;
                value[k] = v;
            }
        }
        return value;
    }
    else if (type === constants.WfVarType.LIST_RECORD) {
        // 4.明细组件
        // 4.1 新值为空直接返回
        if (!value) {
            return value;
        }
        // 4.2 非数组类型，直接报错
        if (!Array.isArray(value)) {
            throw new exceptions.InvalidParamError(`flow.variables.${key}'s param is not array, but ${typeof (value)}`);
        }
        let result = [];
        for (let record of value) {
            if (checkUtils.isNotObject(record)) {
                throw new exceptions.InvalidParamError(`flow.variables.${key}'s item must is object, but ${record}(${typeof (record)})`);
            }
            for (let k of Object.keys(record)) {
                let v = record[k];
                // instanceof 改动3
                // if (v instanceof KunlunFieldType) {
                if ((0, type_1.isKFieldType)(v)) {
                    record[k] = v.toJSON();
                }
                else {
                    record[k] = v;
                }
            }
            result.push(record);
        }
        ctx.workflow.variables[key] = result;
        ctx.flow.variables[key] = result;
        return result;
    }
    else {
        ctx.workflow.variables[key] = value;
        ctx.flow.variables[key] = value;
    }
    return value;
}
exports.convertToKunlunFieldType = convertToKunlunFieldType;
