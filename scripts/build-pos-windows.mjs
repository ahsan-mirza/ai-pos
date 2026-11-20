// Builds the production Windows installer.
// A valid AXIZPOS_SIGN_THUMBPRINT signs the binaries. Otherwise the installer is UNSIGNED.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const desktop = join(root, "apps/desktop");
const thumbprint = (process.env.AXIZPOS_SIGN_THUMBPRINT || "").replace(/\s+/g, "");
const forcedUnsigned = process.env.AXIZPOS_SIGN_MODE === "unsigned";

let signing = "UNSIGNED";
if (!forcedUnsigned && thumbprint !== "") {
  if (!/^[0-9a-fA-F]{40}$/.test(thumbprint)) {
    console.error(
      "Production signing stopped. AXIZPOS_SIGN_THUMBPRINT is set but is not 40 hexadecimal characters.",
    );
    process.exit(1);
  }
  signing = "SIGNED";
  console.log("Authenticode signing is configured. The private key stays in the certificate store.");
} else {
  console.warn(
    "WARNING: This Windows build is UNSIGNED. Authenticode does not identify the publisher. Windows SmartScreen may show an unknown-publisher warning.",
  );
}

const signFlag = signing === "UNSIGNED" ? " --no-sign" : "";
const env = { ...process.env, POS_ENV: "production" };
delete env.CARGO_TARGET_DIR;
if (!process.argv.includes("--stage-only")) {
  const built = spawnSync(
    `pnpm exec tauri build --bundles nsis --target x86_64-pc-windows-msvc${signFlag}`,
    { cwd: desktop, env, stdio: "inherit", shell: true },
  );
  if (built.status !== 0) process.exit(built.status || 1);
}

const releaseDir = join(desktop, "src-tauri/target/x86_64-pc-windows-msvc/release");
const nsisDir = join(releaseDir, "bundle/nsis");
const installerName = readdirSync(nsisDir).find((name) => name.toLowerCase().endsWith(".exe"));
const executableName = readdirSync(releaseDir).includes("ai-pos-desktop.exe")
  ? "ai-pos-desktop.exe"
  : readdirSync(releaseDir).find((name) => name.toLowerCase().endsWith(".exe"));
if (!installerName || !executableName) {
  console.error("The production build did not produce an executable and an NSIS installer.");
  process.exit(1);
}

const installer = join(nsisDir, installerName);
const executable = join(releaseDir, executableName);
const frontend = readFileSync(join(desktop, "dist/index.html"), "utf8");
const bundleScript = readdirSync(join(desktop, "dist/assets")).filter((name) => name.endsWith(".js"));
const bundled = bundleScript.map((name) => readFileSync(join(desktop, "dist/assets", name), "utf8")).join("\n");
const productionText = `${frontend}\n${bundled}`;
if (productionText.includes("127.0.0.1:18081") || productionText.includes("acceptance.invalid")) {
  console.error("The production bundle contains an acceptance endpoint.");
  process.exit(1);
}
for (const file of [installer, executable]) {
  const bytes = readFileSync(file);
  const text = bytes.toString("latin1");
  if (text.includes("BEGIN PRIVATE KEY") || text.includes("BEGIN RSA PRIVATE KEY")) {
    console.error("The production artifact contains a private key.");
    process.exit(1);
  }
}

function verify(file) {
  const script = signing === "SIGNED" ? "verify-pos-signature.ps1" : "verify-pos-unsigned.ps1";
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", join(root, "scripts", script), file],
    { stdio: "inherit" },
  );
  if (result.status !== 0) process.exit(result.status || 1);
}

verify(executable);
verify(installer);

const tauriConf = JSON.parse(readFileSync(join(desktop, "src-tauri/tauri.conf.json"), "utf8"));
const version = tauriConf.version;
const destDir = join(root, "dist");
mkdirSync(destDir, { recursive: true });
const stagedName = `POS-Setup-${version}.exe`;
const staged = join(destDir, stagedName);
copyFileSync(installer, staged);
copyFileSync(executable, join(destDir, executableName));

function hashFile(file, label) {
  const digest = createHash("sha256").update(readFileSync(file)).digest("hex");
  writeFileSync(`${file}.sha256`, `${digest}  ${label}\n`, "utf8");
  return digest;
}

const installerSha = hashFile(staged, stagedName);
hashFile(join(destDir, executableName), executableName);
const metadata = {
  product: tauriConf.productName,
  identifier: tauriConf.identifier,
  version,
  signing,
  authenticode: signing === "SIGNED",
  publisher_verified: signing === "SIGNED",
  warning:
    signing === "SIGNED"
      ? null
      : "This installer is UNSIGNED. Authenticode does not identify the publisher. Windows may show an unknown-publisher warning.",
  files: [
    { name: stagedName, sha256: installerSha },
    { name: executableName, sha256: createHash("sha256").update(readFileSync(join(destDir, executableName))).digest("hex") },
  ],
};
writeFileSync(join(destDir, `POS-Setup-${version}.signing.json`), `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
console.log(`${signing} ${stagedName} ${installerSha}`);
