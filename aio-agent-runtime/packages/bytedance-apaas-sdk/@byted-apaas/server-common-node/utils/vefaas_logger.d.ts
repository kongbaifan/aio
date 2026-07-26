export declare class VeFaaSLogger {
    static originConsoleLog: {
        (...data: any[]): void;
        (message?: any, ...optionalParams: any[]): void;
    };
    static originConsoleInfo: {
        (...data: any[]): void;
        (message?: any, ...optionalParams: any[]): void;
    };
    static originConsoleWarn: {
        (...data: any[]): void;
        (message?: any, ...optionalParams: any[]): void;
    };
    static originConsoleError: {
        (...data: any[]): void;
        (message?: any, ...optionalParams: any[]): void;
    };
    static get_content(...args: any[]): string;
    static info(...args: any[]): void;
    static log(...args: any[]): any;
    static warn(...args: any[]): any;
    static error(...args: any[]): void;
}
