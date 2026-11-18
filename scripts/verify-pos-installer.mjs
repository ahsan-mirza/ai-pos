// Confirms the NSIS installer was signed before anyone copies it into a release folder.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const nsisDir = join(root, "apps/desktop/src-tauri/target/release/bundle/nsis");
const exe = readdirSync(nsisDir).find((name) => name.toLowerCase().endsWith(".exe"));
if (!exe) {
  console.error(`No NSIS installer in ${nsisDir}.`);
  process.exit(1);
}
const installer = join(nsisDir, exe);
const bytes = readFileSync(installer);
const text = bytes.toString("latin1");
if (text.includes("BEGIN PRIVATE KEY") || text.includes("BEGIN RSA PRIVATE KEY")) {
  console.error("Production signing stopped. The installer contains a private key.");
  process.exit(1);
}

const verify = spawnSync(
  "powershell.exe",
  ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(root, "scripts/verify-pos-signature.ps1"), installer],
  { stdio: "inherit" },
);
if (verify.status !== 0) {
  process.exit(verify.status || 1);
}

const digest = createHash("sha256").update(bytes).digest("hex");
writeFileSync(`${installer}.sha256`, `${digest}  ${exe}\n`, "utf8");
console.log(`${exe} ${digest}`);
