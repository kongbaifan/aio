declare class RateLimiter {
    private windowSize;
    private maxRequest;
    private requests;
    constructor(windowSizeMs: number, maxRequest: number);
    /**
     * 动态重置限流阈值
     * @param maxRequest 新的最大请求数
     * @returns 是否实际修改了阈值
     */
    resetRateLimiter(maxRequest: number): boolean;
    getReqLength(): number;
    getMaxRequest(): number;
    /**
     * 判断当前是否允许请求
     * @returns true 表示允许，false 表示拒绝
     */
    allowRequest(): boolean;
    /**
     * 清理过期的请求记录
     * @param now 当前时间戳
     */
    private cleanupExpiredRequests;
}
export declare const limiter: RateLimiter;
export {};
