"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleCriterion = exports.buildLogic = exports.Logic = exports.convertCriterionToCriterionV3 = exports.addIDCriterion = exports.buildExpression = exports.buildCriterion = exports.Condition = void 0;
const expression_1 = require("./expression");
const operator_1 = require("./operator");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const Request = require("../../../request/interface");
const common = require("@byted-apaas/server-common-node");
var fieldType = common.fieldType;
const dayjs = require("dayjs");
// 条件操作
class Condition {
    /**
     *
     * @param objectApiName 对象的ApiName
     * @param fieldApiName  字段的ApiName，指左值，即key
     * @param index         条件的排序
     * @returns {Expression}
     */
    toExpression(objectApiName, fieldApiName, index) {
        this.left = fieldApiName;
        let left;
        let right;
        let op;
        if (this.right instanceof Condition) {
            left = new expression_1.MetadataExpressionField(objectApiName, this.right.left);
            right = new expression_1.ConstantExpressionField(this.right.right);
            left.settings.fieldPath.unshift(new expression_1.MetadataExpressionField(objectApiName, fieldApiName).settings.fieldPath[0]);
            op = this.right.op;
        }
        else {
            left = new expression_1.MetadataExpressionField(objectApiName, fieldApiName);
            right = new expression_1.ConstantExpressionField(this.right);
            op = this.op;
        }
        return new expression_1.Expression(left, op, right, index);
    }
    constructor(left, right, op = operator_1.operates.EQ) {
        this.left = left;
        this.right = right;
        if (op) {
            this.op = op;
        }
    }
}
exports.Condition = Condition;
// param type should be spercific
function isKunlunTypeOrSerializedObject(obj) {
    // instanceof 改动8
    // return !!(obj instanceof fieldType.KunlunFieldType || (obj && obj.toJSON && obj.toJSON instanceof Function));
    return !!(fieldType.isKFieldType(obj) || (obj && obj.toJSON && obj.toJSON instanceof Function));
}
/**
 * 构造 criterion
 *
 * @param logic
 * @param objectApiName
 * @param maxId 添加 _id>maxId 条件，为 -1 表示不使用该参数
 */
