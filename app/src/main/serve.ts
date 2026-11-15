/**
 * Core: serve the built renderer over http://127.0.0.1:<random port> in a packaged (or `vite build`) app.
 *
 * Why: under file:// the page has an opaque origin and no Referer, so YouTube refuses the IFrame embed
 * ("Error 153: video player configuration error") and the IFrame API can't postMessage back. Dev works because
 * the page comes from http://localhost:5173. This gives the packaged app the same kind of origin.
 *
 * Bound to 127.0.0.1 only; serves files under out/renderer and nothing else (no directory listing, no `..`).
 */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, join, normalize, sep } from 'node:path'

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

/** Start (once) and return the origin, e.g. http://127.0.0.1:53817. */
export function serveRenderer(root: string): Promise<string> {
  origin ??= new Promise((resolve, reject) => {
    const base = normalize(root.endsWith(sep) ? root : root + sep)
    const server = createServer(async (req, res) => {
      try {
        const path = decodeURIComponent(new URL(req.url ?? '/', 'http://127.0.0.1').pathname)
        const file = normalize(join(base, path === '/' ? 'index.html' : path))
        if (!file.startsWith(base)) {
          res.writeHead(403).end()
          return
        }
        const body = await readFile(file)
        res.writeHead(200, { 'Content-Type': TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream', 'Cache-Control': 'no-cache' })
        res.end(body)
      } catch {
        res.writeHead(404).end()
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
