import { IRedis } from '../IRedis';
export declare class Redis implements IRedis {
    /**
     * 删除一个或多个 key
     * @param key 键名
     * @param keys 多个键名
     */
    del(key: string, ...keys: string[]): Promise<any>;
    /**
     * 判断一个 key 是否存在
     * @param key 键名
     */
    exists(key: string): Promise<any>;
    /**
     * 设置一个 key 的过期时间，单位为秒
     * @param key 键名
     * @param seconds 时间（秒）
     */
    expire(key: string, seconds: number): Promise<any>;
    /**
     * 以秒为精度设置一个 key 的绝对过期时间
     * @param key 键名
     * @param timestamp 绝对过期时间（精度：秒）
     */
    expireat(key: string, timestamp: number): Promise<any>;
    /**
     * 持久化一个 key，即删除掉 key 上设置的过期时间，并且将其置为永不过期
     * @param key 键名
     */
    persist(key: string): Promise<any>;
    /**
     * 设置一个 key 的过期时间，单位为毫秒
     * @param key 键名
     * @param milliseconds 时间（毫秒）
     */
    pexpire(key: string, milliseconds: number): Promise<any>;
    /**
     * 以毫秒为单位设置一个 key 的绝对过期时间
     * @param key 键名
     * @param millisecondsTimestamp 绝对过期时间（毫秒）
     */
    pexpireat(key: string, millisecondsTimestamp: number): Promise<any>;
    /**
     * 以毫秒为单位返回 key 的剩余存活时间
     * @param key 键名
     */
    pttl(key: string): Promise<any>;
    /**
     * 以秒为单位返回 key 的剩余存活时间
     * @param key 键值
     */
    ttl(key: string): Promise<any>;
    /**
     * 返回 key 的类型
     * @param key 键值
     */
    type(key: string): Promise<any>;
    /**
     * 追加部分内容到 key 的值后，如果 key 不存在，则创建一个空字符串后追加到之后
     * @param key 键值
     * @param value 追加值
     */
    append(key: string, value: string): Promise<any>;
    /**
     * 统计 key 中的值所占用的比特数，如果 key 不存在，则返回 0
     * @param key 键值
     * @param start 统计范围区间左端点，闭区间
     * @param end 统计范围区间右端点，闭区间
     */
    bitcount(key: string, start: number, end: number): Promise<any>;
    /**
     * 对 key 中存储的数值进行减一，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再减一
     * @param key 键值
     */
    decr(key: string): Promise<any>;
    /**
     * 对 key 中存储的数值执行减操作，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再减去设定的减数
     * @param key 键值
     * @param decrement 减数
     */
    decrby(key: string, decrement: number): Promise<any>;
    /**
     * 获取 key 中存储的值
     * @param key 键值
     */
    get(key: string): Promise<any>;
    /**
     * 基于偏移量获取 key 中存储的值的某一位的比特值，如果超出了存储值的长度，则返回 0
     * @param key 键值
     * @param offset 偏移量
     */
    getbit(key: string, offset: number): Promise<any>;
    /**
     * redis 早期版本中的 SUBSTR 方法，获取子字符串
     * @param key 键值
     * @param start 子字符串的开始位置
     * @param end 子字符串的结束位置
     */
    getrange(key: string, start: number, end: number): Promise<any>;
    /**
     * 原子性地设置一个 key 的值，并且返回 key 中原先存储的值，如果 key 不存在，则设置后返回 nil
     * @param key 键值
     * @param value 值
     */
    getset(key: string, value: string): Promise<any>;
    /**
     * 对 key 中存储的数值进行加一，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再加一
     * @param key 键值
     */
    incr(key: string): Promise<any>;
    /**
     * 对 key 中存储的数值执行加操作，仅限制于有符号 64 位整数，如果 key 不存在，则创建该值为零后再加上设定的加数
     * @param key 键值
     * @param increment 加数
     */
    incrby(key: string, increment: number): Promise<any>;
    /**
     * 对 key 中存储的数值执行浮点数加操作，如果 key 不存在，则创建该值为浮点数零后再加上设定的加数
     * @param key 键值
     * @param increment 加数（可以为负数，可以用科学计数法表示）
     */
    incrbyfloat(key: string, increment: number): Promise<any>;
    mget(keys: string[]): Promise<any>;
    mget(key: string, ...keys: string[]): Promise<any>;
    /**
     * 设置 key 的时候同时以毫秒为单位设置过期时间
     * @param key 键值
     * @param milliseconds 过期时间（毫秒）
     * @param value 值
     */
    psetex(key: string, milliseconds: number, value: string): Promise<any>;
    set(key: string, value: string): Promise<any>;
    set(key: string, value: string, setType: 'nx' | 'xx'): Promise<any>;
    set(key: string, value: string, expireMode: 'ex' | 'px', expire: number): Promise<any>;
    set(key: string, value: string, expireMode: 'ex' | 'px', expire: number, setType: 'nx' | 'xx'): Promise<any>;
    mset(kvArr: string[]): Promise<any>;
    mset(key: string, value: string, ...keyAndValue: string[]): Promise<any>;
    mset(keyAndValue: object): Promise<any>;
    /**
     * 基于偏移量设置 key 中存储的值的某一位的比特值
     * @param key 键值
     * @param offset 偏移量
     * @param value 值（0 或 1）
     */
    setbit(key: string, offset: number, value: 0 | 1): Promise<any>;
    /**
     * 设置 key 的时候同时以秒为单位设置过期时间
     * @param key 键值
     * @param seconds 过期时间（秒）
     * @param value 值
     */
    setex(key: string, seconds: number, value: string): Promise<any>;
    /**
     * 设置不存在的 key 的值，如果 key 已经存在的话，设置是无效的
     * @param key 键值
     * @param value 值
     */
    setnx(key: string, value: string): Promise<any>;
    /**
     * 基于偏移量设置 key 中存储的值
     * @param key 键值
     * @param offset 偏移量
     * @param value 值
     */
    setrange(key: string, offset: number, value: string): Promise<any>;
    /**
     * 获取 key 中存储值的长度，如果 key 不存在，则返回 0
     * @param key 键值
     */
    strlen(key: string): Promise<any>;
    /**
     * 移除 key 中存储的哈希结构中的一个或者多个字段
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param fields 多个哈希结构中的字段名
     */
    hdel(key: string, field: string, ...fields: string[]): Promise<any>;
    /**
     * 判断 key 中存储的哈希结构中某个字段是是否存在
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     */
    hexists(key: string, field: string): Promise<any>;
    /**
     * 获取 key 中存储的哈希结构中的某个字段值
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     */
    hget(key: string, field: string): Promise<any>;
    /**
     * 获取 key 中存储的哈希结构中的全部字段名和值
     * @param key 哈希结构的键值
     */
    hgetall(key: string): Promise<any>;
    /**
     * 对 key 中存储的哈希结构中的某一个数字字段执行加操作，加数为整型
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param increment 加数（整形）
     */
    hincrby(key: string, field: string, increment: number): Promise<any>;
    /**
     * 对 key 中存储的哈希结构中的某一个数字字段执行加操作，加数为浮点型
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param increment 加数（浮点型）
     */
    hincrbyfloat(key: string, field: string, increment: number): Promise<any>;
    /**
     * 获取 key 中存储的哈希结构的全部字段名
     * @param key 哈希结构的键值
     */
    hkeys(key: string): Promise<any>;
    /**
     * 获取 key 中存储的哈希结构的字段数
     * @param key 哈希结构的键值
     */
    hlen(key: string): Promise<any>;
    hmget(key: string, fields: string[]): Promise<any>;
    hmget(key: string, field: string, ...fields: string[]): Promise<any>;
    hmset(key: string, kvArr: string[]): Promise<any>;
    hmset(key: string, kvMap: object): Promise<any>;
    hmset(key: string, field: string, value: string, ...fieldValues: string[]): Promise<any>;
    /**
     * 设置 key 中存储的哈希结构的字段值
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param value 期望设定的值
     */
    hset(key: string, field: string, value: string): Promise<any>;
    /**
     * 设置 key 中存储的哈希结构中不存在的字段值，如果该字段已经存在的话，设置是无效的
     * @param key 哈希结构的键值
     * @param field 哈希结构中的字段名
     * @param value 期望设定的值
     */
    hsetnx(key: string, field: string, value: string): Promise<any>;
    /**
     * 获取 key 中存储的哈希结构的全部字段值
     * @param key 哈希结构的键值
     */
    hvals(key: string): Promise<any>;
    /**
     * 获取 key 中存储的列表中某一个下标所存储的值
     * @param key 列表的键值
     * @param index 下标（从 0 开始，可以为负数）
     */
    lindex(key: string, index: number): Promise<any>;
    /**
     * 获取 key 中存储的列表的长度
     * @param key 列表的键值
     */
    llen(key: string): Promise<any>;
    /**
     * 删除并且获取 key 中存储的列表中的第一个值
     * @param key 列表的键值
     */
    lpop(key: string): Promise<any>;
    /**
     * 将一个或多个值顺序插入到 key 中存储的列表的第一个位置，如果 key 不存在，将创建一个列表
     * @param key 列表的键值
     * @param value 单个期望插入的值
     * @param values 多个期望插入的值
     */
    lpush(key: string, value: string, ...values: string[]): Promise<any>;
    /**
     * 将一个值插入到 key 中存储的列表的第一个位置，key 不存在时将不做任何操作
     * @param key 列表的键值
     * @param value 期望插入的值
     */
    lpushx(key: string, value: string): Promise<any>;
    /**
     * 获取 key 中存储的列表的某个范围内的全部值
     * @param key 列表的键值
     * @param start 范围区间左端点，闭区间
     * @param stop 范围区间右端点，闭区间
     */
    lrange(key: string, start: number, stop: number): Promise<any>;
    /**
     * 删除 key 中存储的列表中一个或多个与给定值相等的值
     * @param key 列表的键值
     * @param count 删除值的数量；大于零时，代表从列表头向尾删除若干值，小于零时，代表从列表尾向头删除若干值，等于零时，代表删除全部符合条件的值
     * @param value 需要删除的值
     */
    lrem(key: string, count: number, value: string): Promise<any>;
    /**
     * 设置 key 中存储的列表中某一个下标的值
     * @param key 列表的键值
     * @param index 下标（从 0 开始，可以为负数）
     * @param value 期望设置的值
     */
    lset(key: string, index: number, value: string): Promise<any>;
    /**
     * 删去 key 中存储的列表中某个范围内的全部值，如果范围的左端点大于右端点，则会删除整个列表
     * @param key 列表的键值
     * @param start 范围区间左端点，闭区间
     * @param stop 范围区间右端点，闭区间
     */
    ltrim(key: string, start: number, stop: number): Promise<any>;
    /**
     * 删除并且获取 key 中存储的列表的最后一个值
     * @param key 列表的键值
     */
    rpop(key: string): Promise<any>;
    /**
     * 原子性的删除 source 中存储的列表的最后一个值，并将其插入到 destination 中存储的列表的第一个位置
     * @param source 源列表的键值
     * @param destination 目标列表的键值
     */
    rpoplpush(source: string, destination: string): Promise<any>;
    /**
     * 将一个或多个值顺序插入到 key 中存储的列表的最后，如果 key 不存在，将创建一个列表
     * @param key 列表的键值
     * @param value 单个期望插入的值
     * @param values 多个期望插入的值
     */
    rpush(key: string, value: string, ...values: string[]): Promise<any>;
    /**
     * 将一个给定值插入到 key 中存储的列表的最后，如果 key 不存在，将不执行任何操作
     * @param key 列表的键值
     * @param value 期望插入的值
     */
    rpushx(key: string, value: string): Promise<any>;
    /**
     * 添加元素到 key 中存储的集合中
     * @param key 集合的键值
     * @param member 单个期望添加的元素值
     * @param members 多个期望添加的元素值
     */
    sadd(key: string, member: string, ...members: string[]): Promise<any>;
    /**
     * 获取 key 中存储的集合的元素个数
     * @param key 集合的键值
     */
    scard(key: string): Promise<any>;
    /**
     * 获取由第一个集合和所有后续集合之间的差集
     * @param key 集合的键值
     * @param keys 后续集合的键值
     */
    sdiff(key: string, ...keys: string[]): Promise<any>;
    /**
     * 将由第一个集合和所有后续集合之间的差集存储在 destination 中
     * @param destination 目标集合的键值
     * @param key 集合的键值
     * @param keys 后续集合的键值
     */
    sdiffstore(destination: string, key: string, ...keys: string[]): Promise<any>;
    /**
     * 获取一个或多个集合的交集
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    sinter(key: string, ...keys: string[]): Promise<any>;
    /**
     * 将一个或多个集合的交集存储在 destination 中
     * @param destination 目标集合的键值
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    sinterstore(destination: string, key: string, ...keys: string[]): Promise<any>;
    /**
     * 判断一个元素值是否存在于 key 中存储的集合中
     * @param key 集合的键值
     * @param member 元素值
     */
    sismember(key: string, member: string): Promise<any>;
    /**
     * 获取 key 中存储的集合的全部元素值
     * @param key 集合的键值
     */
    smembers(key: string): Promise<any>;
    /**
     * 将 source 中存储的集合中的某个元素移动到 destination 中存储的集合中
     * @param source 源集合的键值
     * @param destination 目标集合的键值
     * @param member 元素值
     */
    smove(source: string, destination: string, member: string): Promise<any>;
    /**
     * 随机删除并获取 key 中存储的集合中的一个或多个元素值
     * @param key 集合的键值
     * @param count 缺省参数；元素的数量
     */
    spop(key: string, count?: number): Promise<any>;
    /**
     * 随机从 key 中存储的集合中获取一个或多个元素值
     * @param key 集合的键值
     * @param count 缺省参数；元素的数量
     */
    srandmember(key: string, count?: number): Promise<any>;
    /**
     * 删除 key 中存储的集合中的一个或多个元素
     * @param key 集合的键值
     * @param member 单个待删除的元素值
     * @param members 多个待删除的元素值
     */
    srem(key: string, member: string, ...members: string[]): Promise<any>;
    /**
     * 获取一个或多个集合的并集
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    sunion(key: string, ...keys: string[]): Promise<any>;
    /**
     * 将一个或多个集合的并集存储到 destination 中
     * @param destination 目标集合的键值
     * @param key 单个集合的键值
     * @param keys 多个集合的键值
     */
    sunionstore(destination: string, key: string, ...keys: string[]): Promise<any>;
    zadd(key: string, score: number, member: string, ...scoreAndMembers: (number | string)[]): Promise<any>;
    /**
     * 获取 key 中存储的有序集合的元素个数
     * @param key 有序集合的键值
     */
    zcard(key: string): Promise<any>;
    /**
     * 获取 key 中存储的有序集合中分数在 min 和 max 之间的元素个数
     * @param key 有序集合的键值
     * @param min 分数的最小值，闭区间
     * @param max 分数的最大值，闭区间
     */
    zcount(key: string, min: number | string, max: number | string): Promise<any>;
    /**
     * 对 key 中存储的有序集合中的某个元素的分数执行加操作
     * @param key 有序集合的键值
     * @param increment 分数的加数
     * @param member 元素值
     */
    zincrby(key: string, increment: number, member: string): Promise<any>;
    zinterstore(destination: string, numkeys: number, ...key1: any[]): Promise<any>;
    zrange(key: string, start: number, stop: number, withscores?: 'withscores'): Promise<any>;
    zrangebyscore(key: string, min: (number | string), max: (number | string)): Promise<any>;
    zrank(key: string, member: string): Promise<any>;
    zrem(key: string, member: string, ...members: string[]): Promise<any>;
    /**
     * 根据给定排名范围删除 key 中存储的有序集合的若干元素
     * @param key 有序集合的键值
     * @param start 范围区间的左端点，闭区间
     * @param stop 范围区间的右端点，闭区间
     */
    zremrangebyrank(key: string, start: number, stop: number): Promise<any>;
    /**
     * 根据给定分数范围删除 key 中存储的有序集合的若干元素
     * @param key 有序集合的键值
     * @param min 范围区间的左端点，闭区间
     * @param max 范围区间的右端点，闭区间
     */
    zremrangebyscore(key: string, min: (number | string), max: (number | string)): Promise<any>;
    zrevrange(key: string, start: number, stop: number, withscores?: 'withscores'): Promise<any>;
    /**
     * 以逆序获取 key 中存储的有序集合中在给定分数范围内的若干元素
     * @param key 有序集合的键值
     * @param max 范围区间的右端点，闭区间
     * @param min 范围区间的左端点，闭区间
     */
    zrevrangebyscore(key: string, max: (number | string), min: (number | string)): Promise<any>;
    /**
     * 以逆序获取 key 中存储的有序集合的某个元素的排名
     * @param key 有序集合的键值
     * @param member 元素值
     */
    zrevrank(key: string, member: string): Promise<any>;
    /**
     * 获取 key 中存储的有序集合中某个元素的分数
     * @param key 有序集合的键值
     * @param member 元素值
     */
    zscore(key: string, member: string): Promise<any>;
    zunionstore(destination: string, numkeys: number, ...key: any[]): Promise<any>;
    pfadd(key: string, ...elements: string[]): Promise<any>;
    pfcount(key: string, ...keys: string[]): Promise<any>;
    pfmerge(dest: string, ...keys: string[]): Promise<any>;
}
