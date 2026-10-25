/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Store signup, for example http://localhost:5173/signup or https://axizpos.com/signup. */
  readonly VITE_SIGNUP_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
