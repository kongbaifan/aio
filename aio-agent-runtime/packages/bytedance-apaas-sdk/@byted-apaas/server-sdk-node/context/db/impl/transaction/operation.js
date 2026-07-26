"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.BatchUpdateSameValueOperation = exports.BatchDeleteOperation = exports.BatchUpdateOperation = exports.BatchCreateOperation = exports.DeleteOperation = exports.UpdateOperation = exports.CreateOperation = exports.TransactionOperation = void 0;
const exceptions = require('@byted-apaas/server-common-node').exceptions;
var OperationType;
(function (OperationType) {
    OperationType[OperationType["OPERATION_TYPE_CREATE"] = 1] = "OPERATION_TYPE_CREATE";
    OperationType[OperationType["OPERATION_TYPE_UPDATE"] = 2] = "OPERATION_TYPE_UPDATE";
    OperationType[OperationType["OPERATION_TYPE_DELETE"] = 3] = "OPERATION_TYPE_DELETE";
    OperationType[OperationType["OPERATION_TYPE_BATCH_CREATE"] = 4] = "OPERATION_TYPE_BATCH_CREATE";
    OperationType[OperationType["OPERATION_TYPE_BATCH_UPDATE"] = 5] = "OPERATION_TYPE_BATCH_UPDATE";
    OperationType[OperationType["OPERATION_TYPE_BATCH_DELETE"] = 6] = "OPERATION_TYPE_BATCH_DELETE";
    OperationType[OperationType["OPERATION_TYPE_BATCH_UPDATE_SAME_VALUE"] = 7] = "OPERATION_TYPE_BATCH_UPDATE_SAME_VALUE";
})(OperationType || (OperationType = {}));
class TransactionOperation {
    constructor(operationType, objectApiName, input) {
        this.operationType = operationType;
        this.objectApiName = objectApiName;
        try {
            this.input = JSON.stringify(input);
        }
        catch (e) {
            throw new exceptions.InvalidParamError(e.message);
        }
    }
}
exports.TransactionOperation = TransactionOperation;
class CreateOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_CREATE, objectApiName, input);
    }
}
exports.CreateOperation = CreateOperation;
class UpdateOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_UPDATE, objectApiName, input);
    }
}
exports.UpdateOperation = UpdateOperation;
class DeleteOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_DELETE, objectApiName, input);
    }
}
exports.DeleteOperation = DeleteOperation;
class BatchCreateOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_BATCH_CREATE, objectApiName, input);
    }
}
exports.BatchCreateOperation = BatchCreateOperation;
class BatchUpdateOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_BATCH_UPDATE, objectApiName, input);
    }
}
exports.BatchUpdateOperation = BatchUpdateOperation;
class BatchDeleteOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_BATCH_DELETE, objectApiName, input);
    }
}
exports.BatchDeleteOperation = BatchDeleteOperation;
class BatchUpdateSameValueOperation extends TransactionOperation {
    constructor(objectApiName, input) {
        super(OperationType.OPERATION_TYPE_BATCH_UPDATE_SAME_VALUE, objectApiName, input);
    }
}
exports.BatchUpdateSameValueOperation = BatchUpdateSameValueOperation;
