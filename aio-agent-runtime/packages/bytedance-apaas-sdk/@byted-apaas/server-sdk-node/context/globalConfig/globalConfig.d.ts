export declare class GlobalConfig {
    /**
     * 根据 key 获取对应的全局变量
     * @param key 全局变量的 key
     */
    getVar<valueT>(key: string): Promise<valueT>;
}
