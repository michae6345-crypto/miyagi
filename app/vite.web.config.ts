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
  // Parallel agents: npm run dev:web -- --port 51xx (see agents/README.md). Falls forward if taken.
  server: { port: Number(process.env.WEB_PORT ?? 5173), strictPort: false, fs: { allow: [resolve(__dirname, '..')] } }
})
