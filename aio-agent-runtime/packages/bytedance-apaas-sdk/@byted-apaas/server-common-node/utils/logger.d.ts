export declare function utils(): any;
declare class ExtraInfo {
    functionVersionID: number;
    sourceLabel: object[];
    objectLabel: object[];
    triggerTimeCost: number;
    runtimeCost: number;
    constructor();
    constructor(functionVersionID: number, sourceLabel: object[], objectLabel: object[]);
}
declare class Log {
    tags: Tag[];
    tagsI18n: I18nTag[];
}
declare class Tag {
    key: string;
    value: string;
}
declare class I18nTag {
    key: string;
    value: object[];
}
export declare function args2string(args: unknown[]): string;
export declare class Logger implements ILogger {
    logs: Log[];
    requestID: string;
    executeID: string;
    functionAPIID: string;
    tags: Tag[];
    tagsI18n: I18nTag[];
    extraInfo: ExtraInfo;
    startTriggerTime: number;
    startRuntime: number;
    errorNum: number;
    infoNum: number;
    warnNum: number;
    isDebug: boolean;
    sequence: number;
    streamLogCount: number;
    logType: string;
    constructor();
    setLogType(logType: string): void;
    error(...args: any[]): void;
    warn(...args: unknown[]): void;
    info(...args: unknown[]): void;
    log(...args: unknown[]): void;
    getFormatLog(logLevel: number, args: any[]): string;
    getFormatDate(): string;
    sendLog(): Promise<void>;
    getSequence(): number;
    /**
     * add log
     *
     * @param content：内容
     * @param level：日志等级，4表示error；6表示info
     * @param type：类型，1表示普通日志；2表示聚合日志
     */
    addLog(content: string, level: number, type?: number): void;
    tagsAddNum(log: Log): void;
    /**
     * 单语tags，用于检索
     *
     * @returns {({value: string, key: string}|{value: number, key: string}|{value: (number|*), key: string}|{value: (string|*), key: string})[]}
     */
    getTags(): Tag[];
    /**
     * 多语tags，用于检索
     *
     * @returns {{value: [], key: string}[]}
     */
    getTagsI18n(): {
        key: string;
        value: any;
    }[];
    /**
     * 仅用来展示
     *
     * @returns {{functionName: (string|*), sourceLabel: (*[]|*), functionVersionID: string, objectLabel: []}}
     */
    getExtraInfo(): ExtraInfo;
}
export interface ILogger {
    /**
     * 信息级别日志
     * @param args 日志内容
     */
    info(...args: any[]): any;
    /**
     * 信息级别日志
     * @param args 日志内容
     */
    log(...args: any[]): any;
    /**
     * 警告级别日志
     * @param args 日志内容
     */
    warn(...args: any[]): any;
    /**
     * 错误级别日志
     * @param args 日志内容
     */
    error(...args: any[]): any;
}
export {};
