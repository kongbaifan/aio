"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getCredential = exports.getFaaSCredential = exports.AppCredential = void 0;
const constants_1 = require("../constants/constants");
const utils = require("../utils/utils");
const openapi_1 = require("../http/openapi");
class AppCredential {
    constructor(id, secret, isSystem = false) {
        this.id = id;
        this.secret = secret;
        this.isSystem = isSystem;
    }
    setSystemFlag(isSystem) {
        this.isSystem = true;
    }
    async getToken() {
        if (this.expireTime - new Date().getTime() > constants_1.AppTokenRefreshTime) {
            return this.token;
        }
        let { token } = await this.refresh();
        return token;
    }
    async getTenantInfo() {
        if (!this || !this.id || !this.secret) {
            this.id = utils.getClientId();
            this.secret = utils.getClientSecret();
        }
        if (this.tenantInfo) {
            return this.tenantInfo;
        }
        let { tenantInfo } = await this.refresh();
        return tenantInfo;
    }
    async refresh() {
        let data = await this.fetchToken();
        let domain = '';
        if (data && data.tenantInfo && data.tenantInfo.outsideTenantInfo) {
            domain = data.tenantInfo.outsideTenantInfo.outsideDomainName;
        }
        this.token = data.accessToken;
        this.expireTime = data.expireTime;
        if (!this.tenantInfo) {
            this.tenantInfo = {
                id: data.tenantInfo.id,
                name: data.tenantInfo.domainName,
                type: data.tenantInfo.tenantType,
                namespace: data.namespace,
                domain: domain
            };
        }
        return { token: this.token, tenantInfo: this.tenantInfo };
    }
    async fetchToken() {
        // TODO veFaaS 迁移完成 下掉
        if (utils.isOnlineDev()) {
            return { accessToken: utils.getOpenapiToken(), expireTime: 0, tenantInfo: {} };
        }
        return await (0, openapi_1.getAppTokenHttp)(this.id, this.secret);
    }
}
exports.AppCredential = AppCredential;
let faaSCredential = undefined;
function getFaaSCredential() {
    if (faaSCredential) {
        return faaSCredential;
    }
    if (utils.getFaasType() == constants_1.faaSAccessType.InspirecloudExternalAccessType) {
        faaSCredential = new AppCredential('', '', true);
    }
    else {
        faaSCredential = new AppCredential(utils.getClientId(), utils.getClientSecret(), true);
    }
    return faaSCredential;
}
exports.getFaaSCredential = getFaaSCredential;
function getCredential() {
    if (utils.isOpenSDKMode()) {
        return utils.getCredential();
    }
    return getFaaSCredential();
}
exports.getCredential = getCredential;
