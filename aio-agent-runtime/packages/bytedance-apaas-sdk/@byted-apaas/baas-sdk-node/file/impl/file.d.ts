/// <reference types="node" />
import { IFile } from '../IFile';
export declare class File implements IFile {
    upload(filename: string, file: string | Buffer | {
        url: string;
    }, options?: {
        type?: string;
        region?: string;
    }, addition?: {
        [key: string]: any;
    }): Promise<{
        id: Object;
        url: string;
    }>;
}
