/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The API the console talks to (its /api/v1/super-admin routes). */
  readonly VITE_CONSOLE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
