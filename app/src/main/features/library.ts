/**
 * Feature: library (plan A6). Main-process side of the Library app window (route `library`, main/appWindows.ts).
 * Brief: app/agents/library.md
 *
 *   bridge.invoke('library:caps')        → { list, get, start }: what this engine says it understands (engine.hello)
 *   bridge.invoke('library:list')        → LibraryItem[] (cleaned), [] on any failure
 *   bridge.invoke('library:get', id)     → { item, steps, overview? } or null
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

async function getJson(path: string): Promise<unknown> {
  const origin = httpOrigin()
  if (!origin) return undefined
  try {
    const res = await fetch(`${origin}${path}`, {
      headers: { Accept: 'application/json', ...(ENGINE_TOKEN ? { [TOKEN_HEADER]: ENGINE_TOKEN } : {}) },
      redirect: 'error',
      signal: AbortSignal.timeout(HTTP_MS)
    })
    if (!res.ok || !/json/i.test(res.headers.get('content-type') ?? '')) return undefined
    const text = await res.text()
    return text.length > MAX_BYTES ? undefined : (JSON.parse(text) as unknown)
  } catch {
    return undefined
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
      return cleanList(await getJson('/library'))
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
      return cleanDetail(await getJson(`/library/${encodeURIComponent(id)}`), id) ?? null
    })

    ctx.handle('library:start', (id: unknown): boolean => {
      if (!isLibraryId(id) || !engine.connected || !engine.can('library.start')) return false
      engine.send({ type: 'library.start', payload: { id } })
      return true
    })
  }
})
