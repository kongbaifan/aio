export type globalFuncNames = 'a' | 'b';
export interface globalVariablesMap {
    a: string;
    b: string;
}
export type globalVariables = keyof globalVariablesMap;
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
