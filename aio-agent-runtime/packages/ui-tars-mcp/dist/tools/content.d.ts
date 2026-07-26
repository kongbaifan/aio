import { z } from 'zod';
declare const _default: (import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {};
}, false> | import("./defineTool.js").ToolDefinition<{
    description: string;
    outputSchema: {
        links: z.ZodArray<z.ZodObject<{
            text: z.ZodString;
            href: z.ZodString;
        }, "strip", z.ZodTypeAny, {
            text: string;
            href: string;
        }, {
            text: string;
            href: string;
        }>, "many">;
    };
}, false>)[];
export default _default;
