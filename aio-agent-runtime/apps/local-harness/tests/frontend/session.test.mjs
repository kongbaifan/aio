/**
 * 点开历史会话恢复现场。
 *
 * 会话本来就存在 SQLite 里，但前端 selectSession 只切了 id，
 * 对话区既不清空也不加载，点开旧会话看到的是上一个会话的残留。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { controlledSse, jsonResponse, launchWorkbench, messages, sseResponse } from "./harness.mjs";

const SESSION_LIST = {
  sessions: [
    {
      id: "s-old",
      title: "统计销售数据",
      created_at: "2026-07-25T10:00:00+00:00",
      updated_at: "2026-07-25T10:05:00+00:00",
      message_count: 2,
      provider: "fake",
      model: "fake-1",
      usage: { prompt_tokens: 12375, completion_tokens: 38, total_tokens: 12413, calls: 1 },
    },
  ],
};

const SESSION_DETAIL = {
  ...SESSION_LIST.sessions[0],
  messages: [
    { role: "user", content: "统计销售数据" },
    { role: "assistant", content: "已生成 **sales.csv**" },
  ],
};

function sessionRoutes(detail = SESSION_DETAIL) {
  return {
    "/api/sessions": () => jsonResponse(SESSION_LIST),
    "/api/sessions/s-old": () => jsonResponse(detail),
  };
}

async function clickFirstSession(app) {
  const button = app.document.querySelector(".session-item");
  assert.ok(button, "侧边栏应该有会话条目");
  button.dispatchEvent(new app.window.Event("click", { bubbles: true }));
  await app.flush();
  return button;
}

describe("历史会话", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("侧边栏列出已有会话", async () => {
    const app = await launchWorkbench({ routes: sessionRoutes() });
    opened.push(app);

    const item = app.document.querySelector(".session-item");
    assert.match(item.textContent, /统计销售数据/);
    assert.match(item.textContent, /2 条消息/);
  });

  it("点开后把历史消息渲染回来", async () => {
    const app = await launchWorkbench({ routes: sessionRoutes() });
    opened.push(app);

    await clickFirstSession(app);

    const bubbles = messages(app.document);
    assert.equal(bubbles.length, 2);
    assert.deepEqual(
      bubbles.map(item => item.role),
      ["user", "assistant"],
    );
    assert.equal(bubbles[0].text, "统计销售数据");
    assert.match(bubbles[1].text, /已生成/);
  });

  it("恢复时显示会话累计用量", async () => {
    const app = await launchWorkbench({ routes: sessionRoutes() });
    opened.push(app);

    await clickFirstSession(app);

    const note = app.document.querySelector(".usage-note");
    assert.ok(note, "应该显示累计用量");
    assert.match(note.textContent, /会话累计 12,413 tokens/);
    // 恢复历史时没有"本次"这一说
    assert.doesNotMatch(note.textContent, /本次/);
  });

  it("切换会话前清掉上一个会话的内容", async () => {
    const app = await launchWorkbench({
      routes: {
        ...sessionRoutes(),
        ...{
          "/api/chat/stream": () =>
            sseResponse([
              { kind: "start", session_id: "s-new", matched: [] },
              { kind: "delta", text: "这是新会话的回答" },
              {
                kind: "done",
                session_id: "s-new",
                files: [],
                usage: { prompt_tokens: 10, completion_tokens: 2, total_tokens: 12, calls: 1 },
              },
            ]),
        },
      },
    });
    opened.push(app);

    await app.submit("先问一句");
    assert.equal(messages(app.document).length, 2);

    await clickFirstSession(app);

    // 只剩历史会话的两条，新会话的问答和它的用量行都不该残留
    const bubbles = messages(app.document);
    assert.equal(bubbles.length, 2);
    assert.equal(bubbles[0].text, "统计销售数据");
    assert.equal(app.document.querySelectorAll(".usage-note").length, 1);
  });

  it("空历史会话显示空状态", async () => {
    const app = await launchWorkbench({
      routes: sessionRoutes({ ...SESSION_DETAIL, messages: [], usage: {} }),
    });
    opened.push(app);

    await clickFirstSession(app);

    assert.equal(messages(app.document).length, 0);
    assert.equal(app.document.getElementById("emptyState").hidden, false);
  });

  it("详情加载失败时提示且不留下半截内容", async () => {
    const app = await launchWorkbench({
      routes: {
        "/api/sessions": () => jsonResponse(SESSION_LIST),
        "/api/sessions/s-old": () => ({
          ok: false,
          status: 500,
          json: async () => ({ detail: "数据库损坏" }),
        }),
      },
    });
    opened.push(app);

    await clickFirstSession(app);

    assert.equal(messages(app.document).length, 0);
    assert.match(app.document.getElementById("toast").textContent, /历史消息加载失败/);
    // 光有一条几秒就消失的 toast 不够：对话区不能是一片纯空白。
    assert.equal(app.document.getElementById("emptyState").hidden, false);
  });

  it("运行中切换会话，旧会话的事件不会串进新会话", async () => {
    const stream = controlledSse([
      { kind: "start", session_id: "s-running", matched: [] },
      {
        kind: "event",
        event: { type: "tool", name: "execute_python", status: "running", detail: "模型请求执行工具", payload: {}, timestamp: "" },
      },
    ]);
    const app = await launchWorkbench({
      routes: {
        ...sessionRoutes(),
        "/api/chat/stream": () => stream.response,
      },
    });
    opened.push(app);

    // 发一个还在跑的任务，然后中途点开历史会话。
    await app.submit("跑个长任务", { wait: false });
    await clickFirstSession(app);

    // 被 abort 的那一轮会在微任务里收尾。以前它会把刚清空的 state.events
    // 重新塞满旧事件，并往新会话里插一个「任务已停止」分组。
    await app.flush();

    const bubbles = messages(app.document);
    // 现在 vendor 真实加载，assistant 的 Markdown 会被渲染，textContent 里
    // 的 ** 已消失（**sales.csv** -> sales.csv）。
    assert.deepEqual(
      bubbles.map(item => item.text),
      ["统计销售数据", "已生成 sales.csv"],
      "对话区只应该有被点开那个会话的历史消息",
    );
    assert.equal(
      app.document.querySelector(".activity-group"),
      null,
      "上一轮的活动分组（含「任务已停止」）不该出现在新会话里",
    );
  });
});
