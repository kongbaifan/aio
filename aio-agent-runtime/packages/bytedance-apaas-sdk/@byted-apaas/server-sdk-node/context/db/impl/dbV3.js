"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DBV3 = void 0;
const object_1 = require("./object");
const index_1 = require("./transaction/index");
class DBV3 {
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
        const appCtx = {
            dataVersion: 'v3',
        };
        return new object_1._KObject(objectApiName, appCtx);
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
            dataVersion: 'v3',
        };
        return new index_1.Transaction(this.objectApiName, appCtx);
    }
    ;
}
exports.DBV3 = DBV3;
