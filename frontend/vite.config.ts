import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Same-origin proxy to the FastAPI backend on :8000. Keeps the httponly
    // `kryptos_session` cookie and the `/ws` upgrade working with no CORS
    // middleware on the FastAPI side. Set `?mock` / `?frozen` in the URL to run
    // the app on the deterministic mock feed with no backend at all.
    proxy: {
      '/auth': 'http://localhost:8000',
      '/orders': 'http://localhost:8000',
      '/portfolio': 'http://localhost:8000',
      '/holdings': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
