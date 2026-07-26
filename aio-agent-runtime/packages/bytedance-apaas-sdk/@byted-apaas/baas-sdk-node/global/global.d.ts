import { IRedis } from '../redis/IRedis';
import { IMongodb } from '../mongodb/mongodb';
declare global {
    export module baas {
        /**
         * 缓存数据库
         */
        let redis: IRedis;
        /**
         * 文档数据库
         */
        let mongodb: IMongodb;
    }
}
