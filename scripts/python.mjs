import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const apiRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "apps", "api");
const venvPython =
  process.platform === "win32"
    ? join(apiRoot, ".venv", "Scripts", "python.exe")
    : join(apiRoot, ".venv", "bin", "python");
const python = existsSync(venvPython) ? venvPython : process.platform === "win32" ? "python" : "python3";

// `--env=<name>` selects apps/api/.env.<name> (development, dev, production) via APP_ENV.
const args = process.argv.slice(2);
const env = { ...process.env };
if (args[0]?.startsWith("--env=")) {
  env.APP_ENV = args.shift().slice("--env=".length);
}

const result = spawnSync(python, args, {
  cwd: apiRoot,
  stdio: "inherit",
  env,
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
