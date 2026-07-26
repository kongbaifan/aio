/**
 * 在 jsdom 里把工作台真实跑起来。
 *
 * app.js 没有构建步骤、没有模块化，全部逻辑挂在顶层作用域，靠 DOMContentLoaded 启动。
 * 所以这里直接加载真实的 index.html，再把 app.js 求值进同一个 window，
 * 测的就是浏览器里跑的那份代码本身。
 *
 * index.html 引用的 marked / DOMPurify / highlight.js / lucide 都在 static/vendor/。
 * jsdom 不会自动执行 <script src>（没开 resources，开了也有 file:// 的坑），
 * 所以这里在 eval(app.js) 之前，把这几个 UMD 直接读文件注入 window——
 * 让 Markdown 渲染 / DOMPurify 净化 / 代码高亮走真实实现，而不是降级成纯文本。
 * 可以传 { vendor: false } 显式测降级路径。
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url));
const staticDir = resolve(here, "../../app/static");

const INDEX_HTML = readFileSync(resolve(staticDir, "index.html"), "utf-8");
const APP_JS = readFileSync(resolve(staticDir, "app.js"), "utf-8");

// index.html <script src> 引用顺序，注入 window 用。lucide 是 defer 的图标库，
// 测试里不需要（图标渲染不影响断言），省掉避免它的 DOM 副作用。
const VENDOR_SCRIPTS = ["marked.min.js", "purify.min.js", "highlight.min.js"];

function installVendor(window) {
  for (const name of VENDOR_SCRIPTS) {
    const code = readFileSync(resolve(staticDir, "vendor", name), "utf-8");
    // UMD 会挂到它们在 window 上的全局名（marked / DOMPurify / hljs）。
    window.eval(code);
  }
  // lucide 缺席时 app.js 的 refreshIcons 已做空值保护，这里补一个 no-op 兜底，
  // 免得偶发路径触发 window.lucide.createIcons 报错。
  window.lucide = window.lucide || { createIcons() {} };
}

/**
 * 把若干帧拼成 SSE 响应体，可选按 chunk 切分以模拟分片到达。
 *
 * endWith 控制帧发完之后怎么收场：
 *   "close"（默认）—— 正常 EOF
 *   "drop"         —— 连接被对端掐断（读到一半断网 / 服务端进程被 kill）
 *   "hang"         —— 永远不结束，用来测「用户点停止」和确认框悬挂
 */
export function sseResponse(frames, { chunks = 1, endWith = "close" } = {}) {
  const text = frames.map(frame => `data: ${JSON.stringify(frame)}\n\n`).join("");
  const bytes = new TextEncoder().encode(text);
  const size = Math.max(1, Math.ceil(bytes.length / chunks));
  const slices = [];
  for (let offset = 0; offset < bytes.length; offset += size) {
    slices.push(bytes.slice(offset, offset + size));
  }
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader() {
        return {
          async read() {
            if (index < slices.length) return { done: false, value: slices[index++] };
            if (endWith === "drop") {
              throw Object.assign(new Error("network error"), { name: "TypeError" });
            }
            if (endWith === "hang") return new Promise(() => {}); // 永不 settle
            return { done: true, value: undefined };
          },
          cancel() {},
        };
      },
    },
  };
}

function encodeFrame(frame) {
  return new TextEncoder().encode(`data: ${JSON.stringify(frame)}\n\n`);
}

/**
 * 手动驱动的 SSE 流：模拟服务端「发到某一帧就挂起等待」的真实时序。
 *
 * confirm 帧正是这种情况——服务端 agent 阻塞在人工确认上，done 帧只可能在
 * 用户做出决定之后才发出。用一次性发完所有帧（含 done）的 fixture 去测确认框，
 * 测的是现实里不会发生的顺序，也测不出「流结束后弹窗还在」这类缺陷。
 *
 * 用法：push() 追加帧并唤醒读取，close() 结束流。
 */
