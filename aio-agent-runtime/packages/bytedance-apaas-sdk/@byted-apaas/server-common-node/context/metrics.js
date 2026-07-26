"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Metrics = void 0;
class Metrics {
    constructor(type, method, success, cost, isRetry) {
        this.type = type;
        this.method = method;
        this.success = success;
        this.cost = cost;
        this.isRetry = isRetry;
    }
}
exports.Metrics = Metrics;
