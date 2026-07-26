/// <reference types="node" />
export interface IFileObject {
    url: string;
}
export interface IFileUploadOptions {
    type?: string;
    region?: string;
}
type uploadRet = {
    id: object;
    /**
     * 文件的 URL 地址
     */
    url: string;
};
export interface Oss {
    /**
     * 上传文件，成功时返回文件的 URL 地址。
     * @param name 文件名，只作为标识，会为每个上传文件添加唯一的 ID，即使上传多个同名文件，返回的 URL 也各自独立
     * @param file 文件内容，可以为 Buffer，字符串或者包含 url 值的文件对象
     * @param options 上传选项
     * @param addition 附加存储到文件表（_file 表）中的内容
     */
    upload: (name: string, file: (Buffer | string | IFileObject), options?: Partial<IFileUploadOptions>, addition?: object) => Promise<uploadRet>;
}
export {};
