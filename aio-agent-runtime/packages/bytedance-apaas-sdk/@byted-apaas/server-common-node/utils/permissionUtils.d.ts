/**
 * 存储记录类型的无权限字段
 *
 * @param objectAPIName
 * @param record
 * @param unauthFields
 * @param modifyRecord
 */
export declare function appendUnauthFieldRecord(objectAPIName: string, record: any, unauthFields: string[], modifyRecord?: boolean): void;
/**
 * 存储记录列表类型的无权限字段
 *
 * @param objectAPIName 对象的 objectAPIName，为空时表示不支持透传，但无权限字段正常返回
 * @param records
 * @param unauthFieldsList
 * @param modifyRecord
 */
export declare function appendUnauthFieldRecordList(objectAPIName: string, records: any[], unauthFieldsList: string[][], modifyRecord?: boolean): void;
/**
 * 根据对象获取所有的无权限字段
 *
 * @param objectAPIName
 */
export declare function getUnauthFieldByObject(objectAPIName: string): Record<number, string[]>;
/**
 * 根据记录 ID 获取无权限字段
 *
 * @param objectAPIName
 * @param recordID
 */
export declare function getUnauthFieldByRecordID(objectAPIName: string, recordID: number): string[];
/**
 * 删除无权限字段
 *
 * @param record
 * @param objectAPIName
 */
export declare function delUnauthField(record: any, objectAPIName?: string): {
    newRecord: any;
    unauthFields: string[];
};
/**
 * 批量删除无权限字段
 *
 * @param records
 * @param objectAPIName
 */
export declare function batchDelUnauthField(records: any[], objectAPIName?: string): {
    newRecords: any;
    unauthFieldsList: string[][];
};
/**
 * 删除参数中的无权限字段
 * 1.去除参数中 _unauthFields
 * 2.构造 permission: {_unauthFields: {}}
 *
 * @param funcAPIName 函数的 apiName
 * @param inputOrOutput 入参或出参，取值为 input 或 output
 * @param params 参数
 */
export declare function delParamsUnauthField(funcAPIName: string, inputOrOutput: 'input' | 'output', params: Record<string, any>): Promise<{
    _unauthFields: Record<string, string[] | string[][]>;
}>;
/**
 * 向参数中追加无权限字段
 * 1.无权限字段信息存储到上下文中
 * 2.无权限字段信息写入到 params 的参数中
 *
 * @param funcAPIName 函数的 apiName
 * @param inputOrOutput 入参或出参，值为 input | output
 * @param params 参数
 * @param unauthFieldsMap 无权限字段
 */
export declare function appendUnauthFieldToParams(funcAPIName: string, inputOrOutput: 'input' | 'output', params: Record<string, any>, unauthFieldsMap: Record<string, string[] | string[][]>): Promise<void>;
