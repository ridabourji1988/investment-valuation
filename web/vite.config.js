import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built assets are served by FastAPI from /assets; index.html from /.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
