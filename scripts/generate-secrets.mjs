// Replaces change-me placeholders in a backend env file with random values; existing values are never touched,
// because rotating ENCRYPTION_SECRET or PIN_SALT on a live database makes stored identifiers and PINs unusable.
//
//   node scripts/generate-secrets.mjs                   .env  (local; also the register preview key)
//   node scripts/generate-secrets.mjs --env dev         .env.dev.local, created from .env.dev.example if missing
//   node scripts/generate-secrets.mjs --env production  .env.production (gitignored; database URL is left as-is)
//
// Database passwords stay change-me: fill them from the server's credentials.
// The committed .env.dev holds public build values only and is never rewritten. Production secrets live in .env.production.
import { randomBytes, randomInt } from "node:crypto";
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ENVIRONMENTS = ["development", "dev", "production"];
const flag = process.argv.indexOf("--env");
const appEnv = flag === -1 ? "development" : process.argv[flag + 1];
if (!ENVIRONMENTS.includes(appEnv)) {
  console.error(`--env must be one of ${ENVIRONMENTS.join(", ")}.`);
  process.exit(1);
}

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiEnv =
  appEnv === "development"
    ? join(root, ".env")
    : appEnv === "production"
      ? join(root, ".env.production")
      : join(root, `.env.${appEnv}.local`);
const example = appEnv === "development" ? join(root, ".env.example") : join(root, `.env.${appEnv}.example`);

const token = (bytes) => randomBytes(bytes).toString("base64url");
const pin = () => Array.from({ length: 6 }, () => randomInt(10)).join("");

function read(path) {
  return readFileSync(path, "utf8");
}

function valueOf(text, key) {
  const match = text.match(new RegExp(`^${key}=(.*)$`, "m"));
  return match ? match[1].trim() : null;
}

function replacePlaceholders(path, values) {
  let text = read(path);
  const changed = [];
  for (const [key, value] of Object.entries(values)) {
    const current = valueOf(text, key);
    if (current !== null && current.startsWith("change-me")) {
      text = text.replace(new RegExp(`^${key}=.*$`, "m"), `${key}=${value}`);
      changed.push(key);
    }
  }
  writeFileSync(path, text);
  return changed;
}

if (!existsSync(apiEnv)) {
  copyFileSync(example, apiEnv);
  console.log(`Created ${apiEnv} from its template.`);
}

const existingApiKey = valueOf(read(apiEnv), "API_KEY");
const apiKey = existingApiKey && !existingApiKey.startsWith("change-me") ? existingApiKey : token(24);
const adminPassword = token(12);

const apiChanged = replacePlaceholders(apiEnv, {
  JWT_SECRET: token(48),
  PIN_SALT: token(24),
  ENCRYPTION_SECRET: token(48),
  API_KEY: apiKey,
  ADMIN_PASSWORD: adminPassword,
});
if (valueOf(read(apiEnv), "ADMIN_PIN") === "135790") {
  writeFileSync(apiEnv, read(apiEnv).replace(/^ADMIN_PIN=.*$/m, `ADMIN_PIN=${pin()}`));
  apiChanged.push("ADMIN_PIN");
}
const label = appEnv === "development" ? ".env" : appEnv === "production" ? ".env.production" : `.env.${appEnv}.local`;
console.log(`${label}: generated ${apiChanged.join(", ") || "nothing"}`);

// The register browser preview uses the same file and the same API key. Installers never carry one.
if (appEnv === "development") {
  const previewChanged = replacePlaceholders(apiEnv, { VITE_API_KEY: apiKey });
  if (previewChanged.length > 0) console.log(`${label}: set ${previewChanged.join(", ")}`);
}
if (apiChanged.includes("ADMIN_PASSWORD")) {
  console.log(`Super Admin credentials for the first seed are in ${label} (ADMIN_PASSWORD, ADMIN_PIN).`);
}