function buildCriterion(logic, objectApiName) {
    let index = 0;
    let logics = [];
    let expressions = [];
    // check type of logic
    function f(logic, value = 'and') {
        // 1.如果是逻辑表达式
        if (logic instanceof Logic) {
            logics.push('(');
            for (let i = 0; i < logic.logics.length; i++) {
                let p = logic.logics[i];
                f(p, logic.value);
                if (i < logic.logics.length - 1) {
                    logics.push(` ${logic.value} `);
                }
            }
            if (logic.expressions) {
                f(logic.expressions, logic.value);
            }
            logics.push(')');
            return;
        }
        // 2.否则是算法表达式
        let exps = logic;
        let logs = [];
        for (let left of Object.keys(exps)) {
            let right = parseCondition(logic[left]);
            let copy = right;
            if (server_common_node_1.utils.isObject(right) && !(right instanceof Condition) && !isKunlunTypeOrSerializedObject(right)) {
                for (let leftInner of Object.keys(right)) {
                    index++;
                    logs.push(index);
                    copy = {};
                    copy[leftInner] = right[leftInner];
                    expressions.push(buildExpression(objectApiName, left, copy, index));
                }
            }
            else if (right instanceof Condition && right.op === operator_1.operates.EQ && server_common_node_1.utils.isObject(right.right)) {
                right = right.right;
                for (const leftInner of Object.keys(right)) {
                    index++;
                    logs.push(index);
                    copy = {};
                    copy[leftInner] = right[leftInner];
                    expressions.push(buildExpression(objectApiName, left, copy, index));
                }
            }
            else {
                index++;
                logs.push(index);
                expressions.push(buildExpression(objectApiName, left, right, index));
            }
        }
        logics.push(logs.join(` ${value} `));
    }
    f(logic);
    // 如果未设置filter，默认添加: _isDeleted = false
    if (expressions.length < 1) {
        logics = [];
        expressions.push(buildExpression(objectApiName, '_isDeleted', false, expressions.length + 1));
        logics.push('1');
        return { conditions: expressions, logic: logics.join('') };
    }
    let isContainDeleted = false;
    for (let i = 0; i < expressions.length; i++) {
        let expression = expressions[i];
        try {
            if (expression.left.type === 'metadataVariable' && expression.left.settings.fieldPath[0].fieldApiName === '_isDeleted') {
                isContainDeleted = true;
                break;
            }
        }
        catch (e) {
            console.error(e);
        }
    }
    if (!isContainDeleted) {
        expressions.push(buildExpression(objectApiName, '_isDeleted', false, expressions.length + 1));
        logics.splice(0, 0, '(');
        logics.push(' and ', `${expressions.length}`, ')');
    }
    return { conditions: expressions, logic: logics.join('') };
}
exports.buildCriterion = buildCriterion;
// 避免引入组件库导致 app 使用的是组件库的 condition 是出现判断失败的问题。
function parseCondition(obj) {
    if (!(obj instanceof Object)) {
        return obj;
    }
    // 检查是否有 Condition 类定义的属性
    const expectedKeys = ['left', 'right', 'op'];
    const keys = Object.keys(obj);
    // 检查属性数量是否匹配
    if (keys.length !== expectedKeys.length) {
        return obj;
    }
    // 检查属性是否都存在
    for (const key of expectedKeys) {
        if (!keys.includes(key)) {
            return obj;
        }
    }
    // 校验 op 属性的值是否在 operates 中
    const opValue = obj.op;
    if (!Object.values(operator_1.operates).includes(opValue)) {
        return obj;
    }
    // 创建一个 Condition 的实例并比较属性
    return new Condition(obj.left, obj.right, obj.op);
}
function buildExpression(objectApiName, left, right, index = 1) {
    if (!(right instanceof Condition)) {
        right = new Condition(left, right);
    }
    if (right instanceof Condition) {
        if (server_common_node_1.utils.isObject(right.right) && !(right.right instanceof Condition) && !isKunlunTypeOrSerializedObject(right.right)) {
            let key = Object.keys(right.right)[0];
            let rr = right.right;
            if (key === 'id') {
                if (rr[key] instanceof Condition) {
                    right.op = rr[key].op;
                    right.right = { id: rr[key].right };
                }
            }
            else if (!(rr[key] instanceof Condition)) {
                right.right = new Condition(key, rr[key], right.op);
            }
            else {
                rr[key].left = key;
                right.right = rr[key];
            }
        }
        return right.toExpression(objectApiName, left, index);
    }
    return null;
}
exports.buildExpression = buildExpression;
/**
 * 在 criterion 中添加 _id>maxId 的判断条件
 *
 * @param criterion
 * @param apiName
 * @param maxId 添加 _id>maxId 条件
 */
function addIDCriterion(criterion, apiName, maxId) {
    criterion.conditions.push(buildExpression(apiName, '_id', new Condition('_id', maxId, operator_1.operates.GT), criterion.conditions.length + 1));
    const logics = criterion.logic.split('');
    logics.splice(0, 0, '(');
    logics.push(' and ', `${criterion.conditions.length}`, ')');
    criterion.logic = logics.join('');
    return criterion;
}
exports.addIDCriterion = addIDCriterion;
/**
 * 构造 convertCriterionToCriterionV3
 *
 * @param criterion v1 版本的条件
 */
