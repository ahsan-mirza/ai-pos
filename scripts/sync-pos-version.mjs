// Copies apps/desktop/VERSION into the files Cargo and Tauri parse themselves.
// Run before `tauri build` so the installer version is already loaded from those files.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const desktop = join(root, "apps", "desktop");
const versionFile = join(desktop, "VERSION");

const SEMVER = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

export function readPosVersion() {
  const line = readFileSync(versionFile, "utf8")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item !== "" && !item.startsWith("#"));
  if (!line || !SEMVER.test(line)) {
    console.error(`apps/desktop/VERSION must contain one version such as 0.2.0. Found: ${line ?? "(empty)"}`);
    process.exit(1);
  }
  return line;
}

function patch(path, pattern, version) {
  const original = readFileSync(path, "utf8");
  const next = original.replace(pattern, `$1${version}$2`);
  if (next === original) {
    if (!original.includes(version)) {
      console.error(`Could not find a version field to update in ${path}`);
      process.exit(1);
    }
    return false;
  }
  writeFileSync(path, next);
  return true;
}

const version = readPosVersion();
if (process.argv.includes("--print")) {
  console.log(version);
  process.exit(0);
}

const targets = [
  [join(desktop, "package.json"), /("version"\s*:\s*")[^"]+(")/],
  [join(desktop, "src-tauri", "tauri.conf.json"), /("version"\s*:\s*")[^"]+(")/],
  [join(desktop, "src-tauri", "Cargo.toml"), /(\[package\][\s\S]*?\nversion = ")[^"]+(")/],
  [
    join(desktop, "src-tauri", "Cargo.lock"),
    /(\[\[package\]\]\r?\nname = "ai-pos-desktop"\r?\nversion = ")[^"]+(")/,
  ],
];

const changed = targets.filter(([path, pattern]) => patch(path, pattern, version)).map(([path]) => path);
if (changed.length === 0) {
  console.log(`POS version ${version} already synced.`);
} else {
  console.log(`POS version ${version} written to:`);
  for (const path of changed) console.log(`  ${path}`);
}
