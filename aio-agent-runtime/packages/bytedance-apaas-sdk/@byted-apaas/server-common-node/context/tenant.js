"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Event = exports.App = exports.Tenant = exports.TenantType = void 0;
var TenantType;
(function (TenantType) {
    TenantType[TenantType["NORMAL"] = 1] = "NORMAL";
    TenantType[TenantType["FEISHU"] = 2] = "FEISHU";
    TenantType[TenantType["DEVORG"] = 3] = "DEVORG";
    TenantType[TenantType["SANDBOX"] = 4] = "SANDBOX";
})(TenantType = exports.TenantType || (exports.TenantType = {}));
class Tenant {
    constructor(params) {
        if (params) {
            this.name = params.name;
            this.id = params.id;
            this.type = params.type;
            this.namespace = params.namespace;
            this.domain = params.domain;
        }
    }
}
exports.Tenant = Tenant;
class App {
}
exports.App = App;
class Event {
}
exports.Event = Event;
