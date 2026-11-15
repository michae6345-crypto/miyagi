import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const alias = { '@contracts': resolve(__dirname, '../shared/contracts') }

export default defineConfig({
  main: { resolve: { alias } },
  preload: { resolve: { alias } },
  renderer: {
    resolve: { alias: { ...alias, '@': resolve(__dirname, 'src/renderer/src') } },
    plugins: [react(), tailwindcss()],
    // hmr.overlay off: the overlay window is full-screen, so Vite's red error page would cover (and block) the whole desktop.
    server: { fs: { allow: [resolve(__dirname, '..')] }, hmr: { overlay: false } }
  }
})
