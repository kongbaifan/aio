import { z } from 'zod';
declare const _default: (import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {
        url: z.ZodString;
    };
}, false> | import("./defineTool.js").ToolDefinition<{
    description: string;
    outputSchema: {
        tabList: z.ZodArray<z.ZodObject<{
            index: z.ZodNumber;
            active: z.ZodBoolean;
            title: z.ZodString;
            url: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            title: string;
            index: number;
            active: boolean;
            url: string;
        }, {
            title: string;
            index: number;
            active: boolean;
            url: string;
        }>, "many">;
    };
}, false> | import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {
        index: z.ZodNumber;
    };
}, false> | import("./defineTool.js").ToolDefinition<{
    description: string;
}, false>)[];
export default _default;
