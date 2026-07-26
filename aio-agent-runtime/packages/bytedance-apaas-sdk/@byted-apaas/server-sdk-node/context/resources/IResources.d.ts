/// <reference types="node" />
/// <reference types="node" />
import { Stream } from 'stream';
import { UploadFileResp } from '../../request/interface';
export interface _FileInfo {
    id: string;
}
export interface _IKunlunFile {
    /**
     * 上传文件
     * @param filePath 文件路径
     * @param expire 文件过期时间，可选，单位：秒
     * @param fileName 文件名，可选
     */
    upload(filePath: string, expire?: number, fileName?: string): Promise<UploadFileResp>;
    /**
     * 上传文件
     * @param stream 文件流
     * @param expire 文件过期时间，可选，单位：秒
     * @param fileName 文件名，可选
     */
    upload(stream: Stream, expire?: number, fileName?: string): Promise<UploadFileResp>;
    /**
     * 下载文件
     * @param fileToken 文件令牌
     */
    download(fileToken: string): Promise<Buffer>;
    /**
     * 下载文件
     * @param fileToken 文件令牌
     * @param filePath 文件保存的路径
     */
    download(fileToken: string, filePath: string): Promise<void>;
    /**
     * 下载文件
     * @param fileInfo 文件信息
     */
    download(fileInfo: _FileInfo): Promise<Buffer>;
    /**
     * 下载文件
     * @param fileInfo 文件信息
     * @param filePath 文件保存的路径
     */
    download(fileInfo: _FileInfo, filePath: string): Promise<void>;
}
export type FileUploadResult = {
    fileId: string;
    type: string;
    name: string;
    size: number;
};
export type UploadAvatarResult = {
    ImageId: string;
    PreviewImageId: string;
};
export interface _IOpenSDKFile {
    Upload(fileName: string, path: string): Promise<FileUploadResult>;
    Upload(fileName: string, reader: Stream): Promise<FileUploadResult>;
    Upload(fileName: string, buffer: Buffer): Promise<FileUploadResult>;
    UploadAvatar(fileName: string, path: string): Promise<UploadAvatarResult>;
    UploadAvatar(fileName: string, reader: Stream): Promise<UploadAvatarResult>;
    UploadAvatar(fileName: string, buffer: Buffer): Promise<UploadAvatarResult>;
    Download(fileID: string): Promise<Buffer>;
    DownloadAvatar(imageID: string): Promise<Buffer>;
}
export interface _IOpenSDKResources {
    file: _IOpenSDKFile;
}
