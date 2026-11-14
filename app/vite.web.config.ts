/**
 * `npm run dev:web`: the renderer alone in a browser, over a fake Mac desktop.
 * Open http://localhost:5173/  (stage)  ·  add ?os=win to preview Windows labels.
 */
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@contracts': resolve(__dirname, '../shared/contracts'),
      '@': resolve(__dirname, 'src/renderer/src')
    }
  },
  server: { port: 5173, strictPort: true, fs: { allow: [resolve(__dirname, '..')] } }
})
