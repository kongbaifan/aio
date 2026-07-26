import { z } from 'zod';
declare const _default: import("./defineTool.js").ToolDefinition<{
    description: string;
    outputSchema: {
        list: z.ZodArray<z.ZodObject<{
            guid: z.ZodOptional<z.ZodString>;
            url: z.ZodOptional<z.ZodString>;
            suggestedFilename: z.ZodOptional<z.ZodString>;
            resourceUri: z.ZodOptional<z.ZodString>;
            createdAt: z.ZodOptional<z.ZodString>;
            progress: z.ZodOptional<z.ZodNumber>;
            state: z.ZodOptional<z.ZodString>;
        }, "strip", z.ZodTypeAny, {
            url?: string | undefined;
            progress?: number | undefined;
            guid?: string | undefined;
            suggestedFilename?: string | undefined;
            resourceUri?: string | undefined;
            createdAt?: string | undefined;
            state?: string | undefined;
        }, {
            url?: string | undefined;
            progress?: number | undefined;
            guid?: string | undefined;
            suggestedFilename?: string | undefined;
            resourceUri?: string | undefined;
            createdAt?: string | undefined;
            state?: string | undefined;
        }>, "many">;
    };
}, true>[];
export default _default;
