"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApplicationDB = exports.DBWithCurrentObject = exports.DB = void 0;
const object_1 = require("./object");
const server_common_node_1 = require("@byted-apaas/server-common-node");
const index_1 = require("./transaction/index");
const oql_1 = require("./oql/oql");
class DB {
    constructor(objectApiName) {
        this.objectApiName = objectApiName;
    }
    /**
     * 操作指定对象的记录数据
     * @param objectApiName 指定对象的 ApiName
     * @example
     * ```
     * context.db.object('_user').where({
     *     gender: 'male'
     * }).find()
     * ```
     */
    object(objectApiName) {
        return new object_1._KObject(objectApiName);
    }
    ;
    /**
     * 创建一个新的空事务
     * @example
     * ```
     * let tx = context.db.newTransaction();
     * let user = tx.object('_user').registerCreate({
     *     _name: new kunlun.type.Multilingual({ zh: '用户1', en: 'user1' }),
     * });
     * let contract = tx.object('contract').registerCreate({
     *     _name: new kunlun.type.Multilingual({ zh: '用户1的合同', en: 'user1's contract' }),
     *     user: {id: user._id}
     * });
     * await tx.commit();
     * ```
     */
    newTransaction() {
        const appCtx = {
            dataVersion: 'v1',
        };
        return new index_1.Transaction(this.objectApiName, appCtx);
    }
    ;
    oql(oql, nameArgs) {
        if (nameArgs) {
            return new oql_1.Oql(oql, nameArgs);
        }
        return new oql_1.Oql(oql);
    }
}
exports.DB = DB;
class DBWithCurrentObject extends DB {
    /**
     * 无需入参，操作当前对象的记录数据
     */
    // @ts-ignore
    currentObject() {
        if (!this.objectApiName) {
            throw new server_common_node_1.exceptions.InternalError(`context.objectApiName is empty`);
        }
        return new object_1._KObject(this.objectApiName);
    }
    ;
    constructor(objectApiName) {
        super(objectApiName);
    }
}
exports.DBWithCurrentObject = DBWithCurrentObject;
/**
 * ApplicationDB: 用于支持 OpenSDK 相关能力的 DB 相关类，目前仅实现 DB 同步操作接口
 */
class ApplicationDB {
    constructor(appCtx) {
        this.appCtx = appCtx;
    }
    object(objectApiName) {
        return new object_1._KApplicationObject(objectApiName, this.appCtx);
    }
}
exports.ApplicationDB = ApplicationDB;
