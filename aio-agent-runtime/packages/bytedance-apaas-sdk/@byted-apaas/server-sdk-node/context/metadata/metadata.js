"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.metadataV3 = exports.MetaDataV3 = exports.metaType = exports.metadata = exports.MetaData = void 0;
const components = require("./components/components");
const common = require("@byted-apaas/server-common-node");
const fields = require("./objects/fields");
const fieldsV3 = require("./objects/fieldsV3");
const Request = require("../../request/interface");
const commonExceptions = common.exceptions;
// interface ---------------------------------------------------------------------------------------
class MetaData {
    constructor(ctx) {
    }
    object(objectApiName) {
        if (!objectApiName) {
            throw new commonExceptions.InvalidParamError('objectApiName is empty');
        }
        return new KObject(objectApiName);
    }
    page(apiName, objectApiName, type) {
        if (!apiName) {
            throw new commonExceptions.InvalidParamError('apiName is empty');
        }
        if (!objectApiName) {
            throw new commonExceptions.InvalidParamError('objectApiName is empty');
        }
        if (!type) {
            throw new commonExceptions.InvalidParamError('type is empty');
        }
        return new Page(apiName, objectApiName, type);
    }
}
exports.MetaData = MetaData;
function metadata(ctx) {
    return new MetaData(ctx);
}
exports.metadata = metadata;
class MetaDataV3 {
    constructor(ctx) {
    }
    object(objectApiName) {
        if (!objectApiName) {
            throw new commonExceptions.InvalidParamError('objectApiName is empty');
        }
        const appCtx = {
            dataVersion: 'v3',
        };
        return new KObject(objectApiName, appCtx);
    }
}
exports.MetaDataV3 = MetaDataV3;
function metadataV3(ctx) {
    return new MetaDataV3(ctx);
}
exports.metadataV3 = metadataV3;
class KObject {
    constructor(objectApiName, appCtx) {
        this.objectApiName = objectApiName;
        this.appCtx = appCtx;
    }
    async getFields() {
        let res = await Request.GetInstance().getFields(this.objectApiName);
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return fieldsV3.parseFieldsV3(res);
        }
        return fields.parseFields(res);
    }
    async getField(fieldApiName) {
        let res = await Request.GetInstance().getField(this.objectApiName, fieldApiName);
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            return fieldsV3.parseFieldV3(res);
        }
        return fields.parseField(res);
    }
}
class Page {
    /**
     *
     * @param pageApiName: 页面apiName
     * @param objectApiName：对象apiName
     * @param type：app 或 record_page
     */
    constructor(pageApiName, objectApiName, type) {
        this.pageApiName = pageApiName;
        this.objectApiName = objectApiName;
        this.type = type;
    }
    async getRecordDetail(componentName) {
        // return await openapi.getDesktopRecordDetail(this.ctx, this.pageApiName, componentName, this.objectApiName, this.type);
        return null;
    }
    async getList(componentName) {
        // return await openapi.getDesktopList(this.ctx, this.pageApiName, componentName, this.objectApiName, this.type);
        return null;
    }
    async getId() {
        // return await openapi.getIdByApiName(this.ctx, this.objectApiName, this.pageApiName, 'RecordPage');
        return null;
    }
    async getMobileList(componentName) {
        // return await openapi.getMobileList(this.ctx, this.pageApiName, componentName, this.objectApiName, this.type) as any;
        return null;
    }
    async updateMobileList(componentName, params) {
        // params.pageApiName = this.pageApiName;
        // params.objectApiName = this.objectApiName;
        // params.componentName = componentName;
        // params.pageType = this.type;
        // return await openapi.updateMobileList(this.ctx, params);
        return null;
    }
}
function metaType() {
    return {
        pageComponent: {
            desktop: {},
            mobile: {
                List: components.mobile.List,
            },
        }
    };
}
exports.metaType = metaType;
