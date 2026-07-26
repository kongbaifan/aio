import type { Viewport } from 'puppeteer-core';
import { ToolDefinition } from '../typings.js';
export declare const delayReject: (ms: number) => Promise<unknown>;
export declare const delay: (ms: number) => Promise<unknown>;
/**
 * Validate if either selector or index is provided
 * @param args - The arguments to validate
 * @returns True if either selector or index is provided, false otherwise
 */
export declare function validateSelectorOrIndex(args: {
    selector?: string;
    index?: number;
    [key: string]: any;
}): boolean;
export declare function defineTools<T extends Record<keyof T, ToolDefinition>>(tools: T): T;
/**
 * Parse proxy url to username and password
 * @param proxyUrl - proxy url
 * @returns username and password
 */
export declare function parseProxyUrl(proxyUrl: string): {
    username: string;
    password: string;
};
export declare function parseViewportSize(viewportSize: string): Viewport | undefined;
export declare function parserFactor(factor: string): [number, number] | undefined;
export declare function sanitizeForFilePath(s: string): string;
/**
 * get download suggestion
 *
 * @param downloadsBefore before download
 * @param downloadsAfter after download
 * @param downloadedFiles downloaded files
 * @returns download suggestion
 */
export declare function getDownloadSuggestion(downloadsBefore: number, downloadedFiles: Array<{
    suggestedFilename?: string;
}>, outputDir: string): string;
