import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = "d:/Work/ai-pos/apps/site";
const opt = join(root, "public/images/opt");
const files = readdirSync(opt);
const groups = new Map();
for (const file of files) {
  const kind = file.endsWith(".avif") ? "avif" : file.endsWith(".webp") ? "webp" : "other";
  const stem = file.replace(/-\d+\.(avif|webp)$/, "");
  const row = groups.get(stem) ?? { avif: [], webp: [] };
  row[kind]?.push(statSync(join(opt, file)).size);
  groups.set(stem, row);
}
const kb = (n) => Math.round(n / 1024);
for (const [stem, row] of groups) {
  row.avif.sort((a, b) => a - b);
  console.log(`${stem} avif ${kb(row.avif[0])}-${kb(row.avif.at(-1))} KiB (${row.avif.length})`);
}
const assets = readdirSync(join(root, "dist/site-assets"))
  .filter((file) => file.endsWith(".js"))
  .map((file) => ({ file, size: statSync(join(root, "dist/site-assets", file)).size }))
  .sort((a, b) => b.size - a.size);
console.log("---js---");
for (const asset of assets.slice(0, 15)) console.log(`${kb(asset.size)} KiB ${asset.file}`);
