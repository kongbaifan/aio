"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MockPressureHttpClient = exports.PressureHttpClient = exports.getPressureDecelerator = exports.initPressureDecelerator = exports.PressureDecelerator = exports.newPressureConfigByJsonStr = void 0;
const utils = require("../utils/utils");
const request_1 = require("./request");
const openapi_1 = require("./openapi");
const config_1 = require("./config");
const constants_1 = require("./constants");
const DefaultPressureMaxSleeptime = 1000; // 1s
const DefaultPressureUpdateInterval = 5000; // 5s
const DefaultPressureMaxKeyCapacity = 1000; // 1000个
const DefaultPressureEvictThreshold = 1 * 60 * 1000; // 1min
const defaultPressureConfig = {
    MaxSleeptime: DefaultPressureMaxSleeptime,
    UpdateInterval: DefaultPressureUpdateInterval,
    MaxKeyCapacity: DefaultPressureMaxKeyCapacity,
    EvictThreshold: DefaultPressureEvictThreshold,
};
function newPressureConfigByJsonStr(data) {
    if (!data) {
        return { ...defaultPressureConfig };
    }
    let config = { ...defaultPressureConfig }; // 初始化为默认配置
    try {
        // 使用对象合并保持默认值
        config = {
            ...config,
            ...JSON.parse(data), // 用户提供的配置会覆盖默认值
        };
    }
    catch (err) {
        console.error('NewPressureConfigByJsonStr json parse error:', err);
    }
    if ((config.MaxSleeptime ?? 0) === 0) {
        config.MaxSleeptime = DefaultPressureMaxSleeptime;
    }
    if (config.UpdateInterval <= 0) {
        config.UpdateInterval = DefaultPressureUpdateInterval;
    }
    if (config.MaxKeyCapacity <= 0) {
        config.MaxKeyCapacity = DefaultPressureMaxKeyCapacity;
    }
    if (config.EvictThreshold <= 0) {
        config.EvictThreshold = DefaultPressureEvictThreshold;
    }
    return config;
}
exports.newPressureConfigByJsonStr = newPressureConfigByJsonStr;
class PressureDeceleratorItem {
    constructor(key, sleeptime) {
        this.firstLoaded = false;
        this.key = key;
        this.sleeptime = sleeptime;
        this.lastReqTime = Date.now();
    }
}
class PressureDecelerator {
    constructor(ctx, config, client) {
        this.size = 0;
        this.updateIntervalId = null;
        this.updating = false;
        this.ctx = ctx;
        this.config = config;
        this.client = client;
        this.cache = new Map();
        console.log('[PressureDecelerator] init, config: ', JSON.stringify(config));
        if (config.UpdateInterval > 0) {
            this.updateIntervalId = setInterval(async () => await this.runUpdateTask(), config.UpdateInterval);
        }
    }
    async getSleeptime(key) {
        if (!key) {
            return 0;
        }
        let item = this.cache.get(key);
        if (!item) {
            item = new PressureDeceleratorItem(key, 0);
            this.cache.set(key, item);
            this.size++;
        }
        if (!item.firstLoaded) {
            await this.updateOne(item);
            item.firstLoaded = true;
        }
        item.lastReqTime = Date.now();
        return item.sleeptime;
    }
    async updateOne(item) {
        try {
            let st = await this.client.getSleeptime(this.ctx, item.key);
            if (this.config.MaxSleeptime > 0) {
                st = Math.min(st, this.config.MaxSleeptime);
            }
            item.sleeptime = st;
        }
        catch (err) {
            console.error('PressureDecelerator http client error:', err);
            item.sleeptime = 0;
        }
    }
    async runUpdateTask() {
        if (this.updating) {
            return;
        }
        this.updating = true;
        try {
            const now = Date.now();
            const evictKeys = [];
            const updateKeys = [];
            const sortKeys = new Map();
            // 遍历缓存并分类
            for (const [key, item] of this.cache.entries()) {
                if (now - item.lastReqTime > this.config.EvictThreshold) {
                    evictKeys.push(key);
                }
                else {
                    updateKeys.push(key);
                    sortKeys.set(key, item.lastReqTime); // 记录对应key的lastReqTime
                }
            }
            // 淘汰过期key
            evictKeys.forEach(key => {
                this.cache.delete(key);
                this.size--;
            });
            if (updateKeys.length > 0) {
                // 按最后请求时间降序排序
                updateKeys.sort((a, b) => sortKeys.get(b) - sortKeys.get(a));
                // 超过最大容量时淘汰最早的key
                if (this.config.MaxKeyCapacity > 0 && updateKeys.length > this.config.MaxKeyCapacity) {
                    const toEvict = updateKeys.splice(this.config.MaxKeyCapacity);
                    toEvict.forEach(key => {
                        this.cache.delete(key);
                        this.size--;
                    });
                }
                // 批量更新剩余key
                const res = await this.client.batchGetSleeptime(this.ctx, updateKeys);
                if (this.config.MaxSleeptime > 0) {
                    updateKeys.forEach(key => {
                        const item = this.cache.get(key);
                        if (item) {
                            item.sleeptime = Math.min(res[key] || 0, this.config.MaxSleeptime);
                        }
                    });
                }
                else {
                    updateKeys.forEach(key => {
                        const item = this.cache.get(key);
                        if (item) {
                            item.sleeptime = res[key] || 0;
                        }
                    });
                }
            }
        }
        finally {
            this.updating = false;
        }
    }
    stop() {
        if (this.updateIntervalId) {
            clearInterval(this.updateIntervalId);
        }
    }
    updateCtx(ctx) {
        this.ctx = ctx;
    }
    updateConfig(config) {
        this.config = config;
    }
}
exports.PressureDecelerator = PressureDecelerator;
// 单例模式实现
let pressureDeceleratorInstance = null;
function initPressureDecelerator(ctx, config) {
    if (!pressureDeceleratorInstance) { // 实例初始化
        // const client = new MockPressureHttpClient();
        const client = new PressureHttpClient();
        pressureDeceleratorInstance = new PressureDecelerator(ctx, config, client);
        console.log('[PressureDecelerator] initialized');
        return;
    }
    // 更新
    pressureDeceleratorInstance.updateCtx(ctx);
    pressureDeceleratorInstance.updateConfig(config);
    return;
}
exports.initPressureDecelerator = initPressureDecelerator;
function getPressureDecelerator() {
    return pressureDeceleratorInstance;
}
exports.getPressureDecelerator = getPressureDecelerator;
// http client implements
const BatchQueryPressureSignalPath = '/v1/namespaces/:namespace/arch_service/pressure/batch_query';
const pressureDefaultReqTimeout = 20000; // 反压中心接口 20s超时
class PressureHttpClient {
    async getSleeptime(ctx, key) {
        const resp = await this.batchGetSleeptime(ctx, [key]);
        return resp[key] || 0;
    }
    async batchGetSleeptime(_ctx, keys) {
        try {
            const setting = new config_1.PostHttpConfig(BatchQueryPressureSignalPath, constants_1.metricsMethodKeys.pressureSdk, pressureDefaultReqTimeout);
            const path = BatchQueryPressureSignalPath.replace(constants_1.replaceKeys.namespace, utils.getNamespaceFromCtx());
            const options = (0, request_1.getOptions)(null, setting);
            options.json = {
                'signal_list': keys,
            };
            options._skipPreIntercept = true;
            const resp = await (0, openapi_1.doRequest)(null, path, options) || {};
            console.log(`batchGetSleeptime response: ${JSON.stringify(resp)}`);
            return resp['pressure_signal_map'] || {};
        }
        catch (err) {
            console.error('PressureHttpClient request failed:', err);
            throw err;
        }
    }
}
exports.PressureHttpClient = PressureHttpClient;
class MockPressureHttpClient {
    async getSleeptime(_ctx, _key) {
        return 1000;
    }
    async batchGetSleeptime(_ctx, keys) {
        const res = {};
        for (const key of keys) {
            res[key] = 1000;
        }
        return res;
    }
}
exports.MockPressureHttpClient = MockPressureHttpClient;
