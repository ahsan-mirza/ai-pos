#!/usr/bin/env node
// Fails when a localize()/t() string has no Arabic, an empty Arabic value, or a broken placeholder.
// Unwrapped JSX is reported and does not fail the build; those screens are still being migrated.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const localePath = join(root, "packages", "ui", "src", "locale.ts");
const source = readFileSync(localePath, "utf8");

function unquote(value) {
  return value.replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/\\\\/g, "\\");
}

function catalog() {
  const start = source.indexOf("const arabic");
  const end = source.indexOf("const listeners");
  const body = source.slice(start, end);
  const entries = [];
  const seen = new Map();
  const pattern = /(?:^|\n)\s*(?:"((?:\\.|[^"\\])*)"|([A-Za-z][\w ]*))\s*:\s*"((?:\\.|[^"\\])*)"/g;
  let match;
  while ((match = pattern.exec(body))) {
    const key = unquote(match[1] ?? match[2]);
    const value = unquote(match[3]);
    if (seen.has(key)) seen.get(key).push(entries.length);
    else seen.set(key, [entries.length]);
    entries.push({ key, value });
  }
  return { entries, seen };
}

function keepEnglish() {
  const match = source.match(/export const localeKeepEnglish = \[([\s\S]*?)\] as const/);
  if (!match) return new Set();
  return new Set([...match[1].matchAll(/"((?:\\.|[^"\\])*)"/g)].map((item) => unquote(item[1])));
}

function placeholders(text) {
  return [...text.matchAll(/\{[A-Za-z0-9_]+\}/g)].map((item) => item[0]).sort();
}

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name.startsWith(".")) continue;
    const path = join(dir, name);
    const info = statSync(path);
    if (info.isDirectory()) walk(path, out);
    else if (/\.(tsx|ts)$/.test(name) && !/\.test\./.test(name)) out.push(path);
  }
}

function calls(file) {
  const text = readFileSync(file, "utf8");
  const found = [];
  const pattern = /\b(?:localize|t)\(\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)')/g;
  let match;
  while ((match = pattern.exec(text))) {
    const line = text.slice(0, match.index).split("\n").length;
    found.push({ key: unquote(match[1] ?? match[2]), file, line });
  }
  return found;
}

function jsxText(file) {
  const text = readFileSync(file, "utf8");
  const found = [];
  const pattern = />([^<>{}\n][^<>{}]{2,})</g;
  let match;
  while ((match = pattern.exec(text))) {
    const value = match[1].trim();
    if (!/[A-Za-z]/.test(value)) continue;
    if (/^(className|true|false|null|undefined)$/.test(value)) continue;
    found.push(value);
  }
  return found;
}

const { entries, seen } = catalog();
const arabic = new Map(entries.map((entry) => [entry.key, entry.value]));
const allowed = keepEnglish();
const problems = [];

for (const [key, indexes] of seen) {
  if (indexes.length > 1) problems.push(`duplicate catalog key "${key}"`);
}

for (const entry of entries) {
  if (entry.value.trim() === "") problems.push(`empty Arabic for "${entry.key}"`);
  else if (entry.value === entry.key && !allowed.has(entry.key)) problems.push(`Arabic still matches English for "${entry.key}"`);
  const left = placeholders(entry.key);
  const right = placeholders(entry.value);
  if (left.join(" ") !== right.join(" ")) problems.push(`placeholder mismatch for "${entry.key}"`);
}

const roots = ["apps/web/src", "apps/desktop/src", "plugins/reach/frontend", "packages/ui/src"].map((dir) => join(root, dir));
const files = [];
for (const dir of roots) walk(dir, files);

const used = [];
for (const file of files) used.push(...calls(file));
const usedKeys = new Set(used.map((item) => item.key));

for (const item of used) {
  if (!arabic.has(item.key)) {
    problems.push(`missing Arabic for "${item.key}" (${relative(root, item.file)}:${item.line})`);
  }
}

const byModule = new Map();
for (const file of files) {
  if (!file.endsWith(".tsx")) continue;
  const rel = relative(root, file).replaceAll("\\", "/");
  const moduleName = rel.split("/").slice(0, 3).join("/");
  const texts = jsxText(file);
  if (texts.length === 0) continue;
  const bucket = byModule.get(moduleName) ?? { files: 0, jsx: 0 };
  bucket.files += 1;
  bucket.jsx += texts.length;
  byModule.set(moduleName, bucket);
}

console.log(`Catalog keys: ${entries.length}`);
console.log(`localize()/t() literals: ${used.length} (${usedKeys.size} unique)`);
console.log("JSX text still outside localize() (report only):");
for (const [name, bucket] of [...byModule.entries()].sort((a, b) => b[1].jsx - a[1].jsx)) {
  console.log(`  ${String(bucket.jsx).padStart(5)}  ${name}`);
}

if (problems.length > 0) {
  console.error(`\n${problems.length} localization problem(s):`);
  for (const problem of problems.slice(0, 80)) console.error(`- ${problem}`);
  if (problems.length > 80) console.error(`- … ${problems.length - 80} more`);
  process.exit(1);
}

console.log("\nArabic catalog matches every localize()/t() literal.");
