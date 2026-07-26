/// <reference types="node" />
export interface IFile {
    /**
     * 文件上传
     * @param filename 文件名
     * @param file 文件内容 字符串/二进制/url 对象
     * @param options 上传选项 type: 文件类型, region: 上传节点
     */
    upload(filename: string, file: string | Buffer | {
        url: string;
    }, options?: {
        type?: string;
        region?: string;
    }): Promise<{
        id: Object;
        url: string;
    }>;
}
