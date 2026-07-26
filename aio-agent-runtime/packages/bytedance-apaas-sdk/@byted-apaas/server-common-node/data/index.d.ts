export interface workflowVariables {
    _initiator: User;
    _initialRecord: any;
}
export type globalFuncNames = 'a' | 'b';
export type globalVariables = 'a' | 'b';
export interface metadataMap {
    /**
     * @description 用户
     */
    _user: User;
    _department: Department;
}
export type currentObjApiName = '_user';
interface User {
    _name: string;
    _id: number;
    _department: Department;
}
interface Department {
    _id: number;
    _name: string;
    _superior: Department;
}
export {};
