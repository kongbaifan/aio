import { z } from 'zod';
declare const _default: import("./defineTool.js").ToolDefinition<{
    description: string;
    inputSchema: {
        selector: z.ZodOptional<z.ZodString>;
        index: z.ZodOptional<z.ZodNumber>;
        value: z.ZodString;
        clear: z.ZodDefault<z.ZodOptional<z.ZodBoolean>>;
    };
}, false>[];
export default _default;
