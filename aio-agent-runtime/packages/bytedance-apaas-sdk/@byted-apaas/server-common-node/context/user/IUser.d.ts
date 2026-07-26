import { LocaleWithUID, Locale } from './types';
import { metadataMap } from '../../data';
export interface IUser {
    /**
     * 根据单个 UserID 获取对应用户的 Locale 信息
     * @param userId 单个用户的 ID
     */
    getLocale(userId: number): Promise<LocaleWithUID>;
    /**
     * 根据多个 UserID 获取对应用户的 Locale 信息
     * @param userIdList 多个用户的 ID
     */
    getLocale(userIdList: number[]): Promise<LocaleWithUID[]>;
}
export type IUserWithInitiator = IUser & {
    /**
     * 获取触发 workflow 用户的信息
     */
    initiator: metadataMap['_user'] & {
        /**
         * Locale 信息
         */
        _locale: Locale;
    };
};
