# AIO Sandbox 技术栈学习路线图

> 起点：Python 基础为零（学了两天）  
> 目标：能独立理解和改造本项目  
> 周期：约 6-9 个月

---

## ✅ Phase 1：Python 基础（第 1-2 个月）

### 第 1 周：基础语法
- [ ] 变量、数字、字符串
- [ ] 列表、字典、元组、集合（增删改查）
- [ ] `if/elif/else` 条件判断
- [ ] `for/while` 循环
- [ ] 函数定义、参数、返回值

**练习：** 写一个计算器脚本 → 猜数字游戏 → 九九乘法表

### 第 2 周：进阶语法
- [ ] 文件读写 `open/with`（txt/json/csv）
- [ ] 异常处理 `try/except/finally`
- [ ] 模块和包 `import`
- [ ] 列表推导式
- [ ] `lambda` / `map` / `filter`

**对应本项目：** `server.py` 的 `read_file` / `write_file`、所有 `try/except`

### 第 3 周：面向对象
- [ ] `class` / `__init__` / `self`
- [ ] 实例方法 vs 类方法 vs 静态方法
- [ ] 继承和方法重写
- [ ] 魔术方法 `__str__`、`__repr__`
- [ ] 装饰器 `@app.get` / `@app.post`（**重点**）

**对应本项目：** `WorkspaceManager` 类、Pydantic 的 `BaseModel`

### 第 4 周：异步编程
- [ ] `async def` / `await` 语法
- [ ] `asyncio.run()` 事件循环
- [ ] `asyncio.sleep` / `asyncio.create_task`
- [ ] 同步 vs 异步的区别（**重点**）
- [ ] async 上下文管理器 `async with`

**对应本项目：** 所有 FastAPI 端点、WebSocket 终端

> **验收标准：** 能写一个异步 HTTP 请求爬虫

---

## ✅ Phase 2：Python Web 框架（第 2-3 个月）

### 第 5-6 周：FastAPI
- [ ] 路由定义 `@app.get/post/put/delete`
- [ ] 路径参数 `{id}` 和查询参数 `?name=x`
- [ ] 请求体注入 `Body` / `Query` / `Header`
- [ ] Pydantic 模型 `BaseModel`
- [ ] 响应模型 `response_model`
- [ ] 错误处理 `HTTPException`（404/403/400）
- [ ] 文件上传和下载（`UploadFile` / `FileResponse`）
- [ ] CORS 中间件配置
- [ ] 中间件（Middleware）编写

**练习：** TODO 清单 API（CRUD）

### 第 7 周：服务器部署
- [ ] `uvicorn.run` 参数配置
- [ ] `--reload` 热重载
- [ ] 日志配置
- [ ] 理解 ASGI 协议基本概念

### 第 8 周：WebSocket
- [ ] WebSocket 握手流程
- [ ] `receive_json` / `send_json`
- [ ] 心跳机制 `ping/pong`
- [ ] 多客户端 session 管理
- [ ] 连接断开重连

**练习：** 写一个 WebSocket 聊天室

> **验收标准：** 能读懂并修改 `server.py` 的所有端点

---

## ✅ Phase 3：前端三件套（第 3-4 个月）

### 第 9 周：HTML
- [ ] 基础标签 `div/span/button/input/a`
- [ ] `class` / `id` / `data-*` 属性
- [ ] 表单和输入类型
- [ ] `iframe` 嵌入
- [ ] 语义化标签 `header/footer/section`

### 第 10 周：CSS
- [ ] 选择器（class/id/属性/伪类/组合）
- [ ] Flexbox（**重点**）`display:flex` / `flex-grow` / `flex-shrink` / `flex-basis`
- [ ] 颜色、字体、边框、背景
- [ ] `position: static/relative/absolute/fixed`
- [ ] `transform` / `transition` 动画
- [ ] `z-index` 层叠上下文

### 第 11 周：JavaScript 基础
- [ ] `let/const`、数据类型
- [ ] 函数声明、箭头函数 `() => {}`
- [ ] DOM 操作（`getElementById` / `querySelector` / `createElement`）
- [ ] 事件监听（`click/mousemove/keydown/input`）
- [ ] `fetch` API（**重点**）GET / POST JSON
- [ ] `JSON.parse` / `JSON.stringify`
- [ ] `async/await` 和 Promise

