/**
 * 把前端第三方资产从 node_modules 同步到 app/static/vendor/。
 *
 * 工作台原本从 unpkg 加载 marked / DOMPurify / highlight.js / lucide，
 * 离线或内网环境下 Markdown 会静默降级成纯文本、图标全部消失——
 * 对一个自称「本地运行时」的项目来说这不合适。
 *
 * vendor/ 下的产物会提交进仓库，这样只装 Python 依赖的人也能直接用，不需要 Node。
 * 升级版本时改 package.json，重跑 `npm run sync-vendor`，把 vendor/ 的变更一起提交。
 */

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const vendorDir = resolve(root, "app/static/vendor");

// [包名, 包内路径, 输出文件名]
const ASSETS = [
  ["marked", "marked.min.js", "marked.min.js"],
  ["dompurify", "dist/purify.min.js", "purify.min.js"],
  ["@highlightjs/cdn-assets", "highlight.min.js", "highlight.min.js"],
  ["@highlightjs/cdn-assets", "styles/github-dark.min.css", "github-dark.min.css"],
  ["lucide", "dist/umd/lucide.min.js", "lucide.min.js"],
];

function packageVersion(name) {
  const manifest = resolve(root, "node_modules", name, "package.json");
  return JSON.parse(readFileSync(manifest, "utf-8")).version;
}

mkdirSync(vendorDir, { recursive: true });

const manifest = [];
for (const [pkg, source, target] of ASSETS) {
  const from = resolve(root, "node_modules", pkg, source);
  const to = resolve(vendorDir, target);
  copyFileSync(from, to);
  const version = packageVersion(pkg);
  manifest.push({ file: target, package: pkg, version });
  console.log(`${target}  <-  ${pkg}@${version}/${source}`);
}

// 记录来源和版本，避免以后看着 vendor/ 里的压缩文件猜不出出处。
writeFileSync(
  resolve(vendorDir, "MANIFEST.json"),
  `${JSON.stringify({ note: "由 npm run sync-vendor 生成，请勿手工编辑", assets: manifest }, null, 2)}\n`,
  "utf-8",
);
console.log(`\n已同步 ${manifest.length} 个文件到 app/static/vendor/`);
