/**
 * Feature: library (plan A6). Main-process side of the Library app window (route `library`, main/appWindows.ts).
 * Brief: app/agents/library.md
 *
 *   bridge.invoke('library:caps')        → { list, get, start }: what this engine says it understands (engine.hello)
 *   bridge.invoke('library:list')        → LibraryItem[] (cleaned), [] on any failure
 *   bridge.invoke('library:get', id)     → { item, steps, overview? }, null when the engine answered without one,
 *                                          rejects when nothing answered (so the window asks again later)
 *   bridge.invoke('library:start', id)   → true when library.start went out (zero model calls engine side)
 *
 * Why main and not the window: the engine's replay log drops engine.hello once a lesson starts, so a Library window
 * opened mid-lesson can't tell what the engine supports. Main keeps the capabilities for the whole connection
 * (EngineLink.can). Data comes from the v2 commands when the engine lists them, otherwise from GET /library and
 * GET /library/{id} on the engine's http origin (loopback or https only, a short timeout, a size cap). Every answer
 * goes through features/library/sanitize.ts: ids must match ^[A-Za-z0-9_-]{1,64}$, unknown fields are dropped.
 * Nothing here ever sends `learn` (that would build a lesson with model calls).
 */
import type { Incoming } from '../../common/wire'
import { defineMainFeature } from '../context'
import { TOKEN_HEADER, secureEngineUrl } from '../engine'
import { ENGINE_TOKEN } from '../localEngine'
import { cleanDetail, cleanList, isLibraryId, type LibraryDetail } from '../../renderer/src/features/library/sanitize'
import type { LibraryItem } from '../../../../shared/contracts/events'

const ENGINE_URL = process.env.ENGINE_URL ?? 'ws://localhost:8787'
/** How long to wait for the engine's answer to library.list / library.get. */
const ASK_MS = 4000
const HTTP_MS = 3000
const MAX_BYTES = 1_000_000

/** ws://host:port → http://host:port (wss → https). Only this Mac or TLS: undefined otherwise (no token, no fetch). */
function httpOrigin(): string | undefined {
  if (!secureEngineUrl(ENGINE_URL)) return undefined
  try {
    const u = new URL(ENGINE_URL.replace(/^ws/i, 'http'))
    return u.origin
  } catch {
    return undefined
  }
}

/** The body as text, or undefined past MAX_BYTES (counted in bytes as they arrive; the rest is never read). */
async function readCapped(res: Response): Promise<string | undefined> {
  const declared = Number(res.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > MAX_BYTES) {
    await res.body?.cancel().catch(() => undefined)
    return undefined
  }
  if (!res.body) return ''
  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
    if (total > MAX_BYTES) {
      await reader.cancel().catch(() => undefined)
      return undefined
    }
    chunks.push(value)
  }
  const buf = new Uint8Array(total)
  let at = 0
  for (const c of chunks) {
    buf.set(c, at)
    at += c.byteLength
  }
  return new TextDecoder().decode(buf)
}

/**
 * GET a JSON path on the engine's http origin. `{ body }` when it answered with JSON, null when it answered without
 * usable JSON (404, wrong type, over the cap, unparsable), undefined when nothing answered (no origin, down, timeout).
 */
async function getJson(path: string): Promise<{ body: unknown } | null | undefined> {
  const origin = httpOrigin()
  if (!origin) return undefined
  let res: Response
  try {
    res = await fetch(`${origin}${path}`, {
      headers: { Accept: 'application/json', ...(ENGINE_TOKEN ? { [TOKEN_HEADER]: ENGINE_TOKEN } : {}) },
      redirect: 'error',
      signal: AbortSignal.timeout(HTTP_MS)
    })
  } catch {
    return undefined
  }
  if (!res.ok || !/json/i.test(res.headers.get('content-type') ?? '')) {
    await res.body?.cancel().catch(() => undefined)
    return null
  }
  let text: string | undefined
  try {
    text = await readCapped(res)
  } catch {
    return undefined // the stream broke or timed out mid-body
  }
  if (text === undefined) return null
  try {
    return { body: JSON.parse(text) as unknown }
  } catch {
    return null
  }
}

export default defineMainFeature({
  id: 'library',
  setup(ctx) {
    const { engine } = ctx
    // One listener; each pending ask registers a matcher that resolves on its answer.
    const waiters = new Set<(e: Incoming) => boolean>()
    engine.onEvent((e) => {
      for (const w of [...waiters]) if (w(e)) waiters.delete(w)
    })

    function ask<T>(send: () => void, match: (e: Incoming) => T | undefined): Promise<T | undefined> {
      return new Promise((resolve) => {
        const timer = setTimeout(() => {
          waiters.delete(w)
          resolve(undefined)
        }, ASK_MS)
        const w = (e: Incoming): boolean => {
          const v = match(e)
          if (v === undefined) return false
          clearTimeout(timer)
          resolve(v)
          return true
        }
        waiters.add(w)
        send()
      })
    }

    ctx.handle('library:caps', () => ({ list: engine.can('library.list'), get: engine.can('library.get'), start: engine.can('library.start') }))

    ctx.handle('library:list', async (): Promise<LibraryItem[]> => {
      if (engine.connected && engine.can('library.list')) {
        const items = await ask(
          () => engine.send({ type: 'library.list', payload: {} }),
          (e) => (e.type === 'library' ? cleanList(e.payload) : undefined)
        )
        if (items) return items
      }
      return cleanList((await getJson('/library'))?.body)
    })

    ctx.handle('library:get', async (id: unknown): Promise<LibraryDetail | null> => {
      if (!isLibraryId(id)) return null
      if (engine.connected && engine.can('library.get')) {
        const d = await ask(
          () => engine.send({ type: 'library.get', payload: { id } }),
          (e) => (e.type === 'library.item' ? cleanDetail(e.payload, id) : undefined)
        )
        if (d) return d
      }
      const got = await getJson(`/library/${encodeURIComponent(id)}`)
      // Nothing answered (engine not connected, the WS ask timed out, HTTP down): reject, so the window doesn't cache
      // "no steps" and asks again on its next refresh.
      if (got === undefined) throw new Error('library:get: no answer from the engine')
      return got ? (cleanDetail(got.body, id) ?? null) : null
    })

    ctx.handle('library:start', (id: unknown): boolean => {
      if (!isLibraryId(id) || !engine.connected || !engine.can('library.start')) return false
      engine.send({ type: 'library.start', payload: { id } })
      return true
    })
  }
})