export function controlledSse(initialFrames = []) {
  const queue = initialFrames.map(encodeFrame);
  let wake = null;
  let closed = false;
  const reader = {
    async read() {
      while (!queue.length && !closed) {
        await new Promise(resolve => { wake = resolve; });
      }
      if (queue.length) return { done: false, value: queue.shift() };
      return { done: true, value: undefined };
    },
    cancel() { closed = true; wake?.(); wake = null; },
  };
  const resume = () => { const w = wake; wake = null; w?.(); };
  return {
    response: { ok: true, status: 200, body: { getReader: () => reader } },
    push(...frames) { queue.push(...frames.map(encodeFrame)); resume(); },
    close() { closed = true; resume(); },
  };
}

function abortError() {
  return Object.assign(new Error("The operation was aborted."), { name: "AbortError" });
}

/**
 * 给流式响应套上 AbortSignal 语义。
 *
 * 之前假 fetch 完全忽略 options.signal，reader 也没有 cancel()，
 * 所以 sendMessage 里 error.name === "AbortError" 的整条分支零覆盖——
 * 「运行中切会话」这类缺陷根本测不出来。
 */
function withSignal(response, signal) {
  if (!signal || !response?.body?.getReader) return response;
  return {
    ...response,
    body: {
      getReader() {
        const reader = response.body.getReader();
        return {
          async read() {
            if (signal.aborted) throw abortError();
            // race：即使底层 read 永远挂着（endWith:"hang"），abort 也能立刻打断。
            return Promise.race([
              reader.read(),
              new Promise((_, reject) =>
                signal.addEventListener("abort", () => reject(abortError()), { once: true })
              ),
            ]);
          },
          cancel: () => reader.cancel?.(),
        };
      },
    },
  };
}

export function jsonResponse(data) {
  return { ok: true, status: 200, json: async () => data, text: async () => JSON.stringify(data) };
}

/** 初始化时那几个 GET 的最小可用返回值。 */
const DEFAULT_ROUTES = {
  "/api/health": () =>
    jsonResponse({
      status: "ok",
      provider: "fake",
      model: "fake-1",
      model_label: "fake/fake-1",
      sandbox: { status: "ok" },
      node: { status: "disabled" },
      tools: ["list_files", "read_skill"],
      skills: 2,
      mcp: { status: "optional", name: "t", transport: "stdio", tools: [] },
    }),
  "/api/models": () =>
    jsonResponse({
      default: { provider: "fake", model: "fake-1", label: "fake/fake-1" },
      models: [{ provider: "fake", id: "fake-1", label: "fake/fake-1", available: true, name: "fake-1" }],
    }),
  "/api/sessions": () => jsonResponse({ sessions: [] }),
  "/api/files": () => jsonResponse({ items: [], cwd: "." }),
  "/api/skills": () => jsonResponse({ skills: [] }),
};

/**
 * 启动一个工作台实例。
 *
 * routes 可覆盖或新增路由，值是 (url, options) => response。
 * 返回 { window, document, calls, submit, flush, close }。
 */
