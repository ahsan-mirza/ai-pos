/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  /** Register browser preview. Set when the admin portal's VITE_API_BASE_URL is a different address. */
  readonly VITE_POS_API_BASE_URL?: string;
  readonly VITE_API_KEY?: string;
  readonly VITE_DEVICE_ID: string;
  readonly VITE_SYNC_INTERVAL_MS: string;
  readonly VITE_STORE_ID?: string;
  readonly VITE_TENANT_DOMAIN?: string;
  /** Store domain suffix shown on the activation screen: axizpos.com, dev.axizpos.com, or localhost. */
  readonly VITE_TENANT_BASE_DOMAIN?: string;
  readonly VITE_SHOW_DEMO_ACCOUNTS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
