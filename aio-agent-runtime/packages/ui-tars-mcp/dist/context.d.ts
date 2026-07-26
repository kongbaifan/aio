/**
 * Copyright (c) 2025 Bytedance, Inc. and its affiliates.
 * SPDX-License-Identifier: Apache-2.0
 */
import { Page } from 'puppeteer-core';
import { ResourceContext, ToolContext } from './typings.js';
import { DOMElementNode } from '@agent-infra/browser-use';
export declare class BrowserContext {
    getResourceContext(): Promise<ResourceContext>;
    getToolContext(): Promise<ToolContext | null>;
    buildDomTree(page: Page): Promise<{
        clickableElements: string;
        elementTree: DOMElementNode;
        selectorMap: Map<number, DOMElementNode>;
    } | null>;
}
