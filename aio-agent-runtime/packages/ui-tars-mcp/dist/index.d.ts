#!/usr/bin/env node
import { BaseLogger } from '@agent-infra/logger';
import { setConfig } from './server.js';
import { getRequestContext, onBeforeStart, addMiddleware } from './request-context.js';
declare global {
    interface Window {
        mcpHelper: {
            logs: string[];
            originalConsole: Partial<typeof console>;
        };
    }
}
export { setConfig, BaseLogger, getRequestContext, onBeforeStart, addMiddleware, };
