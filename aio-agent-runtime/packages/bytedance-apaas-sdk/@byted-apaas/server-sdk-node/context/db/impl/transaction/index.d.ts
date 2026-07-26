import { ITransaction, ITransactionWithCurrentObject, TransactionObject } from '../transaction';
import { TransactionOperation } from './operation';
import { currentObjApiName } from '../../../../data';
import { AppCtx } from '../../../../application/application';
type uuidOrRecordIDResult = {
    _id: uuidOrRecordID;
};
type uuidOrRecordID = number | string;
export declare class Transaction<T, mt> implements ITransaction<mt>, ITransactionWithCurrentObject<mt> {
    objectApiName: string;
    placeholders: Record<string, number>;
    operations: TransactionOperation[];
    uuid2result: Record<string, uuidOrRecordIDResult>;
    isCommit: boolean;
    authType: string;
    appCtx?: AppCtx;
    batchResults: (string | number)[][];
    constructor(objectApiName: string, appCtx?: AppCtx);
    currentObject(): TransactionObject<mt[currentObjApiName]>;
    object<T extends keyof mt>(objectApiName: T): TransactionObject<mt[T]>;
    commit(): Promise<void>;
    useSystemAuth(): this;
    useUserAuth(): this;
}
export {};
