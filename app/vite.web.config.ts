/**
 * `npm run dev:web`: the renderer alone in a browser, over a fake Mac desktop.
 * Open http://localhost:5173/  (stage)  ·  add ?os=win to preview Windows labels.
 */
import { readFileSync } from 'node:fs'
import { createServer, type Server } from 'node:http'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { HOST_PAGE, HOST_SCRIPT, hostReply, isOrigin } from './src/main/playerHost'

/** The stage asks this where to frame the player's host page from (features/player/store.ts, 'player:host'). */
const HOST_ORIGIN_PATH = '/__miyagi/player-host'
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]'])

/**
 * R33: the stage serves the player's host page itself, so the stage runs the same framed player and the same
 * postMessage channel. Like Electron's main (main/playerHost.ts), it serves it from its own loopback origin: a second
 * server on 127.0.0.1 and a free port, one per stage origin that asks. Framed from the stage's own origin, Chrome warns
 * on every load that a frame with allow-scripts and allow-same-origin can escape its sandbox (QA Q13). The same page
 * on the stage's origin stays as the fallback when that server can't start.
 */
function playerHost(): Plugin {
  const script = resolve(__dirname, 'src/main/playerHost.page.js')
  const hosts = new Map<string, Promise<string>>()
  const servers: Server[] = []
  /** The host page's URL for the stage page at `parent` (its own server, started on first ask). */
  const hostFor = (parent: string): Promise<string> => {
    let p = hosts.get(parent)
    if (!p) {
      p = new Promise<string>((ok, fail) => {
        const side = createServer((req, res) => {
          const r = hostReply(req.method, req.url, parent, readFileSync(script, 'utf8'))
          res.writeHead(r.status, r.headers)
          res.end(req.method === 'HEAD' ? undefined : r.body)
        })
        side.once('error', fail)
        side.listen(0, '127.0.0.1', () => {
          const a = side.address()
          if (!a || typeof a !== 'object') return fail(new Error('no port'))
          side.unref()
          servers.push(side)
          ok(`http://127.0.0.1:${a.port}${HOST_PAGE}`)
        })
      })
      p.catch(() => hosts.delete(parent))
      hosts.set(parent, p)
    }
    return p
  }
  return {
    name: 'miyagi-player-host',
    configureServer(server) {
      server.httpServer?.once('close', () => servers.forEach((s) => s.close()))
      server.middlewares.use((req, res, next) => {
        if ((req.url ?? '').split('?')[0] !== HOST_ORIGIN_PATH) return next()
        const parent = req.headers.host ? `http://${req.headers.host}` : ''
        const reply = (url: string): void => {
          res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
          res.end(JSON.stringify({ url }))
        }
        // A stage opened from another machine (--host) can't reach this one's 127.0.0.1: it keeps the same-origin page.
        // One host server per name this very server answers on, never one for any Host header that comes in.
        const own = server.httpServer?.address()
        const at = isOrigin(parent) ? new URL(parent) : undefined
        if (!at || !LOOPBACK.has(at.hostname) || !own || typeof own !== 'object' || at.port !== String(own.port)) return reply(`${parent}${HOST_PAGE}`)
        hostFor(parent).then(reply, () => reply(`${parent}${HOST_PAGE}`))
      })
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
