export declare class GlobalVar<gv> {
    /**
     * 根据 apiName 获取对应的全局变量
     * @param apiName 全局变量的 API Name
     */
    getVar<Key extends keyof gv>(apiName: Key): Promise<gv[Key]>;
}
