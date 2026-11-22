import fs from "node:fs";
import path from "node:path";

const roots = [
  "d:/Work/ai-pos/apps/desktop/src",
  "d:/Work/ai-pos/packages/ui/src",
  "d:/Work/ai-pos/packages/design-tokens",
];
const exts = new Set([".ts", ".tsx", ".css", ".js"]);

function formatRem(px) {
  const abs = Math.abs(px);
  if (abs === 999 || abs === 9999) return `${px < 0 ? "-" : ""}999rem`;
  const rem = abs / 16;
  const text = rem
    .toFixed(4)
    .replace(/0+$/, "")
    .replace(/\.$/, "");
  return `${px < 0 ? "-" : ""}${text || "0"}rem`;
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === "dist") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (exts.has(path.extname(entry.name))) out.push(full);
  }
  return out;
}

let files = 0;
let replacements = 0;
for (const root of roots) {
  for (const file of walk(root)) {
    const before = fs.readFileSync(file, "utf8");
    let count = 0;
    const after = before.replace(/(-?\d*\.?\d+)px\b/g, (_match, num) => {
      count += 1;
      return formatRem(Number(num));
    });
    if (count > 0 && after !== before) {
      fs.writeFileSync(file, after);
      files += 1;
      replacements += count;
      console.log(`${path.relative("d:/Work/ai-pos", file)} ${count}`);
    }
  }
}
console.log(`files ${files}`);
console.log(`replacements ${replacements}`);
