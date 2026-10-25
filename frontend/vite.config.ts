import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Forward API calls to the FastAPI dev server (python -m brandlens.api, port 8000).
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})