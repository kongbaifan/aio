export interface Locale {
    /**
     * 语言
     */
    language: string;
    /**
     * 时区
     */
    timezone: Timezone;
}
export interface Timezone {
    /**
     * 时区位置
     */
    location: string;
    /**
     * 较于标准时区的偏移量
     */
    offset: string;
}
export type LocaleWithUID = {
    /**
     * 用户 ID
     */
    userID: number;
} & Locale;
