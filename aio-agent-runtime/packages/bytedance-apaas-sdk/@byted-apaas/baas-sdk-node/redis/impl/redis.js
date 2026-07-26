"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Redis = void 0;
const faasinfra_1 = require("../../http/faasinfra");
const constants_1 = require("../../constants/constants");
const common = require("@byted-apaas/server-common-node");
const exception = common.exceptions;
const checkUtils = common.checkUtils;
const InvalidParamError = exception.InvalidParamError;
const argsLengthErrMsg = constants_1.ErrMsg.argsLengthErrMsg;
class Redis {
    /**
     * 删除一个或多个 key
     * @param key 键名
     * @param keys 多个键名
     */
    async del(key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.DEL, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 判断一个 key 是否存在
     * @param key 键名
     */
    async exists(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.EXISTS, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 设置一个 key 的过期时间，单位为秒
     * @param key 键名
     * @param seconds 时间（秒）
     */
    async expire(key, seconds) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.EXPIRE, parseArgToStr(key), parseArgToNum(seconds)));
    }
    /**
     * 以秒为精度设置一个 key 的绝对过期时间
     * @param key 键名
     * @param timestamp 绝对过期时间（精度：秒）
     */
    async expireat(key, timestamp) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.EXPIREAT, parseArgToStr(key), parseArgToNum(timestamp)));
    }
    /**
     * 持久化一个 key，即删除掉 key 上设置的过期时间，并且将其置为永不过期
     * @param key 键名
     */
    async persist(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PERSIST, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 设置一个 key 的过期时间，单位为毫秒
     * @param key 键名
     * @param milliseconds 时间（毫秒）
     */
    async pexpire(key, milliseconds) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PEXPIRE, parseArgToStr(key), parseArgToNum(milliseconds)));
    }
    /**
     * 以毫秒为单位设置一个 key 的绝对过期时间
     * @param key 键名
     * @param millisecondsTimestamp 绝对过期时间（毫秒）
     */
    async pexpireat(key, millisecondsTimestamp) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PEXPIREAT, parseArgToStr(key), parseArgToNum(millisecondsTimestamp)));
    }
    /**
     * 以毫秒为单位返回 key 的剩余存活时间
     * @param key 键名
     */
    async pttl(key) {
        checkArgsLength(arguments, 1);
        let res = await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PTTL, ...batchParseArgToStr(...arguments)));
        if (res < 0) {
            return res;
        }
        else {
            return Math.floor(res / constants_1.MillSecondDuration);
        }
    }
    /**
     * 以秒为单位返回 key 的剩余存活时间
     * @param key 键值
     */
    async ttl(key) {
        checkArgsLength(arguments, 1);
        let res = await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.TTL, ...batchParseArgToStr(...arguments)));
        if (res < 0) {
            return res;
        }
        else {
            return Math.floor(res / constants_1.SecondDuration);
        }
    }
    /**
     * 返回 key 的类型
     * @param key 键值
     */
    async type(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.TYPE, ...batchParseArgToStr(...arguments)));
    }
    // strings command
    /**
     * 追加部分内容到 key 的值后，如果 key 不存在，则创建一个空字符串后追加到之后
     * @param key 键值
     * @param value 追加值
     */
    async append(key, value) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.APPEND, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 统计 key 中的值所占用的比特数，如果 key 不存在，则返回 0
     * @param key 键值
     * @param start 统计范围区间左端点，闭区间
     * @param end 统计范围区间右端点，闭区间
     */
    async bitcount(key, start, end) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.BITCOUNT, parseArgToStr(key), parseArgToNum(start), parseArgToNum(end)));
    }
    /**
     * 对 key 中存储的数值进行减一，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再减一
     * @param key 键值
     */
    async decr(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.DECR, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 对 key 中存储的数值执行减操作，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再减去设定的减数
     * @param key 键值
     * @param decrement 减数
     */
    async decrby(key, decrement) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.DECRBY, parseArgToStr(key), parseArgToNum(decrement)));
    }
    /**
     * 获取 key 中存储的值
     * @param key 键值
     */
    async get(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.GET, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 基于偏移量获取 key 中存储的值的某一位的比特值，如果超出了存储值的长度，则返回 0
     * @param key 键值
     * @param offset 偏移量
     */
    async getbit(key, offset) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.GETBIT, parseArgToStr(key), parseArgToNum(offset)));
    }
    /**
     * redis 早期版本中的 SUBSTR 方法，获取子字符串
     * @param key 键值
     * @param start 子字符串的开始位置
     * @param end 子字符串的结束位置
     */
    async getrange(key, start, end) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.GETRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(end)));
    }
    /**
     * 原子性地设置一个 key 的值，并且返回 key 中原先存储的值，如果 key 不存在，则设置后返回 nil
     * @param key 键值
     * @param value 值
     */
    async getset(key, value) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.GETSET, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 对 key 中存储的数值进行加一，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再加一
     * @param key 键值
     */
    async incr(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.INCR, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 对 key 中存储的数值执行加操作，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再加上设定的加数
     * @param key 键值
     * @param increment 加数
     */
    async incrby(key, increment) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.INCRBY, parseArgToStr(key), parseArgToNum(increment)));
    }
    /**
     * 对 key 中存储的数值执行浮点数加操作，如果 key 不存在，则创建该值为浮点数零后再加上设定的加数
     * @param key 键值
     * @param increment 加数（可以为负数，可以用科学计数法表示）
     */
    async incrbyfloat(key, increment) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.INCRBYFLOAT, parseArgToStr(key), parseArgToNum(increment)));
    }
    async mget(...args) {
        if (arguments.length == 1 && Array.isArray(arguments[0])) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.MGET, ...batchParseArgToStr(...arguments[0])));
        }
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.MGET, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 设置 key 的时候同时以毫秒为单位设置过期时间
     * @param key 键值
     * @param milliseconds 过期时间（毫秒）
     * @param value 值
     */
    async psetex(key, milliseconds, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PSETEX, parseArgToStr(key), parseArgToNum(milliseconds), parseArgToStr(value)));
    }
    async set(key, value, expireMode, expire, setType) {
        switch (arguments.length) {
            case 2: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SET, ...batchParseArgToStr(...arguments)));
            }
            case 3: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SET, ...batchParseArgToStr(...arguments)));
            }
            case 4: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SET, parseArgToStr(key), parseArgToStr(value), parseArgToStr(expireMode), parseArgToNum(expire)));
            }
            case 5: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SET, parseArgToStr(key), parseArgToStr(value), parseArgToStr(expireMode), parseArgToNum(expire), parseArgToStr(setType)));
            }
            default: {
                throw new InvalidParamError(argsLengthErrMsg);
            }
        }
    }
    async mset(...args) {
        switch (arguments.length) {
            case 0:
                throw new InvalidParamError(argsLengthErrMsg);
            case 1:
                let arg = arguments[0];
                let arr = [];
                if (checkUtils.isObject(arg)) {
                    for (let [k, v] of Object.entries(arg)) {
                        arr.push(parseArgToStr(k), parseArgToStr(v));
                    }
                }
                else if (Array.isArray(arg)) {
                    arr = batchParseArgToStr(...arg);
                }
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.MSET, ...arr));
            default:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.MSET, ...batchParseArgToStr(...arguments)));
        }
    }
    /**
     * 基于偏移量设置 key 中存储的值的某一位的比特值
     * @param key 键值
     * @param offset 偏移量
     * @param value 值（0 或 1）
     */
    async setbit(key, offset, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SETBIT, parseArgToStr(key), parseArgToNum(offset), parseArgToNum(value)));
    }
    /**
     * 设置 key 的时候同时以秒为单位设置过期时间
     * @param key 键值
     * @param seconds 过期时间（秒）
     * @param value 值
     */
    async setex(key, seconds, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SETEX, parseArgToStr(key), parseArgToNum(seconds), parseArgToStr(value)));
    }
    /**
     * 设置不存在的 key 的值，如果 key 已经存在的话，设置是无效的
     * @param key 键值
     * @param value 值
     */
    async setnx(key, value) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SETNX, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 基于偏移量设置 key 中存储的值
     * @param key 键值
     * @param offset 偏移量
     * @param value 值
     */
    async setrange(key, offset, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SETRANGE, parseArgToStr(key), parseArgToNum(offset), parseArgToStr(value)));
    }
    /**
     * 获取 key 中存储值的长度，如果 key 不存在，则返回 0
     * @param key 键值
     */
    async strlen(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.STRLEN, parseArgToStr(key)));
    }
    // hashes
    /**
     * 移除 key 中存储的哈希结构中的一个或者多个字段
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param fields 多个哈希结构中的字段名
     */
    async hdel(key, field, ...fields) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HDEL, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 判断 key 中存储的哈希结构中某个字段是是否存在
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     */
    async hexists(key, field) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HEXISTS, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的哈希结构中的某个字段值
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     */
    async hget(key, field) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HGET, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的哈希结构中的全部字段名和值
     * @param key 哈希结构的键值
     */
    async hgetall(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HGETALL, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 对 key 中存储的哈希结构中的某一个数字字段执行加操作，加数为整型
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param increment 加数（整形）
     */
    async hincrby(key, field, increment) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HINCRBY, parseArgToStr(key), parseArgToStr(field), parseArgToNum(increment)));
    }
    /**
     * 对 key 中存储的哈希结构中的某一个数字字段执行加操作，加数为浮点型
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param increment 加数（浮点型）
     */
    async hincrbyfloat(key, field, increment) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HINCRBYFLOAT, parseArgToStr(key), parseArgToStr(field), parseArgToNum(increment)));
    }
    /**
     * 获取 key 中存储的哈希结构的全部字段名
     * @param key 哈希结构的键值
     */
    async hkeys(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HKEYS, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的哈希结构的字段数
     * @param key 哈希结构的键值
     */
    async hlen(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HLEN, ...batchParseArgToStr(...arguments)));
    }
    async hmget(...args) {
        if (arguments.length == 2 && Array.isArray(arguments[1])) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HMGET, parseArgToStr(arguments[0]), ...batchParseArgToStr(...arguments[1])));
        }
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HMGET, ...batchParseArgToStr(...arguments)));
    }
    async hmset(...args) {
        switch (arguments.length) {
            case 0:
                throw new InvalidParamError(argsLengthErrMsg);
            case 1:
                throw new InvalidParamError(argsLengthErrMsg);
            case 2:
                let arg = arguments[1];
                let arr = [];
                if (checkUtils.isObject(arg)) {
                    for (let [k, v] of Object.entries(arg)) {
                        arr.push(parseArgToStr(k), parseArgToStr(v));
                    }
                }
                else if (Array.isArray(arg)) {
                    arr = batchParseArgToStr(...arg);
                }
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HMSET, parseArgToStr(arguments[0]), ...arr));
            default:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HMSET, ...batchParseArgToStr(...arguments)));
        }
    }
    /**
     * 设置 key 中存储的哈希结构的字段值
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param value 期望设定的值
     */
    async hset(key, field, value) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HSET, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 设置 key 中存储的哈希结构中不存在的字段值，如果该字段已经存在的话，设置是无效的
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param value 期望设定的值
     */
    async hsetnx(key, field, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HSETNX, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的哈希结构的全部字段值
     * @param key 哈希结构的键值
     */
    async hvals(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.HVALS, ...batchParseArgToStr(...arguments)));
    }
    // lists
    /**
     * 获取 key 中存储的列表中某一个下标所存储的值
     * @param key 列表的键值
     * @param index 下标（从 0 开始，可以为负数）
     */
    async lindex(key, index) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LINDEX, parseArgToStr(key), parseArgToNum(index)));
    }
    /**
     * 获取 key 中存储的列表的长度
     * @param key 列表的键值
     */
    async llen(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LLEN, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 删除并且获取 key 中存储的列表中的第一个值
     * @param key 列表的键值
     */
    async lpop(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LPOP, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个或多个值顺序插入到 key 中存储的列表的第一个位置，如果 key 不存在，将创建一个列表
     * @param key 列表的键值
     * @param value 单个期望插入的值
     * @param values 多个期望插入的值
     */
    async lpush(key, value, ...values) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LPUSH, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个值插入到 key 中存储的列表的第一个位置，key 不存在时将不做任何操作
     * @param key 列表的键值
     * @param value 期望插入的值
     */
    async lpushx(key, value) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LPUSHX, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的列表的某个范围内的全部值
     * @param key 列表的键值
     * @param start 范围区间左端点，闭区间
     * @param stop 范围区间右端点，闭区间
     */
    async lrange(key, start, stop) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop)));
    }
    /**
     * 删除 key 中存储的列表中一个或多个与给定值相等的值
     * @param key 列表的键值
     * @param count 删除值的数量；大于零时，代表从列表头向尾删除若干值，小于零时，代表从列表尾向头删除若干值，等于零时，代表删除全部符合条件的值
     * @param value 需要删除的值
     */
    async lrem(key, count, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LREM, parseArgToStr(key), parseArgToNum(count), parseArgToStr(value)));
    }
    /**
     * 设置 key 中存储的列表中某一个下标的值
     * @param key 列表的键值
     * @param index 下标（从 0 开始，可以为负数）
     * @param value 期望设置的值
     */
    async lset(key, index, value) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LSET, parseArgToStr(key), parseArgToNum(index), parseArgToStr(value)));
    }
    /**
     * 删去 key 中存储的列表中某个范围内的全部值，如果范围的左端点大于右端点，则会删除整个列表
     * @param key 列表的键值
     * @param start 范围区间左端点，闭区间
     * @param stop 范围区间右端点，闭区间
     */
    async ltrim(key, start, stop) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.LTRIM, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop)));
    }
    /**
     * 删除并且获取 key 中存储的列表的最后一个值
     * @param key 列表的键值
     */
    async rpop(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.RPOP, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 原子性的删除 source 中存储的列表的最后一个值，并将其插入到 destination 中存储的列表的第一个位置
     * @param source 源列表的键值
     * @param destination 目标列表的键值
     */
    async rpoplpush(source, destination) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.RPOPLPUSH, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个或多个值顺序插入到 key 中存储的列表的最后，如果 key 不存在，将创建一个列表
     * @param key 列表的键值
     * @param value 单个期望插入的值
     * @param values 多个期望插入的值
     */
    async rpush(key, value, ...values) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.RPUSH, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个给定值插入到 key 中存储的列表的最后，如果 key 不存在，将不执行任何操作
     * @param key 列表的键值
     * @param value 期望插入的值
     */
    async rpushx(key, value) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.RPUSHX, ...batchParseArgToStr(...arguments)));
    }
    // sets
    /**
     * 添加元素到 key 中存储的集合中
     * @param key 集合的键值
     * @param member 单个期望添加的元素值
     * @param members 多个期望添加的元素值
     */
    async sadd(key, member, ...members) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SADD, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的集合的元素个数
     * @param key 集合的键值
     */
    async scard(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SCARD, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取由第一个集合和所有后续集合之间的差集
     * @param key 集合的键值
     * @param keys 后续集合的键值
     */
    async sdiff(key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SDIFF, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将由第一个集合和所有后续集合之间的差集存储在 destination 中
     * @param destination 目标集合的键值
     * @param key 集合的键值
     * @param keys 后续集合的键值
     */
    async sdiffstore(destination, key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SDIFFSTORE, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取一个或多个集合的交集
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    async sinter(key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SINTER, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个或多个集合的交集存储在 destination 中
     * @param destination 目标集合的键值
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    async sinterstore(destination, key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SINTERSTORE, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 判断一个元素值是否存在于 key 中存储的集合中
     * @param key 集合的键值
     * @param member 元素值
     */
    async sismember(key, member) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SISMEMBER, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的集合的全部元素值
     * @param key 集合的键值
     */
    async smembers(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SMEMBERS, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将 source 中存储的集合中的某个元素移动到 destination 中存储的集合中
     * @param source 源集合的键值
     * @param destination 目标集合的键值
     * @param member 元素值
     */
    async smove(source, destination, member) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SMOVE, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 随机删除并获取 key 中存储的集合中的一个或多个元素值
     * @param key 集合的键值
     * @param count 缺省参数；元素的数量
     */
    async spop(key, count) {
        switch (arguments.length) {
            case 1:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SPOP, parseArgToStr(key)));
            case 2:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SPOP, parseArgToStr(key), parseArgToNum(count)));
            default:
                throw new InvalidParamError(argsLengthErrMsg);
        }
    }
    /**
     * 随机从 key 中存储的集合中获取一个或多个元素值
     * @param key 集合的键值
     * @param count 缺省参数；元素的数量
     */
    async srandmember(key, count) {
        switch (arguments.length) {
            case 1:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SRANDMEMBER, parseArgToStr(key)));
            case 2:
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SRANDMEMBER, parseArgToStr(key), parseArgToNum(count)));
            default:
                throw new InvalidParamError(argsLengthErrMsg);
        }
    }
    /**
     * 删除 key 中存储的集合中的一个或多个元素
     * @param key 集合的键值
     * @param member 单个待删除的元素值
     * @param members 多个待删除的元素值
     */
    async srem(key, member, ...members) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SREM, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取一个或多个集合的并集
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    async sunion(key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SUNION, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 将一个或多个集合的并集存储到 destination 中
     * @param destination 目标集合的键值
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    async sunionstore(destination, key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.SUNIONSTORE, ...batchParseArgToStr(...arguments)));
    }
    // sorted sets
    async zadd(key, score, member, ...scoreAndMembers) {
        if (arguments.length < 3) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let res = [];
        for (let i = 0; i < arguments.length; i++) {
            if (i % 2 === 0) { // string
                res.push(parseArgToStr(arguments[i]));
            }
            else { // number
                res.push(parseArgToNum(arguments[i]));
            }
        }
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZADD, ...res));
    }
    /**
     * 获取 key 中存储的有序集合的元素个数
     * @param key 有序集合的键值
     */
    async zcard(key) {
        checkArgsLength(arguments, 1);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZCARD, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的有序集合中分数在 min 和 max 之间的元素个数
     * @param key 有序集合的键值
     * @param min 分数的最小值，闭区间
     * @param max 分数的最大值，闭区间
     */
    async zcount(key, min, max) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZCOUNT, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 对 key 中存储的有序集合中的某个元素的分数执行加操作
     * @param key 有序集合的键值
     * @param increment 分数的加数
     * @param member 元素值
     */
    async zincrby(key, increment, member) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZINCRBY, parseArgToStr(key), parseArgToNum(increment), parseArgToStr(member)));
    }
    async zinterstore(destination, numkeys, ...key1) {
        // key 2 key1 key2 weights 2 3 aggregate min
        if (arguments.length < 2) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let curKey = parseArgToStr([arguments[0]]);
        let numKeys = parseArgToNum(arguments[1]);
        let index = 2 + numKeys;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let keys = [];
        for (let i = 2; i < index; i++) {
            keys.push(parseArgToStr(arguments[i]));
        }
        if (arguments.length === index) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZINTERSTORE, curKey, numKeys, ...keys));
        }
        let weightKey = parseArgToStr(arguments[index]);
        if (weightKey.toLowerCase() !== 'weights') {
            throw new InvalidParamError(`weightKey is not correct`);
        }
        index += numKeys + 1;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let weightNums = [];
        for (let i = 2 + numKeys + 1; i < index; i++) {
            weightNums.push(parseArgToNum(arguments[i]));
        }
        if (arguments.length === index) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZINTERSTORE, curKey, numKeys, ...keys, weightKey, ...weightNums));
        }
        let aggKey = parseArgToStr(arguments[index]);
        if (aggKey.toLowerCase() !== 'aggregate') {
            throw new InvalidParamError(`aggregateKey is not correct`);
        }
        index += 1;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let aggregate = parseArgToStr(arguments[index]);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZINTERSTORE, curKey, numKeys, ...keys, weightKey, ...weightNums, aggKey, aggregate));
    }
    async zrange(key, start, stop, withscores) {
        switch (arguments.length) {
            case 3: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop)));
            }
            case 4: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop), parseArgToStr(withscores)));
            }
            default:
                throw new InvalidParamError(argsLengthErrMsg);
        }
    }
    async zrangebyscore(key, min, max) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZRANGEBYSCORE, ...batchParseArgToStr(...arguments)));
    }
    async zrank(key, member) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZRANK, ...batchParseArgToStr(...arguments)));
    }
    async zrem(key, member, ...members) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREM, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 根据给定排名范围删除 key 中存储的有序集合的若干元素
     * @param key 有序集合的键值
     * @param start 范围区间的左端点，闭区间
     * @param stop 范围区间的右端点，闭区间
     */
    async zremrangebyrank(key, start, stop) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREMRANGEBYRANK, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop)));
    }
    /**
     * 根据给定分数范围删除 key 中存储的有序集合的若干元素
     * @param key 有序集合的键值
     * @param min 范围区间的左端点，闭区间
     * @param max 范围区间的右端点，闭区间
     */
    async zremrangebyscore(key, min, max) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREMRANGEBYSCORE, ...batchParseArgToStr(...arguments)));
    }
    async zrevrange(key, start, stop, withscores) {
        switch (arguments.length) {
            case 3: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREVRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop)));
            }
            case 4: {
                return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREVRANGE, parseArgToStr(key), parseArgToNum(start), parseArgToNum(stop), parseArgToStr(withscores)));
            }
            default:
                throw new InvalidParamError(argsLengthErrMsg);
        }
    }
    /**
     * 以逆序获取 key 中存储的有序集合中在给定分数范围内的若干元素
     * @param key 有序集合的键值
     * @param max 范围区间的右端点，闭区间
     * @param min 范围区间的左端点，闭区间
     */
    async zrevrangebyscore(key, max, min) {
        checkArgsLength(arguments, 3);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREVRANGEBYSCORE, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 以逆序获取 key 中存储的有序集合的某个元素的排名
     * @param key 有序集合的键值
     * @param member 元素值
     */
    async zrevrank(key, member) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZREVRANK, ...batchParseArgToStr(...arguments)));
    }
    /**
     * 获取 key 中存储的有序集合中某个元素的分数
     * @param key 有序集合的键值
     * @param member 元素值
     */
    async zscore(key, member) {
        checkArgsLength(arguments, 2);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZSCORE, ...batchParseArgToStr(...arguments)));
    }
    async zunionstore(destination, numkeys, ...key) {
        // key 2 key1 key2 weights 2 3 aggregate min
        if (arguments.length < 2) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let curKey = parseArgToStr([arguments[0]]);
        let numKeys = parseArgToNum(arguments[1]);
        let index = 2 + numKeys;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let keys = [];
        for (let i = 2; i < index; i++) {
            keys.push(parseArgToStr(arguments[i]));
        }
        if (arguments.length === index) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZUNIONSTORE, curKey, numKeys, ...keys));
        }
        let weightKey = parseArgToStr(arguments[index]);
        if (weightKey.toLowerCase() !== 'weights') {
            throw new InvalidParamError(`weightKey is not correct`);
        }
        index += numKeys + 1;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let weightNums = [];
        for (let i = 2 + numKeys + 1; i < index; i++) {
            weightNums.push(parseArgToNum(arguments[i]));
        }
        if (arguments.length === index) {
            return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZUNIONSTORE, curKey, numKeys, ...keys, weightKey, ...weightNums));
        }
        let aggKey = parseArgToStr(arguments[index]);
        if (aggKey.toLowerCase() !== 'aggregate') {
            throw new InvalidParamError(`aggregateKey is not correct`);
        }
        index += 1;
        if (arguments.length < index) {
            throw new InvalidParamError(argsLengthErrMsg);
        }
        let aggregate = parseArgToStr(arguments[index]);
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.ZUNIONSTORE, curKey, numKeys, ...keys, weightKey, ...weightNums, aggKey, aggregate));
    }
    async pfadd(key, ...elements) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PFADD, ...batchParseArgToStr(...arguments)));
    }
    async pfcount(key, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PFCOUNT, ...batchParseArgToStr(...arguments)));
    }
    async pfmerge(dest, ...keys) {
        return await (0, faasinfra_1.requestRedis)(getRedisParam(constants_1.redisCmd.PFMERGE, ...batchParseArgToStr(...arguments)));
    }
}
exports.Redis = Redis;
function getRedisParam(cmd, ...args) {
    return {
        cmd: cmd,
        args: args
    };
}
function parseArgToStr(arg) {
    if (arg === undefined || arg === null) {
        return '';
    }
    return arg.toString();
}
function batchParseArgToStr(...args) {
    let res = [];
    for (const arg of args) {
        res.push(parseArgToStr(arg));
    }
    return res;
}
function parseArgToNum(arg) {
    if (arg === undefined || arg === null) {
        throw new InvalidParamError(`arg ${arg} is not a number`);
    }
    let res = Number(arg);
    if (isNaN(res)) {
        throw new InvalidParamError(`arg ${arg} is not a number`);
    }
    return res;
}
function checkArgsLength(args, length) {
    if (args.length !== length) {
        throw new InvalidParamError(argsLengthErrMsg);
    }
}
