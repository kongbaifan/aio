export declare const ASC = "asc";
export declare const DESC = "desc";
export type OrderType = 'asc' | 'desc';
export declare class Order {
    field: string;
    type: string;
    direction: OrderType;
    constructor(fieldApiName: string, direction: OrderType);
}
