/**
 * Public client configuration. Secrets stay on the API.
 * Set EXPO_PUBLIC_* in apps/mobile/.env (never commit production secrets).
 */
function read(name: string, fallback: string): string {
  const value = process.env[name];
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  return trimmed === "" ? fallback : trimmed;
}

const currency = read("EXPO_PUBLIC_DEFAULT_CURRENCY", "AED").toUpperCase();

export const env = {
  /** Dev default is the local API. Production builds must set an https URL. */
  apiBaseUrl: read("EXPO_PUBLIC_API_BASE_URL", "http://127.0.0.1:8000").replace(/\/$/, ""),
  defaultCurrency: /^[A-Z]{3}$/.test(currency) ? currency : "AED",
  sentryDsn: read("EXPO_PUBLIC_SENTRY_DSN", ""),
  signupUrl: read("EXPO_PUBLIC_SIGNUP_URL", ""),
} as const;

export function assertProductionApi(): void {
  if (!__DEV__ && !env.apiBaseUrl.startsWith("https://")) {
    throw new Error("Production builds require an https EXPO_PUBLIC_API_BASE_URL.");
  }
}
