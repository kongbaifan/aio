/**
 * 前端第三方资产的本地化检查。
 *
 * 原来这些库从 unpkg 加载，离线时 Markdown 静默降级成纯文本、图标全消失。
 * 本地化之后要守住两件事：index.html 不能再有外链，vendor/ 里的文件不能缺。
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(here, "../..");
const staticDir = resolve(appRoot, "app/static");
const indexHtml = readFileSync(resolve(staticDir, "index.html"), "utf-8");

/** 抓出 index.html 里所有 src/href 引用。 */
function references() {
  return [...indexHtml.matchAll(/(?:src|href)="([^"]+)"/g)].map(match => match[1]);
}

describe("前端资产本地化", () => {
  it("index.html 不再引用任何外部主机", () => {
    const external = references().filter(url => /^(https?:)?\/\//.test(url));

    assert.deepEqual(external, [], `仍有外链：${external.join(", ")}`);
  });

  it("引用的本地静态文件都存在", () => {
    const missing = references()
      .filter(url => url.startsWith("/static/"))
      .map(url => url.replace(/^\/static\//, ""))
      .filter(relative => !existsSync(resolve(staticDir, relative)));

    assert.deepEqual(missing, [], `缺文件：${missing.join(", ")}——先跑 npm run sync-vendor`);
  });

  it("vendor 清单里的版本与 package.json 锁定的一致", () => {
    const manifest = JSON.parse(readFileSync(resolve(staticDir, "vendor/MANIFEST.json"), "utf-8"));
    const declared = JSON.parse(readFileSync(resolve(appRoot, "package.json"), "utf-8")).dependencies;

    assert.ok(manifest.assets.length > 0, "清单不应为空");
    for (const asset of manifest.assets) {
      assert.equal(
        asset.version,
        declared[asset.package],
        `${asset.file} 来自 ${asset.package}@${asset.version}，但 package.json 声明的是 ${declared[asset.package]}——重跑 npm run sync-vendor`,
      );
      assert.ok(existsSync(resolve(staticDir, "vendor", asset.file)), `${asset.file} 不存在`);
    }
  });

  it("index.html 引用了清单里的每个文件", () => {
    const manifest = JSON.parse(readFileSync(resolve(staticDir, "vendor/MANIFEST.json"), "utf-8"));
    const referenced = new Set(references());

    // 前置断言：清单为空时下面的 for 会空转通过，等于没测。
    assert.ok(manifest.assets.length > 0, "清单不应为空");
    for (const asset of manifest.assets) {
      assert.ok(
        referenced.has(`/static/vendor/${asset.file}`),
        `${asset.file} 同步了却没被 index.html 引用`,
      );
    }
  });
});
