"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.newFlow = void 0;
const flow_1 = require("./impl/flow");
function newFlow(context) {
    return new flow_1.Flow(context?.flow);
}
exports.newFlow = newFlow;
