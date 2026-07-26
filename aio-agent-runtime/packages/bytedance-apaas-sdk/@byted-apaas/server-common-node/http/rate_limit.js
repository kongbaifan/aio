"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.limiter = void 0;
class RateLimiter {
    constructor(windowSizeMs, maxRequest) {
        this.windowSize = windowSizeMs;
        this.maxRequest = maxRequest;
        this.requests = [];
    }
    /**
     * 动态重置限流阈值
     * @param maxRequest 新的最大请求数
     * @returns 是否实际修改了阈值
     */
    resetRateLimiter(maxRequest) {
        if (this.maxRequest === maxRequest) {
            return false;
        }
        this.maxRequest = maxRequest;
        return true;
    }
    getReqLength() {
        return this.requests.length;
    }
    getMaxRequest() {
        return this.maxRequest;
    }
    /**
     * 判断当前是否允许请求
     * @returns true 表示允许，false 表示拒绝
     */
    allowRequest() {
        if (this.maxRequest <= 0) { // 不限流模式
            return true;
        }
        const now = Date.now();
        this.cleanupExpiredRequests(now);
        if (this.requests.length < this.maxRequest) {
            this.requests.push(now);
            return true;
        }
        return false;
    }
    /**
     * 清理过期的请求记录
     * @param now 当前时间戳
     */
    cleanupExpiredRequests(now) {
        while (this.requests.length > 0 && now - this.requests[0] > this.windowSize) {
            this.requests.shift();
        }
    }
}
// 初始化与 Go 版本对应的默认配置
exports.limiter = new RateLimiter(1000, 0);
