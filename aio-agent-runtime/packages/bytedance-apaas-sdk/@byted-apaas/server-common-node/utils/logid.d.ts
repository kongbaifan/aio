/**
 * logid：版本号[2位] + 时间戳（精确到毫秒）[13位] + IPv6[32位] + random（16进制）[6位] = 2 + 13 + 32 + 6 = 53 位
 * @returns {string}
 */
export default function genLogID(): string;
/**
 * logid：版本号[2位] + 时间戳（精确到毫秒）[13位] + IPv6[32位] + random（16进制）[6位] = 2 + 13 + 32 + 6 = 53 位
 * @returns {string}
 */
export declare function oldGenLogID(): string;
