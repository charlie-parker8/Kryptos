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
    // ── Enabled in the backend-integration phase (see the plan). The prototypes
    // run on 100% mock data and never call the API. Same-origin proxying keeps the
    // httponly `kryptos_session` cookie and the WebSocket upgrade working without
    // any CORS middleware on the FastAPI side.
    //
    // proxy: {
    //   '/auth': 'http://localhost:8000',
    //   '/orders': 'http://localhost:8000',
    //   '/portfolio': 'http://localhost:8000',
    //   '/holdings': 'http://localhost:8000',
    //   '/health': 'http://localhost:8000',
    //   '/ws': { target: 'ws://localhost:8000', ws: true },
    // },
  },
})
