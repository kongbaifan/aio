## aPaaS @byted-apaas/server-sdk-node 版本说明：

### 版本: 1.1.22 | 兼容升级
优化：oql 异常抛出

### 版本：1.1.10｜兼容升级
新功能：优化部分错误码

-------
### 版本：1.1.8｜兼容升级
新功能：支持透传多分支标识

-------
### 版本：1.0.18｜兼容升级
新功能：支持开发者获取飞书集成 app access token 及 tenant access token

-------
### 版本：1.0.17｜兼容升级
优化：废弃 flow.variables & flow.updateVariable 相关 API

-------
### 版本：1.0.16|兼容升级
新功能：支持模糊查询 fuzzySearch
```js
await context.db.object("obj").fuzzySearch("keyword", ["field1", "field2"]).find();
```

-------
### 版本：1.0.15｜兼容升级
新功能：数据操作接口支持指定鉴权身份
- 不指定: 访问数据模型时, 权限 1.0 应用默认使用系统身份鉴权, 权限 2.0 应用默认使用用户身份鉴权
- useUserAuth(): 访问数据模型时, 使用用户身份鉴权
- useSystemAuth(): 访问数据模型时, 使用系统身份鉴权
```js
// 示例
await context.db.object("obj").findOne();
await context.db.object("obj").useUserAuth().findOne();
await context.db.object("obj").useSystemAuth().findOne();

await context.db.newTransaction().object("obj").commit();
await context.db.newTransaction().useUserAuth().object("obj").commit();
await context.db.newTransaction().useSystemAuth().object("obj").commit();

await context.db.oql("SELECT _id FROM obj").execute();
await context.db.oql("SELECT _id FROM obj").useUserAuth().execute();
await context.db.oql("SELECT _id FROM obj").useSystemAuth().execute();
```

### 版本：1.0.14｜兼容升级
新功能：支持流式查询 findStream
```js
await context.db.object("_user").findStream(async (records) => {
    // doSomething ...
});
```
优化：findAll 标记为过时方法，用 findStream 替代