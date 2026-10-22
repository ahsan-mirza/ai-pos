#!/usr/bin/env node
// Runs every check the repo has and prints one summary: `pnpm verify`.
// Each step runs even if an earlier one failed, so a single pass shows everything that needs fixing.
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const shell = process.platform === "win32";

const steps = [
  { name: "API lint (ruff)", cmd: "pnpm", args: ["--filter", "@ai-pos/api", "lint"] },
  { name: "API tests (pytest)", cmd: "pnpm", args: ["--filter", "@ai-pos/api", "test"] },
  { name: "Packages typecheck", cmd: "pnpm", args: ["--filter", "./packages/*", "typecheck"] },
  { name: "Admin portal lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/web", "lint"] },
  { name: "Console lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/super-admin", "lint"] },
  { name: "POS lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/desktop", "lint"] },
  { name: "POS tests (vitest)", cmd: "pnpm", args: ["--filter", "@ai-pos/desktop", "test"] },
  {
    name: "POS native (cargo check)",
    cmd: "cargo",
    args: ["check", "--quiet"],
    cwd: join(root, "apps", "desktop", "src-tauri"),
    optional: true,
  },
];

const only = process.argv.slice(2).map((arg) => arg.toLowerCase());
const results = [];

for (const step of steps) {
  if (only.length > 0 && !only.some((word) => step.name.toLowerCase().includes(word))) continue;
  console.log(`\n=== ${step.name} ===`);
  const started = Date.now();
  const run = spawnSync(step.cmd, step.args, { cwd: step.cwd ?? root, stdio: "inherit", shell });
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  if (run.error && step.optional) {
    results.push({ name: step.name, status: "skipped", seconds, note: `${step.cmd} is not installed` });
  } else {
    results.push({ name: step.name, status: run.status === 0 ? "passed" : "FAILED", seconds });
  }
}

console.log("\n=== Summary ===");
for (const result of results) {
  console.log(`${result.status.padEnd(7)} ${result.name} (${result.seconds}s)${result.note ? ` - ${result.note}` : ""}`);
}
const failed = results.filter((result) => result.status === "FAILED");
process.exit(failed.length === 0 ? 0 : 1);
