/**
 * 错误路径与中断路径。
 *
 * 这些分支以前一条都没被覆盖：假 fetch 忽略 options.signal，AbortError 分支跑不到；
 * settle() 超时后静默放行，"UI 卡在执行中"这类缺陷测不出来。
 * 补上之后暴露的问题就是本文件断言的对象。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { controlledSse, launchWorkbench, messages, settle, sseResponse } from "./harness.mjs";

describe("测试基础设施：settle 的守卫", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("按钮卡在 running 时 settle 必须超时抛错，而不是静默放行", async () => {
    // settle 的抛错是防御性的：将来若有 bug 让 setBusy(false) 漏调，
    // 按钮会一直带 .running，settle 得把它变成失败而不是让用例假绿。
    // 这里手动制造那个状态（正常代码路径不会到达），验证守卫真的在。
    const app = await launchWorkbench({});
    opened.push(app);
    app.window.document.getElementById("sendButton").classList.add("running");

    await assert.rejects(() => settle(app.window, 80), /没有结束/);
  });
});

describe("流中断", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("连接中途断开时气泡要定稿，不能一直闪光标", async () => {
    const app = await launchWorkbench({
      routes: {
        "/api/chat/stream": () =>
          sseResponse(
            [
              { kind: "start", session_id: "s1", matched: [] },
              { kind: "delta", text: "答到一半" },
            ],
            { endWith: "drop" }, // 服务端进程被 kill / 断网
          ),
      },
    });
    opened.push(app);

    // settle 内部会断言发送按钮已复位；卡在 loading 的话这里就抛了。
    await app.submit("问一句");

    const body = app.document.querySelector(".message.assistant .message-body");
    assert.ok(body, "已经流出来的半截文本要保留");
    assert.equal(
      body.classList.contains("streaming"),
      false,
      "streaming class 必须去掉，否则闪烁光标会一直留着，看起来像还在输出",
    );
  });

  it("点停止后按钮复位且留下一条停止记录", async () => {
    const stream = controlledSse([{ kind: "start", session_id: "s1", matched: [] }]);
    const app = await launchWorkbench({
      routes: { "/api/chat/stream": () => stream.response },
    });
    opened.push(app);

    await app.submit("跑个长任务", { wait: false });
    await app.stop();

    const groups = app.document.querySelectorAll(".activity-group");
    assert.ok(groups.length >= 1, "应该留下一个「任务已停止」的活动分组");
  });
});

describe("模型失败", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("失败信息渲染成错误气泡，不是正常回答", async () => {
    const app = await launchWorkbench({
      routes: {
        "/api/chat/stream": () =>
          sseResponse([
            { kind: "start", session_id: "s1", matched: [] },
            {
              kind: "event",
              event: { type: "error", name: "model", status: "error", detail: "模型调用失败：上游 500", payload: {}, timestamp: "" },
            },
            { kind: "answer", answer: "模型调用失败：上游 500", is_error: true },
            { kind: "done", session_id: "s1", files: [] },
          ]),
      },
    });
    opened.push(app);

    await app.submit("问一句");

    const bubbles = messages(app.document).filter(item => item.role === "assistant");
    assert.equal(bubbles.length, 1);
    assert.equal(bubbles[0].error, true, "必须带错误样式，否则失败看起来像正常回答");
    assert.match(bubbles[0].text, /上游 500/);
  });

  it("已经流式输出过再失败时，错误不能被丢掉", async () => {
    const app = await launchWorkbench({
      routes: {
        "/api/chat/stream": () =>
          sseResponse([
            { kind: "start", session_id: "s1", matched: [] },
            { kind: "delta", text: "我正在分析" },
            { kind: "answer", answer: "模型调用失败：连接中断", is_error: true },
            { kind: "done", session_id: "s1", files: [] },
          ]),
      },
    });
    opened.push(app);

    await app.submit("问一句");

    const bubbles = messages(app.document).filter(item => item.role === "assistant");
    // 半截答案保留 + 追加一条错误气泡；否则用户看到的是外观完全正常的截断回答。
    assert.equal(bubbles.length, 2);
    assert.equal(bubbles[0].text, "我正在分析");
    assert.equal(bubbles[1].error, true);
    assert.match(bubbles[1].text, /连接中断/);
  });
});

describe("被拒绝的工具", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  it("blocked 状态显示「已拒绝」而不是「执行中」", async () => {
    const app = await launchWorkbench({
      routes: {
        "/api/chat/stream": () =>
          sseResponse([
            { kind: "start", session_id: "s1", matched: [] },
            {
              kind: "event",
              event: {
                type: "tool",
                name: "write_file",
                status: "blocked",
                detail: '{"error": "用户拒绝了该操作。"}',
                payload: {},
                timestamp: "",
              },
            },
            { kind: "answer", answer: "已停止" },
            { kind: "done", session_id: "s1", files: [] },
          ]),
      },
    });
    opened.push(app);

    await app.submit("写个文件");

    const row = app.document.querySelector(".activity-event.blocked");
    assert.ok(row, "blocked 事件要有自己的样式类");
    assert.equal(
      row.querySelector(".event-status").textContent,
      "已拒绝",
      "拒绝后一直显示「执行中」会让人以为还在跑",
    );
  });
});
