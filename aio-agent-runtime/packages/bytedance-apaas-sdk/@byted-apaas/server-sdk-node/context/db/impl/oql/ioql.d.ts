export interface IOql {
    /**
     * 执行 OQL
     */
    execute(): Promise<any | any[]>;
    /**
     * 用户级鉴权
     */
    useUserAuth(): IOql;
    /**
     * 系统级鉴权
     */
    useSystemAuth(): IOql;
}
