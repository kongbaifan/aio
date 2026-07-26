import { ITool } from "./tool/itool";
export interface IFaaS<T> {
    /**
     * 工具方法
     */
    tool: ITool;
    /**
     * 全局函数
     * @param funcName 函数名
     */
    function(funcName: T): {
        invoke: (params: any) => Promise<any>;
    };
}
