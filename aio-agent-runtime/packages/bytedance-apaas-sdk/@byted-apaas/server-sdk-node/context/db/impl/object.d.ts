import { _Cond, _Record, _WhereCond } from '../../../types/types';
import { _IKAsyncEndpoint, _IKQuery, _IKSyncEndpoint } from './IObject';
import { AppCtx } from '../../../application/application';
import { BatchResult } from '../../../common/structs';
import { _IKQueryV3, _IKSyncEndpointV3 } from './IObjectV3';
/**
 * _KObject is kunlun object, every method new a _KQuery object to deal.
 */
export interface _KObject<T> extends _KObjectSync<T>, _KObjectAsync<T>, _KObjectQuery<T> {
}
export declare class _KObject<T> {
    apiName: string;
    constructor(objectApiName: string, appCtx?: AppCtx);
}
/**
 * _KApplicationObject is open sdk object implement.
 */
export interface _KApplicationObject<T> extends _KObjectSync<T>, _KObjectQuery<T> {
}
export declare class _KApplicationObject<T> {
    apiName: string;
    appCtx: AppCtx;
    constructor(objectApiName: string, appCtx: AppCtx);
}
declare class _KObjectSync<T> implements _IKSyncEndpoint<T>, _IKSyncEndpointV3<T> {
    apiName: string;
    appCtx: AppCtx;
    authType: string;
    create(recordMap: _Cond<T>): Promise<{
        _id: number | string;
    }>;
    delete(recordID: number | string): Promise<void>;
    delete(record: _Cond<T>): Promise<void>;
    private deleteV3;
    update(_id: number | string, recordMap: _Cond<T>): Promise<void>;
    update(recordMap: _Cond<T>): Promise<void>;
    private updateV3;
    batchCreate(recordMapList: _Cond<T>[]): Promise<number[] | string[]>;
    private batchCreateV3;
    batchDelete(recordIdList: string[]): Promise<BatchResult>;
    batchDelete(recordIdList: number[]): Promise<BatchResult>;
    batchDelete(recordList: _Cond<T>[]): Promise<BatchResult>;
    private batchDeleteV3;
    batchUpdate(recordMapList: _Cond<T>[]): Promise<BatchResult>;
    private batchUpdateV3;
    useUserAuth(): this;
    useSystemAuth(): this;
}
declare class _KObjectAsync<T> implements _IKAsyncEndpoint<T> {
    apiName: string;
    authType: string;
    batchCreateAsync(recordMapList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    batchDeleteAsync(recordIDList: number[]): Promise<{
        taskID: number;
    }>;
    batchDeleteAsync(recordList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    batchUpdateAsync(recordMapList: _Cond<T>[]): Promise<{
        taskID: number;
    }>;
    useUserAuth(): this;
    useSystemAuth(): this;
}
declare class _KObjectQuery<T> implements _IKQuery<T>, _IKQueryV3<T> {
    apiName: string;
    appCtx: AppCtx;
    authType: string;
    find(): Promise<_Record<T>[]>;
    findOne(): Promise<_Record<T>>;
    findAll(): Promise<_Record<T>[]>;
    findStream(handler: (records: object[]) => Promise<void>): Promise<void>;
    orderBy<K extends keyof T>(fieldApiNames: K[]): _KQuery<T>;
    orderBy<K extends keyof T>(...fieldApiNames: K[]): _KQuery<T>;
    orderByDesc<K extends keyof T>(fieldApiNames: K[]): _KQuery<T>;
    orderByDesc<K extends keyof T>(...fieldApiNames: K[]): _KQuery<T>;
    select<K extends keyof T>(fieldApiNames: K[]): _KQuery<T>;
    select<K extends keyof T>(...fieldApiNames: K[]): _KQuery<T>;
    where(conditionMap: _WhereCond<T>): _KQuery<T>;
    where(): _KQuery<T>;
    fuzzySearch(keyword: string, fieldAPINames: string[]): _KQuery<T>;
    limit(limit: number): _KQuery<T>;
    offset(offset: number): _KQuery<T>;
    count(): Promise<number>;
    useSystemAuth(): this;
    useUserAuth(): this;
}
/**
 * _KQuery is kunlun query implement, implements ORM operations.
 */
declare class _KQuery<T> implements _IKQuery<T>, _IKQueryV3<T> {
    private authType;
    constructor(objectApiName: string, appCtx?: AppCtx, authType?: string);
    find(): Promise<_Record<T>[]>;
    findOne(): Promise<_Record<T>>;
    /**
     * @Deprecated Use FindStream instead.
     */
    findAll(): Promise<_Record<T>[]>;
    findStream(handler: (records: object[]) => Promise<void>, pageLimit?: number): Promise<void>;
    private walkRecordsByID;
    private walkRecordsByLimitOffset;
    private getRecordsByPage;
    orderBy<K extends keyof T>(fieldApiNames: K[]): this;
    orderBy<K extends keyof T>(...fieldApiNames: K[]): this;
    orderByDesc<K extends keyof T>(fieldApiNames: K[]): this;
    orderByDesc<K extends keyof T>(...fieldApiNames: K[]): this;
    select<K extends keyof T>(fieldApiNames: K[]): this;
    select<K extends keyof T>(...fieldApiNames: K[]): this;
    where(conditionMap: _WhereCond<T>): this;
    where(): this;
    fuzzySearch(keyword: string, fieldAPINames: string[]): this;
    limit(limit: number): this;
    offset(offset: number): this;
    count(): Promise<number>;
    private findV3;
    private findPreCheck;
    useSystemAuth(): this;
    useUserAuth(): this;
}
export {};
