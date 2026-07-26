/// <reference types="node" />
/// <reference types="node" />
import { Stream } from 'stream';
import { _FileInfo, _IKunlunFile, _IOpenSDKFile, UploadAvatarResult, FileUploadResult } from '../IResources';
import * as Request from '../../../request/interface';
import { AppCtx } from '../../../application/application';
export declare class _KunlunOpenSDKFile implements _IOpenSDKFile {
    appCtx: AppCtx;
    constructor(appCtx: AppCtx);
    Upload(fileName: string, path: string): Promise<FileUploadResult>;
    Upload(fileName: string, reader: Stream): Promise<FileUploadResult>;
    Upload(fileName: string, buffer: Buffer): Promise<FileUploadResult>;
    UploadAvatar(fileName: string, path: string): Promise<UploadAvatarResult>;
    UploadAvatar(fileName: string, reader: Stream): Promise<UploadAvatarResult>;
    UploadAvatar(fileName: string, buffer: Buffer): Promise<UploadAvatarResult>;
    Download(fileID: string): Promise<Buffer>;
    DownloadAvatar(imageID: string): Promise<Buffer>;
}
export declare class _KunlunFile implements _IKunlunFile {
    download(fileToken: string): Promise<Buffer>;
    download(fileToken: string, filePath?: string): Promise<void>;
    download(fileToken: _FileInfo): Promise<Buffer>;
    download(fileInfo: _FileInfo, filePath: string): Promise<void>;
    upload(filePath: string): Promise<Request.UploadFileResp>;
    upload(stream: Stream): Promise<Request.UploadFileResp>;
    upload(filePath: string, expire: number, fileName?: string): Promise<Request.UploadFileResp>;
    upload(stream: Stream, expire: number, fileName?: string): Promise<Request.UploadFileResp>;
}
/**
 * OpenSDK 静态资源操作类
 */
export declare class _OpenSDKResources {
    file: _IOpenSDKFile;
    constructor(appCtx: AppCtx);
}
/**
 * 静态资源操作类
 */
export declare class _Resources {
    file: _IKunlunFile;
    constructor();
}
