/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin in the split deploy (e.g. https://api.example.com). Empty/unset
   *  in local dev — the Vite proxy makes `/auth`, `/orders`, … same-origin. */
  readonly VITE_API_URL?: string;
  /** Absolute WebSocket URL (e.g. wss://api.example.com/ws). Empty/unset in local dev —
   *  the source derives it from `window.location`. */
  readonly VITE_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
