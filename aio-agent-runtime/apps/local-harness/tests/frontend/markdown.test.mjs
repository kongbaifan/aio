/**
 * Markdown 渲染 / DOMPurify 净化 / 代码高亮的真实行为。
 *
 * 这些一直是零覆盖：harness 以前没加载 vendor，renderMarkdownInto 永远走
 * container.textContent = raw 的降级分支。现在 vendor 真实注入，这里测的是
 * 浏览器里实际跑的那条路径——包括最要紧的一条：模型输出的 HTML 被净化。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { launchWorkbench, sseResponse } from "./harness.mjs";

const opened = [];
after(() => opened.forEach(app => app.close()));

async function renderAssistant(answer, { vendor = true } = {}) {
  const app = await launchWorkbench({
    vendor,
    routes: {
      "/api/chat/stream": () =>
        sseResponse([
          { kind: "start", session_id: "s1", matched: [] },
          { kind: "answer", answer },
          { kind: "done", session_id: "s1", files: [] },
        ]),
    },
  });
  opened.push(app);
  await app.submit("问一句");
  return app.document.querySelector(".message.assistant .message-body");
}

describe("vendor 真实加载（自检）", () => {
  it("marked / DOMPurify / hljs 确实注入了 window", async () => {
    // 如果注入失败，上面所有渲染/净化用例会因为走降级分支而"假绿"。
    // 这条把前提钉死：库不在，就直接红在这里。
    const app = await launchWorkbench({});
    opened.push(app);
    const { window } = app;
    assert.equal(typeof window.marked?.parse, "function", "marked 未加载");
    assert.equal(typeof window.DOMPurify?.sanitize, "function", "DOMPurify 未加载");
    assert.equal(typeof window.hljs?.highlightElement, "function", "highlight.js 未加载");
  });
});

describe("Markdown 渲染", () => {
  it("加粗被渲染成 <strong>", async () => {
    const body = await renderAssistant("这是 **重点** 内容");
    const strong = body.querySelector("strong");
    assert.ok(strong, "** 应该渲染成 <strong>");
    assert.equal(strong.textContent, "重点");
  });

  it("链接统一新开标签页并加 noopener", async () => {
    const body = await renderAssistant("见 [文档](https://example.com)");
    const link = body.querySelector("a[href]");
    assert.ok(link);
    assert.equal(link.getAttribute("target"), "_blank");
    assert.match(link.getAttribute("rel") || "", /noopener/);
  });

  it("代码块被 highlight.js 处理（打上 hljs 类和高亮 span）", async () => {
    const body = await renderAssistant("```python\nprint('hi')\n```");
    const code = body.querySelector("pre code");
    assert.ok(code, "应该有代码块");
    // hljs.highlightElement 会加 `hljs` 类（marked 只加 language-xxx，区分得开），
    // 并把关键字包进 .hljs-* 的 span。两者都查，才测到的是高亮本身而非 marked。
    assert.match(code.className, /\bhljs\b/, "highlight.js 应加 hljs 类");
    assert.ok(code.querySelector('[class^="hljs-"]'), "应有高亮 span");
  });
});

describe("DOMPurify 净化", () => {
  it("模型输出里的 <script> 被剥掉", async () => {
    const body = await renderAssistant("正常文字<script>window.__pwned=1</script>结尾");
    assert.equal(body.querySelector("script"), null, "<script> 必须被净化掉");
    assert.equal(body.ownerDocument.defaultView.__pwned, undefined, "脚本不能执行");
    assert.match(body.textContent, /正常文字/);
  });

  it("危险的内联事件属性被剥掉", async () => {
    const body = await renderAssistant("<img src=x onerror=\"window.__xss=1\">");
    const img = body.querySelector("img");
    // img 本身可保留，但 onerror 必须被净化。
    if (img) assert.equal(img.getAttribute("onerror"), null);
    assert.equal(body.ownerDocument.defaultView.__xss, undefined);
  });

  it("javascript: 协议的链接被净化", async () => {
    const body = await renderAssistant("[点我](javascript:alert(1))");
    const link = body.querySelector("a[href]");
    if (link) assert.doesNotMatch(link.getAttribute("href") || "", /^javascript:/i);
  });
});

describe("降级路径仍然安全", () => {
  it("vendor 缺席时退回纯文本，不解析任何标记", async () => {
    // 显式关掉 vendor，验证 renderMarkdownInto 的降级分支：
    // 既不渲染 Markdown，也绝不会把 HTML 当标记插进 DOM。
    const body = await renderAssistant("**粗**<script>window.__x=1</script>", { vendor: false });
    assert.equal(body.querySelector("strong"), null, "降级时不解析 Markdown");
    assert.equal(body.querySelector("script"), null, "降级时也不能注入 HTML");
    assert.equal(body.ownerDocument.defaultView.__x, undefined);
    // 原文应作为纯文本保留。
    assert.match(body.textContent, /\*\*粗\*\*/);
  });
});
