/**
 * 上下文面板的文件列表。
 *
 * done 帧带的是根目录列表，此前无条件拿它重渲染，会把正在浏览子目录的用户
 * 踢回根目录，state.path 和「返回上级」的基准也跟着错乱。
 */

import assert from "node:assert/strict";
import { after, describe, it } from "node:test";

import { jsonResponse, launchWorkbench, sseResponse } from "./harness.mjs";

const ROOT_FILES = { items: [{ name: "a.txt", type: "file", size: 1 }], cwd: "." };
const SUB_FILES = { items: [{ name: "inner.csv", type: "file", size: 2 }], cwd: "data" };

function routes(streamFrames) {
  return {
    "/api/files": (path) => {
      const url = String(path);
      return jsonResponse(url.includes("data") ? SUB_FILES : ROOT_FILES);
    },
    "/api/chat/stream": () => sseResponse(streamFrames),
  };
}

const DONE = {
  kind: "done",
  session_id: "s1",
  files: ROOT_FILES.items,
  matched_skills: [],
};

describe("文件面板", () => {
  const opened = [];
  after(() => opened.forEach(app => app.close()));

  function fileNames(document) {
    return [...document.querySelectorAll(".file-row .file-name")].map(n => n.textContent);
  }

  it("任务结束后停留在用户正在浏览的子目录", async () => {
    const app = await launchWorkbench({
      routes: routes([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "answer", answer: "完成" },
        DONE,
      ]),
    });
    opened.push(app);

    // 进到子目录
    const row = [...app.document.querySelectorAll(".file-row")].find(
      n => n.querySelector(".file-name")?.textContent === "a.txt",
    );
    assert.ok(row, "前置条件：根目录列出了 a.txt");

    // 直接驱动到子目录状态：点文件行走的是打开文件，这里模拟目录切换。
    await app.window.eval('loadFiles("data")');
    await app.flush();
    assert.deepEqual(fileNames(app.document), ["inner.csv"], "前置条件：已进入 data/");

    await app.submit("跑个任务");

    assert.deepEqual(
      fileNames(app.document),
      ["inner.csv"],
      "done 帧不该把用户踢回根目录",
    );
    assert.equal(app.document.getElementById("currentPath").textContent, "data");
  });

  it("用户在根目录时正常用 done 帧刷新", async () => {
    const app = await launchWorkbench({
      routes: routes([
        { kind: "start", session_id: "s1", matched: [] },
        { kind: "answer", answer: "完成" },
        { ...DONE, files: [{ name: "new.txt", type: "file", size: 3 }] },
      ]),
    });
    opened.push(app);

    await app.submit("跑个任务");

    assert.deepEqual(fileNames(app.document), ["new.txt"]);
  });
});
