"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Logger = exports.args2string = exports.utils = void 0;
const faasinfra = require("../http/faasinfra");
const constants = require("../constants/constants");
const zlib_1 = require("zlib");
const util = require("util");
const microtime = require("microtime");
function utils() {
    return require('./utils');
}
exports.utils = utils;
const deflatePromise = (input) => {
    return new Promise((resolve, reject) => {
        (0, zlib_1.deflate)(input, (err, buffer) => {
            if (err) {
                reject(err);
            }
            resolve(buffer.toString('base64'));
        });
    });
};
class ExtraInfo {
    constructor(functionVersionID, sourceLabel, objectLabel) {
        this.functionVersionID = functionVersionID;
        this.sourceLabel = sourceLabel;
        this.objectLabel = objectLabel;
    }
}
class Log {
}
class Tag {
}
class I18nTag {
}
function args2string(args) {
    let params = [];
    for (let arg of args) {
        if (arg == null) {
            params.push('null');
            continue;
        }
        if (arg instanceof Error) {
            params.push(arg.stack);
            continue;
        }
        if (arg instanceof Object) {
            params.push(utils().stringify(arg, true));
            continue;
        }
        params.push(arg);
    }
    return util.format(...params);
}
exports.args2string = args2string;
class Logger {
    constructor() {
        // 存储所有的日志：普通日志+聚合日志
        this.logs = new Array();
        // 日志详情
        this.requestID = utils().getLogID();
        this.executeID = utils().getExecuteID();
        this.functionAPIID = utils().getFunctionAPIID();
        this.tags = this.getTags();
        this.tagsI18n = this.getTagsI18n();
        this.extraInfo = this.getExtraInfo();
        // 包含冷启动
        this.startTriggerTime = utils().getTriggerTime();
        // 不包含冷启动
        this.startRuntime = new Date().getTime();
        // 统计数量
        this.errorNum = 0;
        this.infoNum = 0;
        this.warnNum = 0;
        // 区分debug和runtime
        this.isDebug = utils().isDebug();
        // 排序
        this.sequence = 1;
        // 流式日志数量统计
        this.streamLogCount = 0;
    }
    setLogType(logType) {
        this.logType = logType;
    }
    error(...args) {
        if (!this.isDebug) {
            if (this.streamLogCount < constants.logLimit.count) {
                this.streamLogCount++;
                console.error(this.getFormatDate(), constants.APaaSLogPrefix, this.getFormatLog(4, args), constants.APaaSLogSuffix);
            }
        }
        else {
            console.error(...args);
        }
        for (let arg of args) {
            utils().handleErrorMsg(arg);
        }
        if (!this.isDebug) {
            this.errorNum++;
            let argsStr = args2string(args);
            this.addLog(argsStr, 4);
        }
    }
    warn(...args) {
        if (!this.isDebug) {
            if (this.streamLogCount < constants.logLimit.count) {
                this.streamLogCount++;
                console.warn(this.getFormatDate(), constants.APaaSLogPrefix, this.getFormatLog(5, args), constants.APaaSLogSuffix);
            }
        }
        else {
            console.warn(...args);
        }
        for (let arg of args) {
            utils().handleErrorMsg(arg);
        }
        if (!this.isDebug) {
            this.warnNum++;
            let argsStr = args2string(args);
            this.addLog(argsStr, 5);
        }
    }
    info(...args) {
        if (!this.isDebug) {
            if (this.streamLogCount < constants.logLimit.count) {
                this.streamLogCount++;
                console.info(this.getFormatDate(), constants.APaaSLogPrefix, this.getFormatLog(6, args), constants.APaaSLogSuffix);
            }
        }
        else {
            console.info(...args);
        }
        for (let arg of args) {
            utils().handleErrorMsg(arg);
        }
        if (!this.isDebug) {
            this.infoNum++;
            let argsStr = args2string(args);
            this.addLog(argsStr, 6);
        }
    }
    log(...args) {
        this.info(...args);
    }
    getFormatLog(logLevel, args) {
        let content = args2string(args);
        // 单条日志长度限制，超过则截断并在该日志后增加 Tip
        if (content.length > constants.logLimit.len) {
            content = content.substring(0, constants.logLimit.len) + constants.logLimitTip.lenTip;
        }
        // 整体日志条数限制，超过则截断并在最后一条日志增加 Tip
        if (this.streamLogCount === constants.logLimit.count) {
            content = content + constants.logLimitTip.countTip;
        }
        const formatLog = {
            event_id: this.executeID,
            function_api_id: this.functionAPIID,
            log_id: this.requestID,
            timestamp: microtime.now(),
            message: content,
            level: logLevel,
            tenant_id: utils().getTenantIDFromCtx(),
            tenant_type: utils().getTenantTypeFromCtx(),
            namespace: utils().getNamespaceFromCtx(),
            log_type: this.logType || '',
        };
        return JSON.stringify(formatLog);
    }
    getFormatDate() {
        // 返回 1970-01-01 格式的字符串，用于 AliFaaS 日志分割以及 aPaaS 日志解析
        return new Date().toISOString().substring(0, 10);
    }
    async sendLog() {
        if (this.logs.length === 0) {
            return;
        }
        // 添加聚合日志
        this.addLog('', 6, 2);
        let compressLog = await deflatePromise(utils().stringify(this.logs));
        try {
            await faasinfra.sendLog({ 'compressData': compressLog });
        }
        catch (e) {
            console.error('send log failed, err: ', e);
        }
    }
    getSequence() {
        return this.sequence++;
    }
    /**
     * add log
     *
     * @param content：内容
     * @param level：日志等级，4表示error；6表示info
     * @param type：类型，1表示普通日志；2表示聚合日志
     */
    addLog(content, level, type = 1) {
        if (type === 1 && this.logs.length >= constants.logLimit.count) {
            return;
        }
        if (content.length > constants.logLimit.len) {
            content = content.substring(0, constants.logLimit.len) + constants.logLimitTip.lenTip;
        }
        let log = {
            // 通用属性
            domain: 'lowcode_func_log',
            requestID: this.requestID,
            type: type,
            level: level,
            content: content,
            createTime: new Date().getTime(),
            createTimeMicro: microtime.now(),
            sequence: this.getSequence(),
            tags: new Array(),
            tagsI18n: new Array(),
            extraInfo: new ExtraInfo(),
        };
        // 聚合日志
        if (type === 2) {
            // 只对聚合日志设置 tags / tagsI18n / extraInfo 字段，以减少报文体积
            // tags: 单语搜索
            log.tags = this.tags;
            // tagsI18n: 多语搜索
            log.tagsI18n = this.tagsI18n;
            // extraInfo: 仅用来展示
            log.extraInfo = this.extraInfo;
            this.tagsAddNum(log);
            if (this.errorNum > 0) {
                log.level = 4;
            }
            let curTime = new Date().getTime();
            log.extraInfo.triggerTimeCost = curTime - this.startTriggerTime;
            log.extraInfo.runtimeCost = curTime - this.startRuntime;
            if (log.extraInfo.triggerTimeCost <= 0) {
                log.extraInfo.triggerTimeCost = log.extraInfo.runtimeCost;
            }
            this.logs.push(utils().stringify(log));
            return;
        }
        if (this.logs.length < constants.logLimit.count - 1) {
            this.logs.push(utils().stringify(log));
        }
        else if (this.logs.length === constants.logLimit.count - 1) {
            log.content = constants.logLimitTip.countTip;
            this.logs.push(utils().stringify(log));
        }
    }
    tagsAddNum(log) {
        log.tags.push({
            key: 'infoNum',
            value: String(this.infoNum),
        });
        log.tags.push({
            key: 'warnNum',
            value: String(this.warnNum),
        });
        log.tags.push({
            key: 'errorNum',
            value: String(this.errorNum),
        });
    }
    /**
     * 单语tags，用于检索
     *
     * @returns {({value: string, key: string}|{value: number, key: string}|{value: (number|*), key: string}|{value: (string|*), key: string})[]}
     */
    getTags() {
        return [{
                key: 'tenantID',
                value: String(utils().getTenantIDFromCtx()),
            }, {
                key: 'namespace',
                value: utils().getNamespaceFromCtx(),
            }, {
                key: 'sourceID',
                value: String(utils().getSourceID()),
            }, {
                key: 'triggerType',
                value: utils().getTriggerType(),
            }, {
                key: 'functionName',
                value: utils().getInvokeFuncName(),
            }, {
                key: 'source',
                value: utils().getSource(),
            }, {
                key: 'instanceID',
                value: String(utils().getInstanceID()),
            }, {
                key: 'tenantType',
                value: String(utils().getTenantTypeFromCtx()),
            }, {
                key: 'functionAPIID',
                value: utils().getFunctionAPIID(),
            }, {
                key: 'eventID',
                value: utils().getExecuteID(),
            }];
    }
    /**
     * 多语tags，用于检索
     *
     * @returns {{value: [], key: string}[]}
     */
    getTagsI18n() {
        return [{
                key: 'functionLabel',
                value: utils().getFuncLabel(),
            }];
    }
    /**
     * 仅用来展示
     *
     * @returns {{functionName: (string|*), sourceLabel: (*[]|*), functionVersionID: string, objectLabel: []}}
     */
    getExtraInfo() {
        return new ExtraInfo(utils().getFuncVersionID(), utils().getSourceLabel(), utils().getObjectLabel());
    }
}
exports.Logger = Logger;
