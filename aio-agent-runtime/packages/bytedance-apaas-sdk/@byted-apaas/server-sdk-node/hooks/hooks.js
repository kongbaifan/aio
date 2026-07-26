"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const resources_1 = require("../context/resources/impl/resources");
const tasks_1 = require("../context/tasks/tasks");
const msg_1 = require("../context/msg/msg");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const api = require("./api");
const operator_1 = require("../kunlun/operator/impl/operator");
const db_1 = require("../context/db/impl/db");
const common_1 = require("../request/common");
const integration_1 = require("../context/integration/impl/integration");
const metadataApi = require("../context/metadata/metadata");
const flow_1 = require("../global/application/flow/flow");
/**
 * 根据 key 获取对应的全局变量
 * @param key 全局变量的 key
 */
function getVar(key) {
    return server_common_node_1.utils.getGlobalVariableByKey(key);
}
function pre(params, context, logger, requireFunc) {
    // 初始化 kunlun
    if (!global.kunlun) {
        // 缺省的情况，先对 kunlun 进行初始化
        global.kunlun = {};
    }
    global.kunlun.operator = new operator_1.Operator();
    global.kunlun.getVar = getVar;
    global.kunlun.tool.getTenantInfo = common_1.getTenantInfo;
    // 对 context 下的能力进行初始化
    mountContext(context, logger, requireFunc);
    mountApplication(context);
}
/**
 * mountContext 函数用于初始化 context 在 core 包中实现的部分，包括：
 *   - db
 *   - (global function 场景下): setRespHeader, setRedirectLocation
 *   - task, function, msg, resources
 * @param context 系统代理函数中经由 common 创建的用户 context，根据 source 分为不同类型
 * @param logger Logger
 * @param requireFunc
 */
function mountContext(context, logger, requireFunc) {
    // 1. 全量挂载
    context.db = new db_1.DBWithCurrentObject(context.objectApiName);
    // set response headers
    context.setResponseHeader = api.setRespHeader();
    context.setRedirectLocation = api.setRedirectLocation(context);
    context.method = server_common_node_1.utils.getHttpMethod();
    // 2. 初始化 core 包中需要初始化的内容，因此强转为 IContext 类型
    //    - function
    //    - tasks
    //    - msg
    //    - resources
    //    - microservice
    //    - getVar
    context.function = api.getFunctionSync(context, logger);
    context.tasks = new tasks_1.Tasks(context.function);
    context.msg = new msg_1.Message();
    context.resources = new resources_1._Resources();
    context.integration = new integration_1._Integration();
    context.getVar = getVar;
    context.microservice = api.invokeMicroservice();
    api.mountWorkflowFeature(context);
    // 挂载 metadata
    api.mountMetadata(context);
    api.mockFlowFeature(context);
    // 防止 context.function 被串改
    Object.freeze(context.function);
}
function mountApplication(context) {
    if (!global.application) {
        global.application = {};
    }
    global.application.data = new db_1.DB();
    // (global as any).application.dataV3 = new DBV3<IGfCtx>();
    // publicAPI
    if (!global.application.publicAPI) {
        global.application.publicAPI = {};
    }
    global.application.publicAPI.setResponseHeader = api.setRespHeader();
    global.application.publicAPI.setRedirectLocation = api.setRedirectLocation(context);
    global.application.publicAPI.method = server_common_node_1.utils.getHttpMethod();
    global.application.publicAPI.headers = server_common_node_1.utils.getHttpHeaders();
    global.application.msg = new msg_1.Message();
    global.application.resources = new resources_1._Resources();
    global.application.metadata = metadataApi.metadata(context);
    // (global as any).application.metadataV3 = metadataApi.metadataV3(context);
    // globalVar
    if (!global.application.globalVar) {
        global.application.globalVar = {};
    }
    global.application.globalVar.getVar = getVar;
    // constants
    if (!global.application.constants) {
        global.application.constants = {};
    }
    global.application.constants.metaType = metadataApi.metaType();
    // flow
    global.application.flow = (0, flow_1.newFlow)(context);
    // operator
    global.application.operator = new operator_1.Operator();
    global.application.integration = new integration_1._Integration();
}
module.exports = {
    pre,
};
