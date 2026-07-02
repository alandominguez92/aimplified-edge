/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for a split deploy (empty = same-origin). */
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
