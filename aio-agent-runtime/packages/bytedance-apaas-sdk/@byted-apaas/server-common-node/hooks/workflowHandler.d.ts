export declare function updateVariable(context: any, updateWorkflowVariables: Function): (...param: any[]) => Promise<void>;
/**
 * workflow 场景的return 表示调用updateVariable，因此要进行特殊处理
 * @param ctx
 * @param response
 */
export declare function handleResponse(ctx: any, response: any): void;
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
export declare function convertToKunlunFieldType(ctx: any, key: string, value: any): any;
