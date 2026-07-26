import { BaseFieldType } from './types/objects';
import { RecordDetail } from './components/desktop/recordDetail';
import { List as DesktopList } from './components/desktop/list';
import { List as MobileList } from './components/mobile/list';
interface IMetaData<mt> {
    /**
     * 操作指定对象的元数据信息
     * @param objectApiName 指定对象的 ApiName
     * @example
     * ```
     * application.metadata.object('test').getFields()
     * ```
     */
    object<T extends keyof mt>(objectApiName: T): IKObject<mt[T]>;
}
interface IKObject<T> {
    /**
     * 读取对象的字段列表
     */
    getFields(): Promise<BaseFieldType[]>;
    /**
     * 读取某字段的元数据信息
     * @param fieldApiName 字段的 ApiName
     */
    getField<K extends keyof T>(fieldApiName: K): Promise<BaseFieldType>;
}
interface IPage {
    getRecordDetail(componentName: string): Promise<RecordDetail>;
    getList(componentName: string): Promise<DesktopList>;
    getId(): Promise<number>;
    getMobileList(componentName: string): Promise<MobileList>;
    updateMobileList(componentName: string, params: any): Promise<void>;
}
declare class MetaData<mt> implements IMetaData<mt> {
    constructor(ctx: any);
    object<T>(objectApiName: keyof mt): IKObject<T>;
    page(apiName: string, objectApiName: string, type: string): Page;
}
declare function metadata<mt>(ctx: any): IMetaData<mt>;
declare class MetaDataV3<mt> implements IMetaData<mt> {
    constructor(ctx: any);
    object<T>(objectApiName: keyof mt): IKObject<T>;
}
declare function metadataV3<mt>(ctx: any): IMetaData<mt>;
declare class Page implements IPage {
    pageApiName: string;
    objectApiName: string;
    type: 'app' | 'record_page';
    /**
     *
     * @param pageApiName: 页面apiName
     * @param objectApiName：对象apiName
     * @param type：app 或 record_page
     */
    constructor(pageApiName: string, objectApiName: string, type: string);
    getRecordDetail(componentName: string): Promise<RecordDetail>;
    getList(componentName: string): Promise<DesktopList>;
    getId(): Promise<number>;
    getMobileList(componentName: string): Promise<MobileList>;
    updateMobileList(componentName: string, params: any): Promise<void>;
}
declare function metaType(): any;
export { IMetaData, IKObject, IPage, MetaData, metadata, metaType, MetaDataV3, metadataV3, };
