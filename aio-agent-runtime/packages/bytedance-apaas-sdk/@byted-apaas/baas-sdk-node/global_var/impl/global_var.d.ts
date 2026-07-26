import { IGlobalVar } from "../global_var";
export declare class GlobalVar implements IGlobalVar {
    getVar(key: string): Promise<any>;
}
