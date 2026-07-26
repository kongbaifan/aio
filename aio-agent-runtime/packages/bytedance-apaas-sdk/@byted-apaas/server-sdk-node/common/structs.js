"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.NewBatchResult = void 0;
function NewBatchResult(recordIDs, errMap) {
    const result = { code: "", msg: "success", data: [] };
    let hasError = false;
    recordIDs.forEach((id) => {
        const d = { _id: id, success: true };
        if (errMap && errMap[id]) {
            hasError = true;
            d.success = false;
            d.errors = [{ code: errMap[id] }];
        }
        result.data.push(d);
    });
    result.hasError = () => {
        return hasError;
    };
    return result;
}
exports.NewBatchResult = NewBatchResult;
