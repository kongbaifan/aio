export type I18n = {
    language_code: number;
    text: string;
};
export type I18ns = I18n[];
export declare function isNullOrUndefined(param: any): boolean;
export declare function transI18nsToMultilingualV3(i18ns: I18ns): MultilingualTypeV3;
export interface MultilingualTypeV3 {
    zh_CN: string;
    en_US: string;
}
