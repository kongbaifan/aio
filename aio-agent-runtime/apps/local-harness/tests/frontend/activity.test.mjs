/**
 * 活动区的工具调用配对。
 *
 * 同一次工具调用会产生两条事件：running 和终态（success / error / blocked）。
 * 此前 pushActivityEvent 只 append，于是两个工具会渲染成四行、其中两行永久
 * 停在「执行中」，分组标题还写「执行了 4 个步骤」。现在后端在事件里带
 * call_id，前端据此就地替换。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { launchWorkbench, sseResponse } from "./harness.mjs";

const opened = [];
after(() => opened.forEach(app => app.close()));

function toolEvent(callId, name, status, detail) {
  return {
    kind: "event",
    event: {
      type: "tool",
      name,
      status,
      detail: detail || "",
      payload: status === "running" ? { arguments: { path: "." } } : {},
      timestamp: "",
      call_id: callId,
    },
  };
}

async function runWith(frames) {
  const app = await launchWorkbench({
    routes: { "/api/chat/stream": () => sseResponse(frames) },
  });
  opened.push(app);
  await app.submit("跑两个工具");
  return app;
}

function rows(document) {
  return [...document.querySelectorAll(".activity-event")].map(node => ({
    name: node.querySelector(".event-copy strong")?.textContent,
    status: node.querySelector(".event-status")?.textContent,
  }));
}

describe("活动区工具配对", () => {
  it("终态事件替换 running 行，不新增一行", async () => {
    const app = await runWith([
      { kind: "start", session_id: "s1", matched: [] },
      toolEvent("c1", "list_files", "running"),
      toolEvent("c2", "read_file", "running"),
      toolEvent("c1", "list_files", "success", '{"items":[]}'),
      toolEvent("c2", "read_file", "success", '{"content":"x"}'),
      { kind: "answer", answer: "完成" },
      { kind: "done", session_id: "s1", files: [] },
    ]);

    const shown = rows(app.document);
    assert.equal(shown.length, 2, "两个工具应该只有两行");
    assert.deepEqual(
      shown.map(r => r.status),
      ["完成", "完成"],
      "不该有行停在「执行中」",
    );
    // 顺序按首次出现（running 到达的顺序）保持
    assert.deepEqual(shown.map(r => r.name), ["list_files", "read_file"]);
  });

  it("分组标题的步骤数是工具个数，不是事件条数", async () => {
    const app = await runWith([
      { kind: "start", session_id: "s1", matched: [] },
      toolEvent("c1", "list_files", "running"),
      toolEvent("c1", "list_files", "success", "{}"),
      toolEvent("c2", "write_file", "running"),
      toolEvent("c2", "write_file", "success", "{}"),
      { kind: "answer", answer: "完成" },
      { kind: "done", session_id: "s1", files: [] },
    ]);

    const title = app.document.querySelector(".activity-group summary strong").textContent;
    assert.match(title, /执行了 2 个步骤/);
  });

  it("被拒绝的工具显示「已拒绝」而不是留下两行", async () => {
    const app = await runWith([
      { kind: "start", session_id: "s1", matched: [] },
      toolEvent("c1", "write_file", "running"),
      toolEvent("c1", "write_file", "blocked", '{"error":"用户拒绝了该操作。"}'),
      { kind: "answer", answer: "已停止" },
      { kind: "done", session_id: "s1", files: [] },
    ]);

    const shown = rows(app.document);
    assert.equal(shown.length, 1);
    assert.equal(shown[0].status, "已拒绝");
  });

  it("运行记录面板同样按调用折叠", async () => {
    const app = await runWith([
      { kind: "start", session_id: "s1", matched: [] },
      toolEvent("c1", "list_files", "running"),
      toolEvent("c1", "list_files", "success", "{}"),
      { kind: "answer", answer: "完成" },
      { kind: "done", session_id: "s1", files: [] },
    ]);

    const entries = app.document.querySelectorAll(".trace-entry");
    assert.equal(entries.length, 1, "一次调用在运行记录里算一条");
    assert.equal(app.document.getElementById("traceCount").textContent, "1");
  });

  it("没有 call_id 的事件原样保留（plan / 整体错误）", async () => {
    const app = await runWith([
      { kind: "start", session_id: "s1", matched: [] },
      {
        kind: "event",
        event: { type: "plan", name: "planner", status: "success", detail: "一；二", payload: {}, timestamp: "" },
      },
      toolEvent("c1", "list_files", "running"),
      toolEvent("c1", "list_files", "success", "{}"),
      { kind: "answer", answer: "完成" },
      { kind: "done", session_id: "s1", files: [] },
    ]);

    // plan 一行 + 工具一行
    assert.equal(rows(app.document).length, 2);
    assert.equal(app.document.getElementById("traceCount").textContent, "2");
  });
});
