/**
 * 工作台对话链路的冒烟测试。
 *
 * 起因：上一个 commit 加打字机时把 stream.push 写成了 stream.append，
 * 而 readSse 又把 onFrame 包在「跳过非 JSON 心跳」的 catch 里，
 * 于是每次流式回答都是空气泡、控制台一条错误都没有，直到肉眼看见才发现。
 * 这里的断言就是冲着那条链路去的。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { controlledSse, launchWorkbench, messages, sseResponse } from "./harness.mjs";

const USAGE = { prompt_tokens: 12375, completion_tokens: 38, total_tokens: 12413, calls: 1 };

function streamRoute(frames, options) {
  return { "/api/chat/stream": () => sseResponse(frames, options) };
}

describe("流式回答", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("把 delta 累积进气泡而不是留空", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "delta", text: "Markdown 是" },
        { kind: "delta", text: "一种轻量级标记语言。" },
        { kind: "done", session_id: "s1", files: [], usage: USAGE, session_usage: USAGE },
      ]),
    });
    opened.push(app);

    await app.submit("什么是 Markdown");

    const bubbles = messages(app.document);
    assert.equal(bubbles.length, 2);
    assert.deepEqual(bubbles[0], { role: "user", error: false, text: "什么是 Markdown" });
    // 关键断言：气泡里必须有拼接后的全文
    assert.equal(bubbles[1].text, "Markdown 是一种轻量级标记语言。");
  });

  it("分片到达的 SSE 也能正确拼帧", async () => {
    const app = await launchWorkbench({
      routes: streamRoute(
        [
          { kind: "start", session_id: "s1", matched: [] },
          { kind: "delta", text: "分片" },
          { kind: "delta", text: "也要拼对" },
          { kind: "done", session_id: "s1", files: [] },
        ],
        { chunks: 7 }, // 故意切碎，制造半帧
      ),
    });
    opened.push(app);

    await app.submit("测试分片");

    assert.equal(messages(app.document)[1].text, "分片也要拼对");
  });

  it("没有 delta 时用 answer 帧整段渲染", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "answer", answer: "团队模式的汇总结果" },
        { kind: "done", session_id: "s1", files: [] },
      ]),
    });
    opened.push(app);

    await app.submit("跑一个团队任务");

    assert.equal(messages(app.document)[1].text, "团队模式的汇总结果");
  });

  it("delta 与 answer 同时出现时不重复渲染", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "delta", text: "只此一份" },
        { kind: "answer", answer: "只此一份" },
        { kind: "done", session_id: "s1", files: [] },
      ]),
    });
    opened.push(app);

    await app.submit("测试去重");

    const assistant = messages(app.document).filter(item => item.role === "assistant");
    assert.equal(assistant.length, 1);
    assert.equal(assistant[0].text, "只此一份");
  });
});

describe("token 用量", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("done 帧带 usage 时显示本次消耗", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "delta", text: "好" },
        { kind: "done", session_id: "s1", files: [], usage: USAGE, session_usage: USAGE },
      ]),
    });
    opened.push(app);

    await app.submit("问一句");

    const note = app.document.querySelector(".usage-note");
    assert.ok(note, "应该出现 usage-note");
    assert.match(note.textContent, /12,413 tokens/);
    assert.match(note.textContent, /输入 12,375/);
    assert.match(note.textContent, /1 次模型调用/);
    // 本次与累计相同时不重复显示累计
    assert.doesNotMatch(note.textContent, /会话累计/);
  });

  it("会话累计与本次不同时一并显示", async () => {
    const session = { prompt_tokens: 30000, completion_tokens: 500, total_tokens: 30500, calls: 3 };
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "delta", text: "好" },
        { kind: "done", session_id: "s1", files: [], usage: USAGE, session_usage: session },
      ]),
    });
    opened.push(app);

    await app.submit("再问一句");

    assert.match(app.document.querySelector(".usage-note").textContent, /会话累计 30,500/);
  });

  it("没有 usage 时不显示这一行", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "delta", text: "好" },
        { kind: "done", session_id: "s1", files: [] },
      ]),
    });
    opened.push(app);

    await app.submit("问一句");

    assert.equal(app.document.querySelector(".usage-note"), null);
  });
});

describe("工具确认", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  /**
   * 真实时序：服务端发出 confirm 帧后阻塞在人工确认上，
   * 收到决定才继续发后续帧。用 controlledSse 而不是一次性发完（含 done）的
   * fixture——后者在现实里不会发生，也测不出「流已结束但弹窗还在」。
   */
  function confirmScenario({ confirmationId, tool, args, after: afterFrames = [] }) {
    const posted = [];
    const stream = controlledSse([
      { kind: "start", session_id: "s1", matched: [] },
      { kind: "confirm", confirmation_id: confirmationId, tool, arguments: args },
    ]);
    const routes = {
      "/api/chat/stream": () => stream.response,
      "/api/chat/confirm": (_path, options) => {
        posted.push(JSON.parse(options.body));
        stream.push(...afterFrames, { kind: "done", session_id: "s1", files: [] });
        stream.close();
        return { ok: true, status: 200, json: async () => ({ resolved: true }) };
      },
    };
    return { posted, stream, routes };
  }

  it("confirm 帧弹出对话框并把决定回传服务端", async () => {
    const { posted, routes } = confirmScenario({
      confirmationId: "abc123",
      tool: "write_file",
      args: { path: "a.txt", content: "x" },
      after: [{ kind: "delta", text: "已写入" }],
    });
    const app = await launchWorkbench({ routes });
    opened.push(app);

    // 流会停在 confirm 上，不能等它跑完。
    await app.submit("写个文件", { wait: false });

    const dialog = app.document.querySelector(".confirm-dialog");
    assert.ok(dialog, "应该弹出确认框");
    assert.equal(dialog.querySelector(".confirm-tool").textContent, "write_file");
    assert.match(dialog.querySelector(".confirm-args").textContent, /a\.txt/);

    dialog.querySelector('[data-confirm="approve"]').dispatchEvent(
      new app.window.Event("click", { bubbles: true }),
    );
    await app.settle();

    assert.deepEqual(posted, [{ confirmation_id: "abc123", approved: true }]);
    // 决定后对话框销毁，不残留在 DOM 里
    assert.equal(app.document.querySelector(".confirm-dialog"), null);
  });

  it("点拒绝时回传 approved=false", async () => {
    const { posted, routes } = confirmScenario({
      confirmationId: "def456",
      tool: "execute_python",
      args: { code: "print(1)" },
    });
    const app = await launchWorkbench({ routes });
    opened.push(app);

    await app.submit("跑段代码", { wait: false });
    app.document
      .querySelector('[data-confirm="reject"]')
      .dispatchEvent(new app.window.Event("click", { bubbles: true }));
    await app.settle();

    assert.deepEqual(posted, [{ confirmation_id: "def456", approved: false }]);
  });

  it("点停止后确认框不会留在页面上卡住界面", async () => {
    const posted = [];
    const stream = controlledSse([
      { kind: "start", session_id: "s1", matched: [] },
      { kind: "confirm", confirmation_id: "ghi789", tool: "write_file", arguments: { path: "a.txt" } },
    ]);
    const app = await launchWorkbench({
      routes: {
        "/api/chat/stream": () => stream.response,
        "/api/chat/confirm": (_path, options) => {
          posted.push(JSON.parse(options.body));
          return { ok: true, status: 200, json: async () => ({ resolved: true }) };
        },
      },
    });
    opened.push(app);

    await app.submit("写个文件", { wait: false });
    assert.ok(app.document.querySelector(".confirm-dialog"), "前置条件：确认框已弹出");

    // 用户点「停止任务」。<dialog> 是 modal，留在页面上会让 backdrop 吃掉所有
    // 交互，除了刷新页面没有别的出路。
    await app.stop();

    assert.equal(app.document.querySelector(".confirm-dialog"), null, "确认框必须被关闭");
    assert.deepEqual(posted, [], "已放弃的确认不该再回传服务端（那边会自行超时）");
  });
});

describe("事件轨迹", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("工具事件渲染到活动区", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        {
          kind: "event",
          event: { type: "tool", name: "read_skill", status: "running", detail: "模型请求执行工具", payload: {}, timestamp: "" },
        },
        {
          kind: "event",
          event: { type: "tool", name: "read_skill", status: "success", detail: '{"path":"business/lark-doc/SKILL.md"}', payload: {}, timestamp: "" },
        },
        { kind: "delta", text: "读完了" },
        { kind: "done", session_id: "s1", files: [] },
      ]),
    });
    opened.push(app);

    await app.submit("看看文档 skill");

    const activity = app.document.querySelector(".activity-group");
    assert.ok(activity, "应该有活动分组");
    assert.match(activity.textContent, /read_skill/);
    assert.equal(messages(app.document)[1].text, "读完了");
  });

  it("error 帧渲染成错误气泡", async () => {
    const app = await launchWorkbench({
      routes: streamRoute([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "error", detail: "模型调用失败：上游 500" },
      ]),
    });
    opened.push(app);

    await app.submit("触发错误");

    const last = messages(app.document).at(-1);
    assert.equal(last.role, "assistant");
    assert.equal(last.error, true);
    assert.match(last.text, /上游 500/);
  });
});
