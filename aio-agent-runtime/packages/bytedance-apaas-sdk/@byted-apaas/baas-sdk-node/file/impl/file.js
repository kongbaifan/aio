"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.File = void 0;
const constants_1 = require("../../constants/constants");
const faasinfra_1 = require("../../http/faasinfra");
const axios_1 = require("axios");
const common = require("@byted-apaas/server-common-node");
const exceptions = common.exceptions;
const mime = require('mime');
class File {
    async upload(filename, file, options, addition) {
        let buffer;
        let contentType;
        if (!file) {
            throw new exceptions.InvalidParamError('param file is undefined');
        }
        else if (typeof file === 'string') {
            buffer = Buffer.from(file);
            contentType = 'text/plain';
        }
        else if (file instanceof Buffer) {
            buffer = file;
            contentType = mime.getType(filename);
        }
        else if (file.url) {
            try {
                buffer = await readBufferFromUrl(file.url);
                contentType = mime.getType(filename);
            }
            catch (e) {
                throw new exceptions.InvalidParamError(`fetch file from (${file.url}) failed: ${e.message}`);
            }
        }
        else {
            throw new exceptions.InvalidParamError(`param file type is invalid`);
        }
        if (!buffer) {
            throw new exceptions.InvalidParamError(`content of file is empty`);
        }
        if (buffer.length > constants_1.MAX_FILE_SIZE) {
            throw new exceptions.InvalidParamError(`file size is exceeded ${constants_1.MAX_FILE_SIZE}`);
        }
        let res = await (0, faasinfra_1.requestFile)(filename, buffer, contentType, options, addition);
        if (!res || !res.url) {
            throw new exceptions.InvalidParamError(`upload file result is not correct ${JSON.stringify(res)}`);
        }
        return {
            id: res.id,
            url: res.url,
        };
    }
}
exports.File = File;
async function readBufferFromUrl(url) {
    const res = await (0, axios_1.default)({
        method: 'get',
        url,
        responseType: 'stream',
    });
    const stream = res.data;
    let err = undefined;
    return new Promise((resolve, reject) => {
        stream.on('data', onData);
        stream.on('end', onEnd);
        stream.on('error', onEnd);
        stream.on('close', onClose);
        function cleanup() {
            stream.removeListener('data', onData);
            stream.removeListener('end', onEnd);
            stream.removeListener('error', onEnd);
            stream.removeListener('close', onClose);
        }
        let buffer = Buffer.alloc(constants_1.MAX_FILE_SIZE);
        let size = 0;
        function onData(doc) {
            if (size + doc.length > constants_1.MAX_FILE_SIZE) {
                err = new exceptions.InvalidParamError(`file size exceeded ${constants_1.MAX_FILE_SIZE}`);
                stream.destroy(err);
                reject(err);
                return;
            }
            buffer.write(doc.toString('binary'), size, doc.length, 'binary');
            size += doc.length;
        }
        function onEnd(e) {
            if (e) {
                reject(e);
            }
            else if (err) {
                reject(err);
            }
            else {
                resolve(buffer.slice(0, size));
            }
            cleanup();
        }
        function onClose() {
            if (err) {
                reject(err);
            }
            else {
                resolve(buffer.slice(0, size));
            }
            cleanup();
        }
    });
}
