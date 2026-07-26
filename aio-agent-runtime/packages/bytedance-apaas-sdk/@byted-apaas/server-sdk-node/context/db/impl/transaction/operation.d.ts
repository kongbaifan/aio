export declare class TransactionOperation {
    operationType: number;
    objectApiName: string;
    input: string;
    constructor(operationType: number, objectApiName: string, input: any);
}
export declare class CreateOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class UpdateOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class DeleteOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class BatchCreateOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class BatchUpdateOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class BatchDeleteOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
export declare class BatchUpdateSameValueOperation extends TransactionOperation {
    constructor(objectApiName: string, input: any);
}
