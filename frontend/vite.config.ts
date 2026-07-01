import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Disable keep-alive so a stale idle socket (closed by Uvicorn after
        // its keepalive timeout) doesn't cause spurious `read ECONNRESET`
        // errors when Vite's proxy tries to reuse it.
        agent: false,
      },
    },
  },
})
