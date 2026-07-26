/**
 * The following code is modified based on
 * https://github.com/modelcontextprotocol/servers/blob/main/src/puppeteer/index.ts
 *
 * MIT License
 * Copyright (c) 2024 Anthropic, PBC
 * https://github.com/modelcontextprotocol/servers/blob/main/LICENSE
 */
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BaseLogger } from '@agent-infra/logger';
import { z } from 'zod';
import { Page } from '@agent-infra/browser';
import { Browser } from 'puppeteer-core';
import { GlobalConfig } from './typings.js';
import { getScreenshots } from './resources/index.js';
import { BrowserContext } from './context.js';
declare function setConfig(config?: GlobalConfig): void;
declare function getConfig(): GlobalConfig;
declare function setInitialBrowser(_browser?: Browser, _page?: Page): Promise<{
    browser: Browser;
    page: Page;
}>;
export declare const getBrowser: () => {
    browser: Browser | null;
    page: Page | null;
};
export declare const toolsMap: {
    browser_screenshot: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            name: z.ZodOptional<z.ZodString>;
            selector: z.ZodOptional<z.ZodString>;
            index: z.ZodOptional<z.ZodNumber>;
            width: z.ZodOptional<z.ZodNumber>;
            height: z.ZodOptional<z.ZodNumber>;
            fullPage: z.ZodOptional<z.ZodBoolean>;
            highlight: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
        }, "strip", z.ZodTypeAny, {
            highlight: boolean;
            name?: string | undefined;
            selector?: string | undefined;
            index?: number | undefined;
            width?: number | undefined;
            height?: number | undefined;
            fullPage?: boolean | undefined;
        }, {
            name?: string | undefined;
            selector?: string | undefined;
            index?: number | undefined;
            width?: number | undefined;
            height?: number | undefined;
            highlight?: boolean | undefined;
            fullPage?: boolean | undefined;
        }>;
    };
    browser_click: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            index: z.ZodOptional<z.ZodNumber>;
        }, "strip", z.ZodTypeAny, {
            index?: number | undefined;
        }, {
            index?: number | undefined;
        }>;
    };
    browser_select: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            index: z.ZodOptional<z.ZodNumber>;
            selector: z.ZodOptional<z.ZodString>;
            value: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            value: string;
            selector?: string | undefined;
            index?: number | undefined;
        }, {
            value: string;
            selector?: string | undefined;
            index?: number | undefined;
        }>;
    };
    browser_hover: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            index: z.ZodOptional<z.ZodNumber>;
            selector: z.ZodOptional<z.ZodString>;
        }, "strip", z.ZodTypeAny, {
            selector?: string | undefined;
            index?: number | undefined;
        }, {
            selector?: string | undefined;
            index?: number | undefined;
        }>;
    };
    browser_get_clickable_elements: {
        name: string;
        description: string;
    };
    browser_scroll: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            amount: z.ZodOptional<z.ZodNumber>;
        }, "strip", z.ZodTypeAny, {
            amount?: number | undefined;
        }, {
            amount?: number | undefined;
        }>;
    };
    browser_close: {
        name: string;
        description: string;
    };
    browser_press_key: {
        name: string;
        description: string;
        inputSchema: z.ZodObject<{
            key: z.ZodEnum<[string, ...string[]]>;
        }, "strip", z.ZodTypeAny, {
            key: string;
        }, {
            key: string;
        }>;
    };
};
declare function createServer(config?: GlobalConfig): McpServer;
export { BaseLogger, createServer, getScreenshots, setConfig, getConfig, type GlobalConfig, setInitialBrowser, BrowserContext, };
