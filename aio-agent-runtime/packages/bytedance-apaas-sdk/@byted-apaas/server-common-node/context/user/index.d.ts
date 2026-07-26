import { IUser } from './IUser';
import { LocaleWithUID, Locale } from './types';
export declare class User implements IUser {
    _id: number;
    initiator: {
        _locale: Locale;
    } & object;
    getLocale(userId: number): Promise<LocaleWithUID>;
    getLocale(userIdList: number[]): Promise<LocaleWithUID[]>;
    constructor(_id: number, locale: Locale);
}
