// Copies the Tauri NSIS installer to dist/POS-Setup-<version>.exe.
// The version comes from apps/desktop/src-tauri/tauri.conf.json.
import { copyFileSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const tauriConf = JSON.parse(
  readFileSync(join(root, "apps/desktop/src-tauri/tauri.conf.json"), "utf8"),
);
const version = tauriConf.version;
if (typeof version !== "string" || version.trim() === "") {
  console.error("tauri.conf.json is missing a version.");
  process.exit(1);
}

const nsisDir = join(root, "apps/desktop/src-tauri/target/release/bundle/nsis");
let exe;
try {
  exe = readdirSync(nsisDir).find((name) => name.toLowerCase().endsWith(".exe"));
} catch {
  exe = undefined;
}
if (!exe) {
  console.error(`No NSIS installer in ${nsisDir}. Run pnpm build:win first.`);
  process.exit(1);
}

const destDir = join(root, "dist");
mkdirSync(destDir, { recursive: true });
const dest = join(destDir, `POS-Setup-${version}.exe`);
copyFileSync(join(nsisDir, exe), dest);
console.log(dest);
