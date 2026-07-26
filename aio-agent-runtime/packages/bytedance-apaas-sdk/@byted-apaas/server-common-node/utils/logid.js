"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.oldGenLogID = void 0;
const os = require("os");
const nanoid_1 = require("nanoid");
const nanoid = (0, nanoid_1.customAlphabet)('1234567890abcdef', 6);
const version = '02';
const v6Addr = getIpv6Address();
/**
 * logid：版本号[2位] + 时间戳（精确到毫秒）[13位] + IPv6[32位] + random（16进制）[6位] = 2 + 13 + 32 + 6 = 53 位
 * @returns {string}
 */
function genLogID() {
    const timeStamp = Date.now();
    const rand = nanoid();
    return version + timeStamp + v6Addr + rand;
}
exports.default = genLogID;
/**
 * logid：版本号[2位] + 时间戳（精确到毫秒）[13位] + IPv6[32位] + random（16进制）[6位] = 2 + 13 + 32 + 6 = 53 位
 * @returns {string}
 */
function oldGenLogID() {
    const timeStamp = String(Date.now());
    const rand = Math.random().toString(16).slice(-6);
    return version + timeStamp + v6Addr + rand;
}
exports.oldGenLogID = oldGenLogID;
function ocetToBinary(ocetStr) {
    return (Array(8).join('0') + parseInt(ocetStr, 10).toString(2)).slice(-8);
}
function binaryToHex(binaryStr) {
    return (Array(4).join('0') + parseInt(binaryStr, 2).toString(16)).slice(-4);
}
function ipv4ToIPv6(v4Addr) {
    const unknownIP = '00000000000000000000000000000000';
    if (!v4Addr) {
        return unknownIP;
    }
    const v4AddrBytes = v4Addr.split(/\./).map((ocetPart) => ocetToBinary(ocetPart));
    const v6AddrBytes = [];
    v6AddrBytes[0] = binaryToHex(v4AddrBytes[0] + v4AddrBytes[1]);
    v6AddrBytes[1] = binaryToHex(v4AddrBytes[2] + v4AddrBytes[3]);
    const v6Addr = [
        '0000',
        '0000',
        '0000',
        '0000',
        '0000',
        'ffff',
        v6AddrBytes[0],
        v6AddrBytes[1],
    ];
    return v6Addr.join('');
}
function getIpv6Address() {
    const interfaces = os.networkInterfaces();
    let v6Addr = '';
    let v4Addr = '';
    for (const devName of Object.keys(interfaces)) {
        const iface = interfaces[devName];
        if (iface) {
            for (let i = 0; i < iface.length; i++) {
                const alias = iface[i];
                if (alias.family === 'IPv6' &&
                    alias.address !== '::1' &&
                    !alias.internal) {
                    v6Addr = alias.address;
                    return formatIpv6Address(v6Addr);
                }
                if (alias.family === 'IPv4' &&
                    alias.address !== '127.0.0.1' &&
                    !alias.internal) {
                    v4Addr = alias.address;
                }
            }
        }
    }
    return v6Addr || ipv4ToIPv6(v4Addr);
}
/**
 * 将 IPv6 从点分表示还原成 32位 16 进制表示
 *
 * @param {string} address
 * @returns {string}
 */
function formatIpv6Address(address) {
    let result = '';
    const resultParts = [];
    let zerosPos = 0; // :: 位置
    let partNums = 0; // 非零四位组数量
    let zerosPosFlag = true;
    const ZERO_PART = '0000'; // 全零四位组
    if (address.indexOf('::') > -1) {
        const parts = address.split('::');
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (part.indexOf(':') > 0) {
                const subPart = part.split(':');
                if (zerosPosFlag) {
                    zerosPos = subPart.length;
                }
                partNums = partNums + subPart.length;
                for (let j = 0; j < subPart.length; j++) {
                    if (subPart[j].length !== 4) {
                        const zeroPad = ZERO_PART.substring(0, 4 - subPart[j].length);
                        const partWithPad = zeroPad.concat(subPart[j]);
                        resultParts.push(partWithPad);
                    }
                    else {
                        resultParts.push(subPart[j]);
                    }
                }
                zerosPosFlag = false;
            }
            else {
                if (part.length !== 4) {
                    const zeroPad = ZERO_PART.substring(0, 4 - part.length);
                    const partWithPad = zeroPad.concat(part);
                    resultParts.push(partWithPad);
                }
                else {
                    resultParts.push(part);
                }
                if (zerosPosFlag) {
                    zerosPos = zerosPos + 1;
                }
                partNums = partNums + 1;
                zerosPosFlag = false;
            }
        }
        let zeros = '';
        for (let h = 0; h < 8 - partNums; h++) {
            zeros = zeros.concat(ZERO_PART);
        }
        for (let y = 0; y < resultParts.length; y++) {
            if (y === zerosPos) {
                result = result.concat(zeros);
                result = result.concat(resultParts[y]);
            }
            else {
                result = result.concat(resultParts[y]);
            }
        }
        return result;
    }
    else {
        const parts = address.split(':');
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            if (parts[i].length !== 4) {
                const zeroPad = ZERO_PART.substring(0, 4 - parts[i].length);
                const partWithPad = zeroPad.concat(part);
                result = result.concat(partWithPad);
            }
            else {
                result = result.concat(part);
            }
        }
        return result;
    }
}
