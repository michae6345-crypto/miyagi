/**
 * Core: serve the built renderer over http://127.0.0.1:<random port> in a packaged (or `vite build`) app.
 *
 * Why: under file:// the page has an opaque origin and no Referer, so YouTube refuses the IFrame embed
 * ("Error 153: video player configuration error") and the IFrame API can't postMessage back. Dev works because
 * the page comes from http://localhost:5173. This gives the packaged app the same kind of origin (and an exact origin
 * for the player's host page to accept messages from: main/playerHost.ts).
 *
 * Bound to 127.0.0.1 only; serves files under out/renderer and nothing else (no directory listing, no `..`).
 */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, sep } from 'node:path'
import { playerHostOrigin } from './playerHost'

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.mp3': 'audio/mpeg',
  '.wasm': 'application/wasm'
}

let origin: Promise<string> | undefined

/**
 * W0-6 (BUILD-PLAN Section 6): the built app's Content-Security-Policy, sent with every page. Beyond the plan's list:
 * style-src allows inline <style> (motion / React inject a few), and media-src / connect-src allow the local engine's
 * http origin (speak audio at /tts, the overview's /stats). R33: no YouTube script runs in our pages any more; the only
 * frame is the player's host page on its own loopback origin (main/playerHost.ts), which frames YouTube itself.
 * Built per page: the host's port is only known once it serves (index.ts starts it before any window).
 */
export function csp(): string {
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' ws://localhost:8787 ws://127.0.0.1:8787 http://localhost:8787 http://127.0.0.1:8787",
    `frame-src ${playerHostOrigin() ?? "'none'"}`,
    "img-src 'self' data: blob: https://i.ytimg.com",
    "media-src 'self' blob: data: http://localhost:8787 http://127.0.0.1:8787",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'"
  ].join('; ')
}

/** Start (once) and return the origin, e.g. http://127.0.0.1:53817. */
export function serveRenderer(root: string): Promise<string> {
  origin ??= new Promise((resolve, reject) => {
    const base = normalize(root.endsWith(sep) ? root : root + sep)
    const server = createServer(async (req, res) => {
      try {
        const path = decodeURIComponent(new URL(req.url ?? '/', 'http://127.0.0.1').pathname)
        const file = normalize(join(base, path === '/' ? 'index.html' : path))
        if (!file.startsWith(base)) {
          res.writeHead(403, { 'X-Content-Type-Options': 'nosniff' }).end()
          return
        }
        const body = await readFile(file)
        const ext = extname(file).toLowerCase()
        res.writeHead(200, {
          'Content-Type': TYPES[ext] ?? 'application/octet-stream',
          'Cache-Control': 'no-cache',
          'X-Content-Type-Options': 'nosniff',
          'Referrer-Policy': 'strict-origin-when-cross-origin',
          ...(ext === '.html' ? { 'Content-Security-Policy': csp() } : {})
        })
        res.end(body)
      } catch {
        res.writeHead(404, { 'X-Content-Type-Options': 'nosniff' }).end()
      }
    })
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      if (addr && typeof addr === 'object') resolve(`http://127.0.0.1:${addr.port}`)
      else reject(new Error('[serve] no port'))
    })
  })
  return origin
}
