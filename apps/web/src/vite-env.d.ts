/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_DEFAULT_CURRENCY: string;
  /** Tenant for plain localhost (no subdomain), e.g. "demo". */
  readonly VITE_DEFAULT_TENANT?: string;
  /** Comma-separated store domain suffixes: "axizpos.com", "dev.axizpos.com", "localhost". */
  readonly VITE_TENANT_BASE_DOMAINS?: string;
  readonly VITE_SHOW_DEMO_ACCOUNTS?: string;
  readonly VITE_DEMO_ADMIN_USERNAME?: string;
  readonly VITE_DEMO_ADMIN_PASSWORD?: string;
  /** Marketing site origin, for example https://axizpos.com. Exit Demo returns to /explore on this origin. */
  readonly VITE_MARKETING_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