export async function launchWorkbench({ routes = {}, vendor = true } = {}) {
  const dom = new JSDOM(INDEX_HTML, {
    url: "http://127.0.0.1:8080/",
    runScripts: "dangerously",
    pretendToBeVisual: true, // 提供 requestAnimationFrame，打字机合批要用
  });
  const { window } = dom;
  const calls = [];
  const table = { ...DEFAULT_ROUTES, ...routes };

  window.fetch = async (path, options = {}) => {
    calls.push({ path, options });
    if (options.signal?.aborted) throw abortError();
    const key = String(path).split("?")[0];
    const handler = table[key];
    if (!handler) {
      return { ok: false, status: 404, json: async () => ({ detail: `no route ${key}` }) };
    }
    return withSignal(await handler(path, options), options.signal);
  };
  // app.js 里 readSse 会用到，jsdom 未必挂在 window 上
  window.TextDecoder = window.TextDecoder || TextDecoder;
  window.TextEncoder = window.TextEncoder || TextEncoder;
  installDialogPolyfill(window);

  // 先让 jsdom 自己的 DOMContentLoaded 过去，再注入 app.js，最后手动补派一次。
  //
  // 否则会触发两次 initialize：eval 时 jsdom 还没派发 DOMContentLoaded，
  // app.js 注册了监听器，随后 jsdom 派发一次 + 这里手动派发一次。
  // 后果是 bindEvents() 跑两遍、所有监听器都成双份——一次表单提交会进两次
  // handler，第二次看到 state.busy 已是 true 就调 stopRequest()，
  // 把刚发出去的请求 abort 掉。以前假 fetch 忽略 signal，abort 无效，
  // 这个问题就一直被掩盖着。
  await new Promise(resolve => {
    if (window.document.readyState !== "loading") return resolve();
    window.document.addEventListener("DOMContentLoaded", () => resolve(), { once: true });
  });
  // 真实第三方库先于 app.js 注入，让渲染/净化/高亮走真实实现而非降级。
  if (vendor) installVendor(window);
  window.eval(APP_JS);
  window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  await flush(window);

  return {
    window,
    document: window.document,
    calls,
    flush: () => flush(window),
    /** 等当前任务结束（发送按钮复位）；流没结束会抛。 */
    settle: () => settle(window),
    /**
     * 填入内容并提交表单。
     *
     * 默认等整条 SSE 链路跑完；wait:false 只推进到「请求已发出」，
     * 用于流会中途挂起的场景（等人工确认、测停止按钮）。
     */
    async submit(text, { wait = true } = {}) {
      const input = window.document.getElementById("messageInput");
      input.value = text;
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
      window.document
        .getElementById("chatForm")
        .dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
      if (wait) await settle(window);
      else await flush(window);
    },
    /** 点「停止任务」：busy 时表单提交走的是 stopRequest 分支。 */
    async stop() {
      window.document
        .getElementById("chatForm")
        .dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
      await settle(window);
    },
    close: () => window.close(),
  };
}

/**
 * jsdom 认识 <dialog> 元素，但没实现 showModal/close。
 * 确认框依赖它们，这里补一个最小实现（只维护 open 状态并派发 close 事件）。
 */
function installDialogPolyfill(window) {
  const proto = window.HTMLDialogElement?.prototype ?? window.HTMLElement.prototype;
  if (typeof proto.showModal !== "function") {
    proto.showModal = function showModal() {
      this.open = true;
    };
  }
  if (typeof proto.close !== "function") {
    proto.close = function close() {
      this.open = false;
      this.dispatchEvent(new window.Event("close"));
    };
  }
}

/** 让挂起的 microtask 和 rAF 回调都跑完。 */
export async function flush(window, rounds = 4) {
  for (let i = 0; i < rounds; i += 1) {
    await new Promise(done => setTimeout(done, 0));
    await new Promise(done => window.requestAnimationFrame(() => done()));
  }
}

/**
 * 等一次任务真正结束。
 *
 * setBusy 会给发送按钮挂 .running，用它判断比空转固定轮数的 rAF 快得多，
 * 也不会因为链路稍慢就漏断言。
 */
export async function settle(window, timeoutMs = 5000) {
  const button = window.document.getElementById("sendButton");
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline && button?.classList.contains("running")) {
    await new Promise(done => setTimeout(done, 2));
  }
  // 超时必须抛。以前这里是静默放行，等于没人断言过按钮会复位——
  // setBusy(false) 被误删的话所有用例照样全绿，只是每个慢 5 秒，
  // 而「流中断后 UI 卡在 loading」正是这类缺陷。
  if (button?.classList.contains("running")) {
    throw new Error(`任务在 ${timeoutMs}ms 内没有结束：sendButton 仍带 .running（UI 卡在执行中）`);
  }
  await flush(window, 2);
}

/** 收集对话流里的消息气泡。 */
export function messages(document) {
  return [...document.querySelectorAll(".message")].map(node => ({
    role: node.classList.contains("user") ? "user" : "assistant",
    error: node.classList.contains("error"),
    text: (node.querySelector(".message-body")?.textContent || "").trim(),
  }));
}
