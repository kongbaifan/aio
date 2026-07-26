import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { ResourceContext } from '../typings.js';
declare const consoleLogs: string[];
declare const screenshots: Map<string, string>;
declare const getScreenshots: () => Map<string, string>;
export { consoleLogs, screenshots, getScreenshots };
export declare const registerResources: (server: McpServer, ctx: ResourceContext) => void;
