"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports._Resources = exports._OpenSDKResources = exports._KunlunFile = exports._KunlunOpenSDKFile = void 0;
const stream_1 = require("stream");
const Request = require("../../../request/interface");
const common_1 = require("../../../application/impl/common");
const common = require("@byted-apaas/server-common-node");
const stream_to_buffer_1 = require("@jorgeferrero/stream-to-buffer");
const exceptions = common.exceptions;
const fs = require('fs');
class _KunlunOpenSDKFile {
    constructor(appCtx) {
        this.appCtx = appCtx;
    }
    async Upload(fileName, source) {
        // 1. check parameters type
        if (typeof fileName !== 'string') {
            throw new exceptions.InvalidParamError('upload method parameter fileName must be string. ');
        }
        if (typeof source !== 'string' && !(source instanceof stream_1.Stream) && !(source instanceof Buffer)) {
            throw new exceptions.InvalidParamError('upload method parameter source must be string or stream or buffer. ');
        }
        // 2. divide by source type
        if (typeof source === 'string') {
            // upload from path
            if (!fs.existsSync(source)) {
                throw new exceptions.InvalidParamError(`no such file '${source}'`);
            }
            source = fs.createReadStream(source);
        }
        if (source instanceof stream_1.Stream) {
            // upload from stream
            source = await (0, stream_to_buffer_1.streamToBuffer)(source);
        }
        if (source instanceof Buffer) {
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKUploadFile(fileName, source);
            });
        }
        return null;
    }
    ;
    async UploadAvatar(fileName, source) {
        // 1. check parameters type
        if (typeof fileName !== 'string') {
            throw new exceptions.InvalidParamError('upload method parameter fileName must be string. ');
        }
        if (typeof source !== 'string' && !(source instanceof stream_1.Stream) && !(source instanceof Buffer)) {
            throw new exceptions.InvalidParamError('upload method parameter source must be string or stream or buffer. ');
        }
        // 2. divide by source type
        if (typeof source === 'string') {
            // upload from path
            if (!fs.existsSync(source)) {
                throw new exceptions.InvalidParamError(`no such file '${source}'`);
            }
            source = fs.createReadStream(source);
        }
        if (source instanceof stream_1.Stream) {
            // upload from stream
            source = await (0, stream_to_buffer_1.streamToBuffer)(source);
        }
        if (source instanceof Buffer) {
            // upload from buffer
            return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
                return await Request.GetInstance().openSDKUploadAvatar(fileName, source);
            });
        }
        return null;
    }
    ;
    async Download(fileID) {
        // 1. check parameters type
        if (typeof fileID !== 'string') {
            throw new exceptions.InvalidParamError('download method parameter fileID must be string. ');
        }
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().downloadFileByID(fileID);
        });
    }
    ;
    async DownloadAvatar(imageID) {
        // 1. check parameters type
        if (typeof imageID !== 'string') {
            throw new exceptions.InvalidParamError('download method parameter imageID must be string. ');
        }
        return await (0, common_1.runCtxForOpenSDK)(this.appCtx, async () => {
            return await Request.GetInstance().openSDKDownloadAvatar(imageID);
        });
    }
    ;
}
exports._KunlunOpenSDKFile = _KunlunOpenSDKFile;
class _KunlunFile {
    async download(fileTokenOrInfo, filePath) {
        if (typeof (fileTokenOrInfo) === 'string') {
            return await Request.GetInstance().downloadFileByToken(fileTokenOrInfo, filePath);
        }
        else if (typeof (fileTokenOrInfo) === 'object') {
            if (!fileTokenOrInfo.id) {
                throw new exceptions.InvalidParamError(`The value of fileInfo.id is empty`);
            }
            if (typeof (fileTokenOrInfo.id) !== 'string') {
                throw new exceptions.InvalidParamError(`The type of fileInfo.id should be string, but ${typeof (fileTokenOrInfo)}`);
            }
            let tokenListStr = await Request.GetInstance().mGetFileToken([fileTokenOrInfo.id]);
            let id2token;
            try {
                id2token = JSON.parse(tokenListStr);
            }
            catch (err) {
                throw new exceptions.InternalError(`parse mGetFileToken resp failed: ${err.message}`);
            }
            if (!id2token[fileTokenOrInfo.id]) {
                throw new exceptions.InternalError(`id (${fileTokenOrInfo.id})'s token is empty`);
            }
            return await Request.GetInstance().downloadFileByToken(id2token[fileTokenOrInfo.id], filePath);
        }
        else {
            throw new exceptions.InvalidParamError(`The type of first param should be string or object, but ${typeof (fileTokenOrInfo)}`);
        }
    }
    async upload(data, expire, fileName, ...ret) {
        if (ret.length > 0) {
            throw new exceptions.InvalidParamError(`params is too many, as ${ret.length + 2}`);
        }
        if (!data) {
            throw new exceptions.InvalidParamError(`params is null`);
        }
        // 1. data is filePath, read it from disk, convert it to Steam.
        if (typeof (data) === 'string') {
            if (!fs.existsSync(data)) {
                throw new exceptions.InvalidParamError(`no such file '${data}'`);
            }
            data = fs.createReadStream(data);
        }
        // 2. data must be Stream at here.
        return await Request.GetHttpInstance().uploadFile(data, expire, fileName);
    }
}
exports._KunlunFile = _KunlunFile;
/**
 * OpenSDK 静态资源操作类
 */
class _OpenSDKResources {
    constructor(appCtx) {
        this.file = new _KunlunOpenSDKFile(appCtx);
    }
}
exports._OpenSDKResources = _OpenSDKResources;
/**
 * 静态资源操作类
 */
class _Resources {
    constructor() {
        this.file = new _KunlunFile();
    }
}
exports._Resources = _Resources;
