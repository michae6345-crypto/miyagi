/**
 * Core (R33): the page that hosts the YouTube player, on a loopback origin of its own.
 *
 * Why: YouTube's IFrame API is a third-party script. It used to run inside our player page, next to the preload
 * bridge (window.tut). Now it runs only in this small page, which the player panel frames:
 *
 *   player window (our page, with the bridge)
 *     └─ iframe  http://<other loopback name>:<port>/player-host.html   no preload (preloads run in main frames only),
 *          │     cross-origin, so it can't reach window.tut; sandboxed iframe (no popups, no top navigation)
 *          └─ iframe  https://www.youtube.com/embed/…                     YouTube's own player
 *
 * The panel drives it over postMessage, both sides checking origin and source (renderer features/player/frame.ts ↔
 * playerHost.page.js): video commands in, player state out, nothing else. main/features/player.ts locks the frames'
 * navigation (host page, then YouTube hosts only).
 *
 * The host name is the loopback name the app's own pages don't use: the built app is on 127.0.0.1 (main/serve.ts), so
 * the host is on localhost; dev (Vite on localhost) puts it on 127.0.0.1. Another site, not only another origin, so
 * Chromium also gives it its own renderer process. If [::1] can't take the same port, it stays on 127.0.0.1: another
 * origin still, on the same site.
 *
 * Node only (no electron import): vite.web.config.ts serves the same page for the browser stage.
 */
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'

export const HOST_PAGE = '/player-host.html'
export const HOST_SCRIPT = '/player-host.js'

/** A plain http(s) origin (scheme, host, optional port): nothing that could leave an HTML attribute or a CSP. */
const ORIGIN = /^https?:\/\/(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::\d{1,5})?$/i
export const isOrigin = (s: unknown): s is string => typeof s === 'string' && s.length <= 300 && ORIGIN.test(s)

/** The host page's own CSP: YouTube's scripts and frames only, framed by the app's origin only. */
export function hostCsp(parent: string): string {
  return [
    "default-src 'none'",
    "script-src 'self' https://www.youtube.com https://s.ytimg.com",
    'frame-src https://www.youtube.com https://www.youtube-nocookie.com',
    `frame-ancestors ${parent}`,
    "base-uri 'none'",
    "form-action 'none'",
    "object-src 'none'"
  ].join('; ')
}

/** The page: the app's origin in a meta tag (the script answers only it), and the script. No inline code. */
export function hostHtml(parent: string): string {
  return [
    '<!doctype html>',
    '<html lang="en">',
    '<head>',
    '<meta charset="utf-8">',
    `<meta name="miyagi-parent" content="${parent}">`,
    '<title>video</title>',
    `<script src="${HOST_SCRIPT}" defer></script>`,
    '</head>',
    '<body></body>',
    '</html>'
  ].join('\n')
}

export type HostReply = { status: number; headers: Record<string, string>; body: string }

/** The one handler, for main's server and the stage's Vite middleware. Only the page and its script; GET or HEAD. */
export function hostReply(method: string | undefined, url: string | undefined, parent: string | undefined, script: string): HostReply {
  const base = { 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' }
  if (method !== 'GET' && method !== 'HEAD') return { status: 405, headers: base, body: '' }
  let path = ''
  try {
    path = new URL(url ?? '/', 'http://127.0.0.1').pathname
  } catch {
    // malformed: 404 below
  }
  if (!isOrigin(parent)) return { status: 404, headers: base, body: '' }
  if (path === HOST_PAGE) {
    return {
      status: 200,
      headers: {
        ...base,
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Security-Policy': hostCsp(parent),
        // YouTube refuses embeds with no http(s) Referer (error 153): the embed request carries this page's origin.
        'Referrer-Policy': 'strict-origin-when-cross-origin'
      },
      body: hostHtml(parent)
    }
  }
  if (path === HOST_SCRIPT) return { status: 200, headers: { ...base, 'Content-Type': 'text/javascript; charset=utf-8' }, body: script }
  return { status: 404, headers: base, body: '' }
}

function send(req: IncomingMessage, res: ServerResponse, r: HostReply): void {
  res.writeHead(r.status, r.headers)
  res.end(req.method === 'HEAD' ? undefined : r.body)
}

function listen(server: Server, port: number, host: string): Promise<number> {
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(port, host, () => {
      server.off('error', reject)
      const addr = server.address()
      if (addr && typeof addr === 'object') resolve(addr.port)
      else reject(new Error('[playerHost] no port'))
    })
  })
}

let started: Promise<string> | undefined
let origin: string | undefined

/**
 * Start (once) the host page's server for this app origin (`parent`: the only page that may frame it). Resolves to
 * the host's origin, e.g. http://localhost:53911. `script`: playerHost.page.js's text.
 */
export function servePlayerHost(script: string, parent: string): Promise<string> {
  started ??= (async () => {
    if (!isOrigin(parent)) throw new Error('[playerHost] the app has no http origin to allow')
    const handler = (req: IncomingMessage, res: ServerResponse): void => send(req, res, hostReply(req.method, req.url, parent, script))
    const v4 = createServer(handler)
    const port = await listen(v4, 0, '127.0.0.1')
    let name = '127.0.0.1'
    if (new URL(parent).hostname !== 'localhost') {
      // localhost may resolve to [::1] first: take the same port there too, or stay on 127.0.0.1.
      const v6 = createServer(handler)
      try {
        await listen(v6, port, '::1')
        name = 'localhost'
      } catch {
        v6.close()
      }
    }
    origin = `http://${name}:${port}`
    return origin
  })()
  return started
}

/** The host's origin once servePlayerHost has resolved (CSP frame-src, the player's navigation lock). */
export const playerHostOrigin = (): string | undefined => origin

/** YouTube's hosts, for the frames inside the host page (its embed, and anything the embed frames). */
const YOUTUBE_HOSTS = ['youtube.com', 'youtube-nocookie.com']

/**
 * May a frame in the player window go to `url`? depth 1 (a frame in our page): only the host page, on the host's
 * origin. depth 2+ (inside it): https on a YouTube host, or about:blank. depth -1 (Electron gave no frame to place):
 * one of those two, never anything else. depth 0 is our own page: core's lock, not this one.
 */
export function frameAllowed(url: string, depth: number, host = playerHostOrigin()): boolean {
  if (depth === -1) return frameAllowed(url, 1, host) || frameAllowed(url, 2, host)
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return false
  }
  if (depth === 1) return !!host && u.origin === host && u.pathname === HOST_PAGE
  if (depth < 2) return false
  if (u.href === 'about:blank' || u.href === 'about:srcdoc') return true
  if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return false
  const name = u.hostname.toLowerCase()
  return YOUTUBE_HOSTS.some((h) => name === h || name.endsWith(`.${h}`))
}
