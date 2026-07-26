export declare enum OperatorType {
    INSERT = "insert",
    FIND = "find",
    FIND_ONE = "findOne",
    DISTINCT = "distinct",
    DELETE = "delete",
    COUNT = "count",
    UPDATE = "update",
    REPLACE = "replace",
    AGGREGATE = "aggregate",
    BULK_WRITE = "bulkWrite",
    AUTOFILL_POPULATE_SPEC = "autofillPopulateSpec"
}
export declare class Order {
    name: string;
    direction: number;
    constructor(name: string, direction: number);
}
export declare class OrderASC extends Order {
    constructor(field: string);
}
export declare class OrderDESC extends Order {
    constructor(field: string);
}
