import { IQuery, ITable } from '../mongodb';
import { RecordOnlyId } from '../structs';
export declare class Table implements ITable {
    tableName: string;
    constructor(tableName: string);
    create(record: any): any;
    save(record: any): Promise<any>;
    /**
     * 删除记录
     * @param record 对象或数组，且必须包含 _id 字段
     */
    delete(record: RecordOnlyId | RecordOnlyId[]): Promise<any>;
    where(): IQuery;
    where(value: any): IQuery;
    private createFromObject;
    private splitRecordsAndInitCreatedUpdatedAt;
    private saveMany;
}
