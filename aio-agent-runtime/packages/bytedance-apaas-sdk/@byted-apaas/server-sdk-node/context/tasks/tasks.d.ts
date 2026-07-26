export declare class _Options {
    /**
     * 并发数量，默认值为 5，最大可设置值为 10
     */
    concurrency?: number;
    /**
     * 单个子任务的最大数据量，默认值为 5，最大可设置值为 100
     */
    maxSliceNumber?: number;
    /**
     * 触发进度回调函数的步长，以百分比为单位，每当发生大于等于步长的进度变化时，便触发进度回调函数。默认为每当有进度变化时，便触发进度回调函数（进度变化精度为 1%）
     */
    progressCallbackStep?: number;
}
export declare class Tasks<cf> {
    private f;
    constructor(_f?: Function);
    /**
     * 创建异步任务
     * @param apiName 函数的 apiName
     * @param params 参数
     */
    createAsyncTask(apiName: cf, params: object): Promise<void>;
    /**
     * 创建分布式任务
     * @param dataset 待处理数据组成的数组
     * @param handlerFunc 用于处理数据集的全局函数的 API name
     * @param progressCallbackFunc 任务进度发生变化时回调的全局函数的 API name，可通过传入 '' / null / undefined 跳过此步骤
     * @param completedCallbackFunc 任务完成时回调的全局函数的 API name，可通过传入 '' / null / undefined 跳过此步骤
     * @param options 高级配置参数，可选
     */
    createDistributedTask(dataset: any[], handlerFunc: cf, progressCallbackFunc: cf | '' | null | undefined, completedCallbackFunc: cf | '' | null | undefined, options?: _Options): Promise<number>;
}
