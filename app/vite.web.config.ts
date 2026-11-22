/**
 * `npm run dev:web`: the renderer alone in a browser, over a fake Mac desktop.
 * Open http://localhost:5173/  (stage)  ·  add ?os=win to preview Windows labels.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { HOST_PAGE, HOST_SCRIPT, hostReply } from './src/main/playerHost'

/**
 * R33: the stage serves the player's host page itself (Electron's main does it from its own loopback origin), so the
 * stage runs the same framed player and the same postMessage channel. Here it's on the stage's own origin.
 */
function playerHost(): Plugin {
  const script = resolve(__dirname, 'src/main/playerHost.page.js')
  return {
    name: 'miyagi-player-host',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? '').split('?')[0]
        if (path !== HOST_PAGE && path !== HOST_SCRIPT) return next()
        const parent = req.headers.host ? `http://${req.headers.host}` : undefined
        const r = hostReply(req.method, req.url, parent, readFileSync(script, 'utf8'))
        res.writeHead(r.status, r.headers)
        res.end(req.method === 'HEAD' ? undefined : r.body)
      })
    }
  }
}

export default defineConfig({
  root: resolve(__dirname, 'src/renderer'),
  plugins: [react(), tailwindcss(), playerHost()],
  resolve: {
    alias: {
      '@contracts': resolve(__dirname, '../shared/contracts'),
      '@': resolve(__dirname, 'src/renderer/src')
    }
  },
  // Parallel agents: npm run dev:web -- --port 51xx (see agents/README.md). Falls forward if taken.
  server: { port: Number(process.env.WEB_PORT ?? 5173), strictPort: false, fs: { allow: [resolve(__dirname, '..')] } }
})
