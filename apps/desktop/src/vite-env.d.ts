/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_API_KEY?: string;
  readonly VITE_DEVICE_ID: string;
  readonly VITE_SYNC_INTERVAL_MS: string;
  readonly VITE_STORE_ID?: string;
  readonly VITE_TENANT_DOMAIN?: string;
  /** Store domain suffix shown on the activation screen: qios.ae, dev.qios.ae, or localhost. */
  readonly VITE_TENANT_BASE_DOMAIN?: string;
  readonly VITE_SHOW_DEMO_ACCOUNTS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