function convertCriterionToCriterionV3(criterion) {
    let criterionV3 = {
        conditions: [],
        expression: criterion.logic,
    };
    // const criterionCopy = {...criterion};  // 创造一个v1Data的拷贝
    criterionV3.conditions = criterion.conditions.map(condition => {
        const rightField = new expression_1.ConstantExpressionFieldV3(condition.right.settings.data);
        const leftField = new expression_1.MetadataExpressionFieldV3(condition.left.settings.fieldPath);
        let conditionV3 = new expression_1.ExpressionV3(leftField, condition.operator, rightField, condition.index);
        return conditionV3;
    });
    return criterionV3;
}
exports.convertCriterionToCriterionV3 = convertCriterionToCriterionV3;
// 逻辑操作：and 和 or
class Logic {
    constructor(expressions = null, logicValue = 'and') {
        // 通常情况
        this.value = logicValue;
        this.expressions = expressions;
        this.logics = [];
        if (!expressions) {
            return;
        }
        // 下钻右值为逻辑表达式 and|or 的情况
        for (let left of Object.keys(expressions)) {
            if (expressions[left] instanceof Object && !(expressions[left] instanceof Array)) {
                let right = expressions[left];
                for (const key of Object.keys(right)) {
                    if (right[key] instanceof Logic) {
                        this.handleRightLogic(right, left);
                        delete expressions[left];
                        break;
                    }
                }
            }
        }
        // 右值为逻辑表达式 and|or 的情况
        for (let left of Object.keys(expressions)) {
            let right = expressions[left];
            if (right instanceof Logic) {
                this.handleRightLogic(expressions);
                break;
            }
        }
    }
    /**
     * 处理：右值包含逻辑表达式and|or的情况
     *
     * @param expressions
     * @param lookupField
     */
    handleRightLogic(expressions, lookupField = null) {
        this.expressions = null;
        for (let left of Object.keys(expressions)) {
            let right = expressions[left];
            // 1.如果右值为Logic类型
            if (right instanceof Logic) {
                // 1.1 表达式不为空
                if (right.expressions) {
                    let exp = {};
                    if (lookupField && right.expressions instanceof Condition) {
                        right.expressions.left = lookupField;
                        let obj = {};
                        obj[left] = right.expressions.right;
                        right.expressions.right = obj;
                        exp[lookupField] = right.expressions;
                    }
                    else {
                        exp[left] = right.expressions;
                    }
                    this.logics.push(new Logic(exp, 'and'));
                }
                else {
                    // 1.2 表达式为空
                    let log = new Logic(null, right.value);
                    for (let logic of right.logics) {
                        let exp = {};
                        if (lookupField && logic.expressions instanceof Condition) {
                            logic.expressions.left = lookupField;
                            let obj = {};
                            obj[left] = logic.expressions.right;
                            logic.expressions.right = obj;
                            exp[lookupField] = logic.expressions;
                        }
                        else {
                            if (logic.expressions instanceof Condition) {
                                logic.expressions.left = left;
                            }
                            exp[left] = logic.expressions;
                        }
                        log.logics.push(new Logic(exp, logic.value));
                    }
                    this.logics.push(log);
                }
            }
            else {
                let exp = {};
                exp[left] = right;
                const log = new Logic(exp, 'and');
                this.logics.push(log);
            }
        }
    }
    addLogic(logic) {
        if (logic instanceof Logic) {
            this.logics.push(logic);
        }
    }
}
exports.Logic = Logic;
function buildLogic(param, logicValue = 'and') {
    if (param.length === 1) {
        return new Logic(param[0], logicValue);
    }
    let logic = new Logic(null, logicValue);
    param.forEach(p => {
        if (!p) {
            return;
        }
        // Check：会走到这里吗？
        if (p instanceof Logic) {
            logic.logics.push(p);
        }
        else if (p instanceof Object && !(p instanceof Array)) {
            logic.logics.push(new Logic(p, 'and'));
        }
        else {
            throw new server_common_node_1.exceptions.InvalidParamError(`param (${p}) is invalid`);
        }
    });
    return logic;
}
exports.buildLogic = buildLogic;
// where参数的树状结构
class Filter {
    /**
     * @param logic: filters之间的逻辑关系
     */
    constructor(logic) {
        if (!logic) {
            this.logic = 'and';
        }
        else {
            this.logic = logic;
        }
        this.expression = null;
        this.filters = [];
    }
    // 现在仅考虑一层结构，不考虑嵌套
    toCriterion() {
        let conditions = [];
        let logics = [];
        this.filters.forEach((filter, i) => {
            if (!filter.expression) {
                return;
            }
            conditions.push({
                index: i + 1,
                left: filter.expression.left,
                right: filter.expression.right,
                operator: filter.expression.operator,
            });
            logics.push(i + 1);
        });
        const criterion = { conditions, logic: logics.join(' and ') };
        return JSON.stringify(criterion);
    }
}
async function handleCriterion(criterion) {
    if (!criterion || !criterion.conditions || !(criterion.conditions instanceof Array)) {
        return criterion;
    }
    let fieldRes = await handleLookupCondition(criterion.conditions);
    for (let condition of criterion.conditions) {
        if (fieldRes && fieldRes.lookupMap) {
            let val = fieldRes.lookupMap.get(condition.left.settings.fieldPath[0].fieldApiName);
            if (condition.left.settings.fieldPath[1] && val && val.objectApiName) {
                condition.left.settings.fieldPath[1].objectApiName = val.objectApiName;
            }
        }
        await handleCondition(condition, fieldRes);
    }
    return criterion;
}
exports.handleCriterion = handleCriterion;
async function handleLookupCondition(conditions) {
    if (!(conditions && conditions[0] && conditions[0].left && conditions[0].left.settings && conditions[0].left.settings.fieldPath)) {
        return null;
    }
    let queryMap = new Map(), fieldName;
    let opList = [operator_1.operates.LT, operator_1.operates.LTE, operator_1.operates.GT, operator_1.operates.GTE, operator_1.operates.HAS_ANY_OF, operator_1.operates.HAS_NONE_OF];
    for (const condition of conditions) {
        if (condition.left.settings.fieldPath.length > 1 || opList.includes(condition.operator)) {
            fieldName = condition.left.settings.fieldPath[0].fieldApiName;
            queryMap.set(fieldName, {});
        }
    }
    if (queryMap.size === 0) {
        return {};
    }
    let lookupMap = new Map(), dateSet = new Set();
    let firstObjApiName = conditions[0].left.settings.fieldPath[0].objectApiName;
    let fields = [];
    // 获取对象的字段
    if (queryMap.size === 1) {
        fields.push(await Request.GetInstance().getField(firstObjApiName, fieldName));
    }
    else {
        fields = await Request.GetInstance().getFields(firstObjApiName);
    }
    for (const field of fields) {
        parseFieldInfo(field, lookupMap, dateSet);
    }
    return {
        lookupMap: lookupMap,
        dateSet: dateSet,
    };
}
function parseFieldInfo(field, lookupMap, dateSet) {
    if (!(field && field.type && field.type.name && field.type.settings)) {
        return;
    }
    switch (field.type.name) {
        case 'lookup':
            lookupMap.set(field.api_name, {
                objectApiName: field.type.settings.referenced_object_api_name,
                isHierarchy: field.type.settings.is_hierarchy,
                targetIsHierarchy: field.type.settings.target_is_hierarchy,
            });
            break;
        case 'date':
            dateSet.add(field.api_name);
            break;
        case 'formula':
            if (field.type.settings.return_type === 'date') {
                dateSet.add(field.api_name);
            }
            break;
    }
}
async function handleCondition(condition, fieldRes) {
    if (!condition || !condition.left || condition.left.type !== 'metadataVariable') {
        return;
    }
    if (!condition.left.settings || !condition.left.settings.fieldPath || !(condition.left.settings.fieldPath instanceof Array)) {
        return;
    }
    let fieldPathList = condition.left.settings.fieldPath;
    for (let i = 0; i < fieldPathList.length; i++) {
        fieldRes.isFirstLayer = (i === 0);
        if (fieldPathList.length === (i + 1)) { // 最后的查询条件 path 做处理
            switch (condition.operator) {
                case operator_1.operates.LT:
                    // 日期类型的lte，需要转换成isOnOrBefore
                    await handleDateAndDatetimeOperator(fieldRes, condition, fieldPathList[i], operator_1.operates.isOnOrBefore, -1);
                    break;
                case operator_1.operates.LTE:
                    // 日期类型的lte，需要转换成isOnOrBefore
                    await handleDateAndDatetimeOperator(fieldRes, condition, fieldPathList[i], operator_1.operates.isOnOrBefore);
                    break;
                case operator_1.operates.GT:
                    // 日期类型的gte，需要转换成isOnOrAfter
                    await handleDateAndDatetimeOperator(fieldRes, condition, fieldPathList[i], operator_1.operates.isOnOrAfter, 1);
                    break;
                case operator_1.operates.GTE:
                    // 日期类型的gte，需要转换成isOnOrAfter
                    await handleDateAndDatetimeOperator(fieldRes, condition, fieldPathList[i], operator_1.operates.isOnOrAfter);
                    break;
                case operator_1.operates.HAS_ANY_OF:
                case operator_1.operates.HAS_NONE_OF:
                    // hierarchy lookup，需要为extendLogicTags添加all
                    // lookup 下钻的话，只在最后一层加 all
                    await handleHierarchyFieldPath(fieldRes, fieldPathList[i]);
                    break;
            }
        }
    }
}
// 日期类型的lte，需要转换成isOnOrBefore
// 日期类型的gte，需要转换成isOnOrAfter
async function handleDateAndDatetimeOperator(fieldRes, condition, path, operator, addDay = 0) {
    if (!condition || !path || !path.objectApiName || !path.fieldApiName) {
        return;
    }
    let isDateType = false;
    if (fieldRes && fieldRes.isFirstLayer) {
        if (fieldRes.dateSet && fieldRes.dateSet.has(path.fieldApiName)) {
            isDateType = true;
        }
    }
    else {
        let field = await Request.GetInstance().getField(path.objectApiName, path.fieldApiName);
        isDateType = isDate(field);
    }
    if (isDateType) {
        condition.operator = operator;
        if (condition.right && condition.right.settings && condition.right.settings.data) {
            condition.right.settings.data = dateAdd(condition.right.settings.data, addDay);
        }
    }
}
// hierarchy lookup，需要为extendLogicTags添加all
async function handleHierarchyFieldPath(fieldRes, path) {
    if (!path || !path.objectApiName || !path.fieldApiName) {
        return;
    }
    let isHierarchyType = false;
    if (fieldRes && fieldRes.isFirstLayer && fieldRes.lookupMap) {
        let val = fieldRes.lookupMap.get(path.fieldApiName);
        if (val && val.targetIsHierarchy) {
            isHierarchyType = true;
        }
    }
    else {
        let field = await Request.GetInstance().getField(path.objectApiName, path.fieldApiName);
        isHierarchyType = targetIsHierarchy(field);
    }
    if (!isHierarchyType) {
        return;
    }
    if (!path.extendLogicTags) {
        path.extendLogicTags = [];
    }
    path.extendLogicTags.push('all');
}
function isHierarchy(field) {
    return field && field.type && field.type.name === 'lookup' && field.type.settings && field.type.settings.is_hierarchy;
}
function targetIsHierarchy(field) {
    return field && field.type && field.type.name === 'lookup' && field.type.settings && field.type.settings.target_is_hierarchy;
}
function isDate(field) {
    return field && field.type && ((field.type.name === 'date') || (field.type.name === 'formula' && field.type.settings && field.type.settings.return_type === 'date'));
}
function dateAdd(date, num) {
    try {
        if (date instanceof Date) {
            return dayjs(date).add(num, 'day').format('YYYY-MM-DD');
            // } else if (date instanceof fieldType.Date) { // instanceof 改动9
        }
        else if (fieldType.isKFieldTypeDate(date)) {
            return dayjs(date.toJSON()).add(num, 'day').format('YYYY-MM-DD');
        }
        else if (typeof (date) === 'string') {
            return dayjs(date).add(num, 'day').format('YYYY-MM-DD');
        }
        return date;
    }
    catch (e) {
        return date;
    }
}
