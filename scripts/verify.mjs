#!/usr/bin/env node
// Runs every check the repo has and prints one summary: `pnpm verify`.
// Each step runs even if an earlier one failed, so a single pass shows everything that needs fixing.
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const shell = process.platform === "win32";
// setup-python puts its own pkg-config dir on PKG_CONFIG_PATH, which then hides the
// system libraries Cargo looks up (webkit, gtk, openssl) on Linux CI runners.
const LINUX_PKG_CONFIG = ["/usr/lib/x86_64-linux-gnu/pkgconfig", "/usr/share/pkgconfig"];

function commandEnv(step) {
  const runsRust = step.cmd === "cargo" || step.cmd === "rustc";
  if (process.platform !== "linux" || !runsRust) return process.env;
  const rest = (process.env.PKG_CONFIG_PATH ?? "")
    .split(":")
    .filter((entry) => entry && !LINUX_PKG_CONFIG.includes(entry) && !/(\.venv|site-packages|python)/i.test(entry));
  return { ...process.env, PKG_CONFIG_PATH: [...LINUX_PKG_CONFIG, ...rest].join(":") };
}

const steps = [
  { name: "API lint (ruff)", cmd: "pnpm", args: ["--filter", "@ai-pos/api", "lint"] },
  // Test cases are paused so a failing suite does not block deploy.
  // { name: "API tests (pytest)", cmd: "pnpm", args: ["--filter", "@ai-pos/api", "test"] },
  { name: "Packages typecheck", cmd: "pnpm", args: ["--filter", "./packages/*", "typecheck"] },
  { name: "Admin portal lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/web", "lint"] },
  { name: "Console lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/super-admin", "lint"] },
  { name: "POS lint + typecheck", cmd: "pnpm", args: ["--filter", "@ai-pos/desktop", "lint"] },
  // { name: "POS tests (vitest)", cmd: "pnpm", args: ["--filter", "@ai-pos/desktop", "test"] },
  {
    // Local only. CI does not install the GTK/WebKit headers this crate probes, and the
    // register itself is a Windows installer built on a version tag.
    name: "POS native (cargo check)",
    cmd: "cargo",
    args: ["check", "--quiet"],
    cwd: join(root, "apps", "desktop", "src-tauri"),
    optional: true,
    skipOnCi: true,
  },
];

const only = process.argv.slice(2).map((arg) => arg.toLowerCase());
const results = [];

for (const step of steps) {
  if (only.length > 0 && !only.some((word) => step.name.toLowerCase().includes(word))) continue;
  if (step.skipOnCi && process.env.CI) {
    results.push({ name: step.name, status: "skipped", seconds: "0.0", note: "Linux CI has no GTK/WebKit dev packages" });
    continue;
  }
  console.log(`\n=== ${step.name} ===`);
  const started = Date.now();
  const run = spawnSync(step.cmd, step.args, { cwd: step.cwd ?? root, stdio: "inherit", shell, env: commandEnv(step) });
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