### 第 12 周：JavaScript 进阶
- [ ] `class` 语法和面向对象
- [ ] 闭包和作用域
- [ ] 数组方法 `map/filter/reduce/forEach`
- [ ] 对象解构 `{...obj}`、展开运算符
- [ ] `localStorage` 持久化
- [ ] `WebSocket` API 客户端

> **验收标准：** 能用 fetch 调后端 API 并渲染页面

---

## ✅ Phase 4：协议与系统基础（第 4-5 个月）

### 第 13-14 周：HTTP 协议
- [ ] 请求方法 GET/POST/PUT/DLEETE/PATCH
- [ ] 状态码：2xx / 3xx / 4xx / 5xx
- [ ] Header：Content-Type / Authorization / Cookie
- [ ] RESTful API 设计原则
- [ ] JSON 数据格式

### 第 15 周：Linux 基础
- [ ] 文件系统结构
- [ ] 常用命令 ls/cd/cp/mv/rm/ps/kill/grep
- [ ] 权限 chmod/chown
- [ ] 环境变量 export
- [ ] 进程管理 ps/kill/nohup

### 第 16 周：Docker 基础
- [ ] Dockerfile 编写
- [ ] docker build / run / ps / exec
- [ ] 端口映射 `-p`
- [ ] 数据卷 `-v`
- [ ] docker-compose 编排

> **验收标准：** 能 Docker 部署自己的 FastAPI 应用

---

## ✅ Phase 5：扩展语言（第 5-7 个月）

### 第 17-20 周：Node.js / JavaScript
- [ ] Node.js 运行时和 npm
- [ ] package.json / 依赖管理
- [ ] CommonJS / ES Modules
- [ ] Fastify 框架
- [ ] Worker Threads 多线程
- [ ] VM 沙箱执行

**对应本项目：** `09_nodejs_repl_server`

### 第 21-24 周：Go 语言
- [ ] 变量、类型、函数、结构体
- [ ] goroutine 和 channel（并发）
- [ ] `net/http` 处理请求
- [ ] TLS/HTTPS 基础
- [ ] 指针和接口

**对应本项目：** `10_hijack_proxy_go_source`

> **验收标准：** 能读懂对应目录的源码主体逻辑

---

## ✅ Phase 6：项目实战（第 7-9 个月）

### 第 25-28 周：按顺序研读本项目
- [ ] `server.py` — FastAPI 服务器源码
- [ ] `index.html` — 前端面板架构
- [ ] `terminal-ui.html` — WebSocket 交互
- [ ] `04_gem_process_manager/nginx/` — 反向代理配置
- [ ] `03_python_server_source/helpers/` — 工具函数
- [ ] `01_complete_skills/` — Agent 技能结构
- [ ] `10_hijack_proxy_go_source/` — MITM 代理
- [ ] `07_fastmcp_python_framework/` — MCP 协议实现

### 练习项目清单
- [ ] **记事本 API**（Python + FastAPI）→ 第 2 个月
- [ ] **个人博客前端**（HTML + CSS + JS）→ 第 3 个月
- [ ] **在线 Python 代码运行器**（FastAPI + Docker）→ 第 4 个月
- [ ] **简单 HTTP 代理**（Go）→ 第 6 个月
- [ ] **自己改一版前端面板**（全栈）→ 第 8 个月

---

## 📅 日学习计划建议

| 时间 | 学习内容 |
|------|---------|
| 周一三五（1-2h） | 学新知识：看教程、读文档 |
| 周二四六（1-2h） | 动手练习：写代码、改项目 |
| 周日（2-3h） | 复习总结 + 整理笔记 |

---

## 📚 推荐资源

| 领域 | 资源 |
|------|------|
| Python | 廖雪峰 Python 教程 / Python 官方 Tutorial |
| FastAPI | FastAPI 官方文档（有中文） |
| HTML/CSS | MDN Web Docs / FreeCodeCamp |
| JavaScript | JavaScript.info |
| HTTP | MDN HTTP 指南 |
| Linux | 《鸟哥的 Linux 私房菜》基础篇 |
| Docker | Docker 官方 Getting Started |
| Go | Go 官方 Tour of Go |
| 本项目 | `aio-sandbox-lite/` 源码作为练习入口 |
