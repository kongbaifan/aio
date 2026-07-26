import { Order, OrderType } from './order';
import { Logic } from '../../../kunlun/operator/impl/logic';
export declare const defaultLimit = 200;
/**
 * 查询构造器，在 DB 中被初始化，用于构建一次查询
 */
export declare class QueryBuilder {
    objectApiName: string;
    dataSource: string;
    select: string[];
    where: Logic[];
    limit: number;
    isSetLimit: boolean;
    offset: number;
    order: Order[];
    logic: Logic;
    fuzzySearch: object;
    quickQuery: string;
    quickQueryFields: string[];
    constructor(objectApiName: string);
    addLogic(logic: Logic): void;
    getLogic(): Logic;
    addSelect(fieldApiName: string): void;
    addSelects(fields: string[]): void;
    getSelect(): string[];
    addOrder(field: string, orderType: OrderType): void;
    addOrders(fields: string[], orderType: OrderType): void;
    getOrder(): Order[];
    setOffset(offset: number): void;
    setLimit(limit: number): void;
    getLimit(): number;
    getOffset(): number;
}
