export declare class Metrics {
    type: string;
    method: string;
    success: boolean;
    cost: number;
    isRetry: boolean;
    constructor(type: string, method: string, success: boolean, cost: number, isRetry?: boolean);
}
