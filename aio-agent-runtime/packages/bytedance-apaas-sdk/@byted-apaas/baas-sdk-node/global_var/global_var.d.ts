export interface IGlobalVar {
    /**
     * 获取全局变量
     * @param key 全局变量的唯一键
     */
    getVar(key: string): Promise<any>;
}
