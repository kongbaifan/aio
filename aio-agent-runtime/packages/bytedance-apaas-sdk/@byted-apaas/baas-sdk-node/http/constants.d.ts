import { PostHttpConfig, GetHttpConfig } from '@byted-apaas/server-common-node/http/config';
export declare const metricsMethodKeys: Record<string, string>;
export declare const faasinfraHttpPath: {
    requestMongodb: PostHttpConfig;
    requestFile: PostHttpConfig;
    requestRedis: PostHttpConfig;
    requestGlobalVar: GetHttpConfig;
};
