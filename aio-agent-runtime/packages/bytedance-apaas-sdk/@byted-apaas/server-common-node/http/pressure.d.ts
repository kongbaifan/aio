interface PressureConfig {
    MaxSleeptime: number;
    UpdateInterval: number;
    MaxKeyCapacity: number;
    EvictThreshold: number;
}
interface IPressureHttpClient {
    getSleeptime(ctx: any, key: string): Promise<number>;
    batchGetSleeptime(ctx: any, keys: string[]): Promise<Record<string, number>>;
}
export declare function newPressureConfigByJsonStr(data: string): PressureConfig;
export declare class PressureDecelerator {
    private config;
    private ctx;
    private client;
    private cache;
    private size;
    private updateIntervalId;
    private updating;
    constructor(ctx: any, config: PressureConfig, client: IPressureHttpClient);
    getSleeptime(key: string): Promise<number>;
    private updateOne;
    private runUpdateTask;
    stop(): void;
    updateCtx(ctx: any): void;
    updateConfig(config: PressureConfig): void;
}
export declare function initPressureDecelerator(ctx: any, config: PressureConfig): void;
export declare function getPressureDecelerator(): PressureDecelerator | null;
export declare class PressureHttpClient implements IPressureHttpClient {
    getSleeptime(ctx: any, key: string): Promise<number>;
    batchGetSleeptime(_ctx: any, keys: string[]): Promise<Record<string, number>>;
}
export declare class MockPressureHttpClient implements IPressureHttpClient {
    getSleeptime(_ctx: any, _key: string): Promise<number>;
    batchGetSleeptime(_ctx: any, keys: string[]): Promise<Record<string, number>>;
}
export {};
