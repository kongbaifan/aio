/**
 * Copyright (c) 2025 Bytedance, Inc. and its affiliates.
 * SPDX-License-Identifier: Apache-2.0
 */
import type { MiddlewareFunction } from 'mcp-http-server';
import type { RequestContext } from 'mcp-http-server';
export declare const setRequestContext: (context: RequestContext) => void;
export declare const getRequestContext: () => RequestContext | undefined;
export declare const onBeforeStart: () => void;
export declare const addMiddleware: (middleware: MiddlewareFunction) => void;
export declare const getMiddlewares: () => MiddlewareFunction[];
export { setConfig } from './server.js';
export { BaseLogger } from '@agent-infra/logger';
