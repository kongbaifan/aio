"use strict";
// Copyright 2022 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT
Object.defineProperty(exports, "__esModule", { value: true });
exports.Oql = void 0;
const Request = require("../../../../request/interface");
const constants_1 = require("@byted-apaas/server-common-node/constants/constants");
class Oql {
    constructor(oql, namedArgs, appCtx) {
        this.appCtx = null;
        this.oql = oql;
        this.params = [];
        this.namedParams = {};
        this.params = [];
        if (namedArgs) {
            this.namedParams = namedArgs;
        }
        this.appCtx = appCtx;
    }
    async execute() {
        if (this.appCtx && this.appCtx.dataVersion === 'v3') {
            // todo wby
        }
        let records = await Request.GetInstance().oql(this.oql, this.params, this.namedParams, this.authType);
        if (records && Array.isArray(records)) {
            return records;
        }
        return [];
    }
    useSystemAuth() {
        this.authType = constants_1.AuthTypeSystem;
        return this;
    }
    useUserAuth() {
        this.authType = constants_1.AuthTypeMixUserSystem;
        return this;
    }
}
exports.Oql = Oql;
