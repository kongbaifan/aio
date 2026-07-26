"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.tokenCacheMap = exports.tokenRefreshIntervalKey = exports.appTokenType = exports.serviceTokenType = exports.retryMethods = exports.faasinfraHttpPath = exports.openapiHttpPath = exports.metricsMethodKeys = exports.replaceKeys = void 0;
const config_1 = require("./config");
const appTokenType = 'app';
exports.appTokenType = appTokenType;
const serviceTokenType = 'service';
exports.serviceTokenType = serviceTokenType;
const tokenRefreshIntervalKey = 'RefreshInterval';
exports.tokenRefreshIntervalKey = tokenRefreshIntervalKey;
const tokenCacheMap = {
    'appRefreshInterval': 20 * 60 * 1000,
    'app': {
        'accessToken': '',
        'expireTime': 0,
    },
    'serviceRefreshInterval': 20 * 60 * 1000,
    'service': {
        'accessToken': '',
        'expireTime': 0,
    },
};
exports.tokenCacheMap = tokenCacheMap;
const replaceKeys = {
    namespace: ':namespace',
    objectApiName: ':objectApiName',
    fieldApiName: ':fieldApiName',
    resourceApiName: ':resourceApiName',
    functionAPIName: ':functionAPIName',
    resourceType: ':resourceType',
    apiName: ':apiName',
    id: ':id',
    recordID: ':recordID',
    fileID: ':fileID',
    serviceID: ':serviceID',
    key: ':key',
};
exports.replaceKeys = replaceKeys;
const retryMethods = ['updateRecordBySync', 'mGetRecordByCriterionV4', 'mGetRecordByCriterion', 'getFieldV2', 'getFieldV5', 'getFieldsV2', 'getFieldsV5'];
exports.retryMethods = retryMethods;
const metricsMethodKeys = {
    // openapi
    getAppToken: 'openapi_getAppToken',
    getAllGlobalConfigs: 'openapi_getAllGlobalConfigs',
    // data v3 record CRUD
    createRecordBySyncV3: 'openapi_createRecordBySyncV3',
    createRecordsBySyncV3: 'openapi_createRecordsBySyncV3',
    updateRecordBySyncV3: 'openapi_updateRecordBySyncV3',
    updateRecordsBySyncV3: 'openapi_updateRecordsBySyncV3',
    deleteRecordBySyncV3: 'openapi_deleteRecordBySyncV3',
    deleteRecordsBySyncV3: 'openapi_deleteRecordsBySyncV3',
    mGetRecordV3: 'openapi_mGetRecordV3',
    mGetRecordsV3OrCounByCriterion: 'openapi_mGetRecordsV3OrCounByCriterion',
    modifyRecordsWithTransactionV3: 'openapi_modifyRecordsWithTransactionV3',
    // record CRUD
    createRecordBySync: 'openapi_createRecordBySync',
    createRecordsBySync: 'openapi_createRecordsBySync',
    updateRecordBySync: 'openapi_updateRecordBySync',
    updateRecordsBySync: 'openapi_updateRecordsBySync',
    deleteRecordBySync: 'openapi_deleteRecordBySync',
    deleteRecordsBySync: 'openapi_deleteRecordsBySync',
    mGetRecordByCriterionV4: 'openapi_mGetRecordByCriterionV4',
    mGetRecordByCriterion: 'openapi_mGetRecordByCriterion',
    mGetCountByCriterion: 'openapi_mGetCountByCriterion',
    modifyRecordsWithTransaction: 'openapi_modifyRecordsWithTransaction',
    batchCreate: 'openapi_batchCreate',
    batchUpdate: 'openapi_batchUpdate',
    batchDelete: 'openapi_batchDelete',
    // file upload & download
    uploadAttachment: 'openapi_uploadAttachment',
    downloadAttachment: 'openapi_downloadAttachment',
    // message
    createMessage: 'openapi_createMessage',
    updateMessage: 'openapi_updateMessage',
    // locale
    mGetUserSettings: 'openapi_mGetUserSettings',
    getFunction: 'openapi_getFunction',
    // workflow
    workflowUpdateVariables: 'openapi_workflowUpdateVariables',
    terminateWorkflowInstance: 'openapi_terminateWorkflowInstance',
    // 元数据相关
    // field
    getFields: 'openapi_getFields',
    getField: 'openapi_getField',
    getFieldsV2: 'openapi_getFieldsV2',
    getFieldsV5: 'openapi_getFieldsV5',
    getFieldV2: 'openapi_getFieldV2',
    getFieldV5: 'openapi_getFieldV5',
    // page component
    getUIMetaRecordDetail: 'openapi_getUIMetaRecordDetail',
    getUIMetaList: 'openapi_getUIMetaList',
    getMobileList: 'openapi_getMobileList',
    updateMobileList: 'openapi_updateMobileList',
    getIdByApiName: 'openapi_getIdByApiName',
    // faasinfra
    getServiceToken: 'faasinfra_getServiceToken',
    sendLog: 'faasinfra_sendLog',
    invokeFuncSync: 'faasinfra_invokeFuncSync',
    createAsyncTask: 'faasinfra_createAsyncTask',
    createDistributedTask: 'faasinfra_CreateDistributedTask',
    createAsyncTaskV2: 'faasinfra_createAsyncTaskV2',
    createDistributedTaskV2: 'faasinfra_CreateDistributedTaskV2',
    createDistributedTaskV3: 'faasinfra_CreateDistributedTaskV3',
    invokeMicroserviceSync: 'faasinfra_invokeMicroserviceSync',
    invokeMicroserviceAsync: 'faasinfra_invokeMicroserviceAsync',
    invokeFuncWithAuthInnerAPI: 'openapi_invokeFuncWithAuth',
    invokeFuncSyncInnerAPI: 'openapi_invokeFuncSync',
    createAsyncTaskInnerAPIV1: 'openapi_createAsyncTaskV1',
    createAsyncTaskInnerAPIV2: 'openapi_createAsyncTaskV2',
    getIntegrationAppAccessTokenAPI: 'openapi_getIntegrationAppAccessToken',
    getIntegrationTenantAccessTokenAPI: 'openapi_getIntegrationTenantAccessToken',
    getDefaultIntegrationAppAccessTokenAPI: 'openapi_getDefaultIntegrationAppAccessToken',
    getDefaultIntegrationTenantAccessTokenAPI: 'openapi_getDefaultIntegrationTenantAccessToken',
    // 反压中心
    pressureSdk: 'openapi_pressure_sdk',
};
exports.metricsMethodKeys = metricsMethodKeys;
const openapiHttpPath = {
    getAppToken: new config_1.PostHttpConfig(`/auth/v1/appToken`, metricsMethodKeys.getAppToken),
    getAllGlobalConfigs: new config_1.PostHttpConfig(`/generic/globalconfig/v1/namespaces/${replaceKeys.namespace}/getAllConfigs`, metricsMethodKeys.getAllGlobalConfigs),
    // data v3 record CRUD
    createRecordBySyncV3: new config_1.PostHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records`, metricsMethodKeys.createRecordBySyncV3),
    createRecordsBySyncV3: new config_1.PostHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records_batch`, metricsMethodKeys.createRecordsBySyncV3),
    updateRecordBySyncV3: new config_1.PatchHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records/${replaceKeys.recordID}`, metricsMethodKeys.updateRecordBySyncV3),
    updateRecordsBySyncV3: new config_1.PatchHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records_batch`, metricsMethodKeys.updateRecordsBySyncV3),
    deleteRecordBySyncV3: new config_1.DeleteHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records/${replaceKeys.recordID}`, metricsMethodKeys.deleteRecordBySyncV3),
    deleteRecordsBySyncV3: new config_1.DeleteHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records_batch`, metricsMethodKeys.deleteRecordsBySyncV3),
    mGetRecordV3: new config_1.PostHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records/${replaceKeys.recordID}`, metricsMethodKeys.mGetRecordV3),
    mGetRecordsV3OrCounByCriterion: new config_1.PostHttpConfig(`/v1/data/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records_query`, metricsMethodKeys.mGetRecordsV3OrCounByCriterion),
    // record CRUD
    createRecordBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/createBySync`, metricsMethodKeys.createRecordBySync),
    createRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchCreateByAsync`, metricsMethodKeys.createRecordsBySync),
    updateRecordBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/updateBySync`, metricsMethodKeys.updateRecordBySync),
    updateRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchUpdateByAsync`, metricsMethodKeys.updateRecordsBySync),
    deleteRecordBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/deleteBySync`, metricsMethodKeys.deleteRecordBySync),
    deleteRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchDeleteByAsync`, metricsMethodKeys.deleteRecordsBySync),
    mGetRecordByCriterionV4: new config_1.PostHttpConfig(`/data/v4/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/mGetByCriterionAndSync`, metricsMethodKeys.mGetRecordByCriterionV4),
    mGetRecordByCriterion: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/mGetByCriterion`, metricsMethodKeys.mGetRecordByCriterion),
    mGetCountByCriterion: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/mGetByCriterion`, metricsMethodKeys.mGetCountByCriterion),
    mCreateRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchCreate`, metricsMethodKeys.batchCreate),
    mUpdateRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchUpdate`, metricsMethodKeys.batchUpdate),
    mDeleteRecordsBySync: new config_1.PostHttpConfig(`/data/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchDelete`, metricsMethodKeys.batchDelete),
    // file upload & download
    uploadAttachment: new config_1.PostHttpConfig(`/attachment/v2/upload`, metricsMethodKeys.uploadAttachment),
    downloadAttachment: new config_1.GetHttpConfig(`/attachment/v1/download`, metricsMethodKeys.downloadAttachment),
    downloadFile: new config_1.GetHttpConfig(`/api/attachment/v1/files/${replaceKeys.fileID}`, metricsMethodKeys.downloadAttachment),
    // message
    createMessage: new config_1.PostHttpConfig(`/msg/v4/namespaces/${replaceKeys.namespace}/message_center/notify_task/create`, metricsMethodKeys.createMessage),
    updateMessage: new config_1.PostHttpConfig(`/msg/v4/namespaces/${replaceKeys.namespace}/message_center/notify_task/update`, metricsMethodKeys.updateMessage),
    // locale
    mGetUserSettings: new config_1.PostHttpConfig(`/setting/v1/users`, metricsMethodKeys.mGetUserSettings),
    getFunctionDetail: new config_1.PostHttpConfig(`/cloudfunction/v1/namespaces/${replaceKeys.namespace}/functions/detail`, metricsMethodKeys.getFunction),
    // workflow
    workflowUpdateVariables: new config_1.PostHttpConfig(`/workflow/v5/namespaces/${replaceKeys.namespace}/scripts/updateVariables`, metricsMethodKeys.workflowUpdateVariables),
    terminateWorkflowInstance: new config_1.PostHttpConfig(`/generic/workflow/v1/instance/cancel`, metricsMethodKeys.terminateWorkflowInstance),
    // 元数据相关
    // field
    getFields: new config_1.GetHttpConfig(`/metadata/v4/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/describe`, metricsMethodKeys.getFields),
    getField: new config_1.GetHttpConfig(`/metadata/v4/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/fields/${replaceKeys.fieldApiName}`, metricsMethodKeys.getField),
    // page component
    getUIMetaRecordPage: new config_1.GetHttpConfig(`/generic/metadata/v1/namespaces/${replaceKeys.namespace}/recordDetail/describe/uimeta`, metricsMethodKeys.getUIMetaRecordDetail),
    getUIMetaList: new config_1.GetHttpConfig(`/generic/metadata/v1/namespaces/${replaceKeys.namespace}/list/describe/uimeta`, metricsMethodKeys.getUIMetaList),
    getMobileList: new config_1.GetHttpConfig(`/generic/metadata/v1/namespaces/${replaceKeys.namespace}/tablelist/describe/uimeta`, metricsMethodKeys.getMobileList),
    updateMobileList: new config_1.PostHttpConfig(`/generic/metadata/v1/namespaces/${replaceKeys.namespace}/tablelist/describe/uimeta`, metricsMethodKeys.updateMobileList),
    getIdByApiName: new config_1.GetHttpConfig(`/metadata/v4/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/resources/${replaceKeys.resourceApiName}/type/${replaceKeys.resourceType}`, metricsMethodKeys.getIdByApiName),
    /* ================================================= 新接口: ApiAlias 版本 =================================================*/
    // Record CURD
    createRecordBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/createBySync`, metricsMethodKeys.createRecordBySync),
    updateRecordBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/updateBySync`, metricsMethodKeys.updateRecordBySync),
    deleteRecordBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/deleteBySync`, metricsMethodKeys.deleteRecordBySync),
    createRecordsByAsyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchCreateByAsync`, metricsMethodKeys.createRecordsBySync),
    updateRecordsByAsyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchUpdateByAsync`, metricsMethodKeys.updateRecordsBySync),
    deleteRecordsByAsyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchDeleteByAsync`, metricsMethodKeys.deleteRecordsBySync),
    mGetRecordByCriterionV2: new config_1.PostHttpConfig(`/generic/data/v3/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/mGetByCriterion`, metricsMethodKeys.mGetRecordByCriterion),
    mGetCountByCriterionV2: new config_1.PostHttpConfig(`/generic/data/v3/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/mGetByCriterion`, metricsMethodKeys.mGetCountByCriterion),
    mCreateRecordsBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchCreate`, metricsMethodKeys.batchCreate),
    mUpdateRecordsBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchUpdate`, metricsMethodKeys.batchUpdate),
    mDeleteRecordsBySyncV2: new config_1.PostHttpConfig(`/generic/data/v2/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchDelete`, metricsMethodKeys.batchDelete),
    modifyRecordsWithTransaction: new config_1.PostHttpConfig(`/generic/datax/v2/namespaces/${replaceKeys.namespace}/records/_modify_with_transaction`, metricsMethodKeys.modifyRecordsWithTransaction),
    // workflow
    workflowUpdateVariablesV2: new config_1.PostHttpConfig(`/generic/workflow/v2/namespaces/${replaceKeys.namespace}/scripts/updateVariables`, metricsMethodKeys.workflowUpdateVariables),
    //metadata
    getFieldV2: new config_1.GetHttpConfig(`/metadata/v5-beta/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/fields/${replaceKeys.fieldApiName}`, metricsMethodKeys.getFieldV2),
    getFieldV5: new config_1.GetHttpConfig(`/metadata/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/fields/${replaceKeys.fieldApiName}`, metricsMethodKeys.getFieldV5),
    getFieldsV2: new config_1.GetHttpConfig(`/metadata/v5-beta/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/describe`, metricsMethodKeys.getFieldsV2),
    getFieldsV5: new config_1.GetHttpConfig(`/metadata/v5/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/describe`, metricsMethodKeys.getFieldsV5),
    invokeFuncWithAuthInnerAPI: new config_1.PostHttpConfig(`/api/cloudfunction/v1/namespaces/${replaceKeys.namespace}/invoke/${replaceKeys.apiName}`, metricsMethodKeys.invokeFuncWithAuthInnerAPI),
    invokeFuncSyncInnerAPI: new config_1.PostHttpConfig(`/cloudfunction/v1/namespaces/${replaceKeys.namespace}/function/invokeSync`, metricsMethodKeys.invokeFuncSyncInnerAPI),
    createAsyncTaskInnerAPIV1: new config_1.PostHttpConfig(`/faasAsyncTask/v1/namespaces/${replaceKeys.namespace}/asyncTask/CreateAsyncTask`, metricsMethodKeys.createAsyncTaskInnerAPIV1),
    createAsyncTaskInnerAPIV2: new config_1.PostHttpConfig(`/faasAsyncTask/v2/namespaces/${replaceKeys.namespace}/asyncTask/CreateAsyncTask`, metricsMethodKeys.createAsyncTaskInnerAPIV2),
    getDefaultIntegrationTenantAccessTokenAPI: new config_1.GetHttpConfig(`/api/integration/v1/namespaces/${replaceKeys.namespace}/defaultLark/tenantAccessToken`, metricsMethodKeys.getDefaultIntegrationTenantAccessTokenAPI),
    getDefaultIntegrationAppAccessTokenAPI: new config_1.GetHttpConfig(`/api/integration/v1/namespaces/${replaceKeys.namespace}/defaultLark/appAccessToken`, metricsMethodKeys.getDefaultIntegrationAppAccessTokenAPI),
    getIntegrationAppAccessTokenAPI: new config_1.GetHttpConfig(`/api/integration/v1/namespaces/${replaceKeys.namespace}/lark/appAccessToken/${replaceKeys.apiName}`, metricsMethodKeys.getIntegrationAppAccessTokenAPI),
    getIntegrationTenantAccessTokenAPI: new config_1.GetHttpConfig(`/api/integration/v1/namespaces/${replaceKeys.namespace}/lark/tenantAccessToken/${replaceKeys.apiName}`, metricsMethodKeys.getIntegrationTenantAccessTokenAPI),
    // OpenSDK data sync interface
    openSDKGetRecords: new config_1.PostHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/records`, metricsMethodKeys.mGetRecordByCriterionV4),
    openSDKCreateRecord: new config_1.PostHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}`, metricsMethodKeys.createRecordBySync),
    openSDKBatchCreateRecord: new config_1.PostHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchCreate`, metricsMethodKeys.createRecordsBySync),
    openSDKUpdateRecord: new config_1.PatchHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/${replaceKeys.recordID}`, metricsMethodKeys.updateRecordBySync),
    openSDKBatchUpdateRecord: new config_1.PatchHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchUpdate`, metricsMethodKeys.updateRecordsBySync),
    openSDKDeleteRecord: new config_1.DeleteHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/${replaceKeys.recordID}`, metricsMethodKeys.deleteRecordBySync),
    openSDKBatchDeleteRecord: new config_1.PostHttpConfig(`/api/data/v1/namespaces/${replaceKeys.namespace}/objects/${replaceKeys.objectApiName}/batchDelete`, metricsMethodKeys.deleteRecordsBySync),
    openSDKUploadFile: new config_1.PostHttpConfig(`/api/attachment/v1/files`, metricsMethodKeys.uploadAttachment),
    openSDKUploadAvatar: new config_1.PostHttpConfig(`/api/attachment/v1/images`, metricsMethodKeys.downloadAttachment),
    openSDKDownloadFile: new config_1.GetHttpConfig(`/api/attachment/v1/files/${replaceKeys.fileID}`, metricsMethodKeys.uploadAttachment),
    openSDKDownloadAvatar: new config_1.GetHttpConfig(`/api/attachment/v1/images/${replaceKeys.fileID}`, metricsMethodKeys.downloadAttachment),
};
exports.openapiHttpPath = openapiHttpPath;
const faasinfraHttpPath = {
    getServiceToken: new config_1.PostHttpConfig(`/auth/v1/service/token`, metricsMethodKeys.getServiceToken),
    sendLog: new config_1.PostHttpConfig(`/log/v1/namespaces/${replaceKeys.namespace}/logs/batchSend`, metricsMethodKeys.sendLog),
    invokeFuncSync: new config_1.PostHttpConfig(`/cloudfunction/v1/namespaces/${replaceKeys.namespace}/function/invokeSync`, metricsMethodKeys.invokeFuncSync),
    createAsyncTask: new config_1.PostHttpConfig(`/faasAsyncTask/v1/namespaces/${replaceKeys.namespace}/asyncTask/CreateAsyncTask`, metricsMethodKeys.createAsyncTask),
    createDistributedTask: new config_1.PostHttpConfig(`/distributedTask/v1/namespaces/${replaceKeys.namespace}/create`, metricsMethodKeys.createDistributedTask),
    invokeMicroserviceSync: new config_1.PostHttpConfig(`/cloudfunction/v1/namespaces/${replaceKeys.namespace}/microservice/invokeSync`, metricsMethodKeys.invokeMicroserviceSync),
    invokeMicroserviceAsync: new config_1.PostHttpConfig(`/cloudfunction/v1/namespaces/${replaceKeys.namespace}/microservice/invokeAsync`, metricsMethodKeys.invokeMicroserviceAsync),
    createAsyncTaskV2: new config_1.PostHttpConfig(`/faasAsyncTask/v2/namespaces/${replaceKeys.namespace}/asyncTask/CreateAsyncTask`, metricsMethodKeys.createAsyncTaskV2),
    createDistributedTaskV2: new config_1.PostHttpConfig(`/distributedTask/v2/namespaces/${replaceKeys.namespace}/create`, metricsMethodKeys.createDistributedTaskV2),
    createDistributedTaskV3: new config_1.PostHttpConfig(`/distributedTask/v3/namespaces/${replaceKeys.namespace}/create`, metricsMethodKeys.createDistributedTaskV3),
};
exports.faasinfraHttpPath = faasinfraHttpPath;
