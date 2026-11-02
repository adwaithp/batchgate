import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // The API runs on :8000; proxying keeps the browser on one origin (no CORS in dev).
    proxy: { '/api': 'http://localhost:8000' },
  },
})
