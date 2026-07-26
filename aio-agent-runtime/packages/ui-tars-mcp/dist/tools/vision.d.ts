import { z } from 'zod';
declare const _default: (import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {};
}, false> | import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {
        factors: z.ZodOptional<z.ZodArray<z.ZodNumber, "many">>;
        x: z.ZodNumber;
        y: z.ZodNumber;
    };
}, false>)[];
export default _default;
