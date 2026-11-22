/**
 * Island diagnostics, renderer side: what the overlay page itself sees of the island, sent to main's island.log over the
 * `island:diag` IPC (main/features/islandDiag.ts). Log-only. It hooks `window` events and a slow sampler, and reads the
 * DOM the island already renders (the `[data-hit]` box with a clip-path); Island.tsx is not touched.
 *
 * Reports: the island rect, the computed clip-path, devicePixelRatio, visibilityState, and how many times the pointer
 * entered the island and the peek opened / closed (with the time of the last one). Sent on visibility, focus, resize and
 * layout changes, on every hover / peek change (throttled to one per second) and every 30 s.
 */
import { bridge, isElectron } from '../bridge'

export type Counters = { hoverCount: number; hoverAt: number; peekOpens: number; peekCloses: number; peekAt: number }

/** Resting height of the island box: anything this much taller than the notch is open (the peek or a card). */
const OPEN_EXTRA_PX = 6
const SAMPLE_MS = 400
const HEARTBEAT_MS = 30_000
const MIN_GAP_MS = 1000

type Box = { x: number; y: number; w: number; h: number }

/** The island's shaped box: the first `[data-hit]` element that carries a clip-path. Null when the island is not drawn. */
export function findIslandBox(doc: Document = document): { el: Element; rect: Box; clipPath: string } | null {
  for (const el of Array.from(doc.querySelectorAll('[data-hit]'))) {
    const clip = getComputedStyle(el).clipPath
    if (!clip || clip === 'none') continue
    const r = el.getBoundingClientRect()
    if (r.width <= 0 || r.height <= 0) continue
    return { el, rect: { x: r.left, y: r.top, w: r.width, h: r.height }, clipPath: clip }
  }
  return null
}

const inside = (p: { x: number; y: number }, r: Box): boolean => p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h

export function installIslandDiagReport(): () => void {
  const route = location.hash.replace(/^#\/?/, '') || 'overlay'
  if (!isElectron || route !== 'overlay') return () => undefined
  const c: Counters = { hoverCount: 0, hoverAt: 0, peekOpens: 0, peekCloses: 0, peekAt: 0 }
  let pointer = { x: -1, y: -1 }
  let pointerIn = false
  let restH = 0
  let open = false
  let lastSent = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const seenNow = (): string => {
    const w = window as unknown as { __miyagiLayout?: { notch?: unknown; n?: number } }
    try {
      const isl = (window as unknown as { __miyagiIsland?: unknown }).__miyagiIsland
      // What is drawn where the pill and the notch sit (the top centre of the display): each element's tag, data-* names and rect.
      const probe = (x: number, y: number): string =>
        document
          .elementsFromPoint(x, y)
          .slice(0, 6)
          .map((e) => {
            const r = e.getBoundingClientRect()
            const d = Object.keys((e as HTMLElement).dataset ?? {}).join('.')
            return `${e.tagName.toLowerCase()}${d ? '[' + d + ']' : ''}@${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.width)}x${Math.round(r.height)}`
          })
          .join('>')
      const cx = innerWidth / 2
      return `route=${location.hash || '-'} layouts=${w.__miyagiLayout?.n ?? 0} notch=${JSON.stringify(w.__miyagiLayout?.notch ?? null)} island=${JSON.stringify(isl ?? null)} at16=${probe(cx, 16)} at57=${probe(cx, 57)}`
    } catch {
      return 'route=?'
    }
  }
  const send = (why: string): void => {
    const box = findIslandBox()
    const payload = {
      why,
      island: box?.rect ?? null,
      clipPath: box?.clipPath ?? '',
      dpr: window.devicePixelRatio,
      visibility: document.visibilityState,
      hover: { count: c.hoverCount, lastAt: c.hoverAt },
      peek: { opens: c.peekOpens, closes: c.peekCloses, lastAt: c.peekAt },
      seen: seenNow()
    }
    lastSent = Date.now()
    void bridge.invoke('island:diag', payload).catch(() => undefined)
  }
  const soon = (why: string): void => {
    if (timer) return
    timer = setTimeout(() => {
      timer = undefined
      send(why)
    }, Math.max(0, MIN_GAP_MS - (Date.now() - lastSent)))
  }

  const sample = (): void => {
    const box = findIslandBox()
    const now = Date.now()
    const nowIn = !!box && inside(pointer, box.rect)
    if (nowIn && !pointerIn) {
      c.hoverCount++
      c.hoverAt = now
      soon('hover')
    }
    pointerIn = nowIn
    if (box) {
      if (!restH || box.rect.h < restH) restH = box.rect.h
      const nowOpen = box.rect.h > restH + OPEN_EXTRA_PX
      if (nowOpen !== open) {
        open = nowOpen
        if (open) c.peekOpens++
        else c.peekCloses++
        c.peekAt = now
        soon(open ? 'peek-open' : 'peek-close')
      }
    }
  }

  const onMove = (e: PointerEvent): void => {
    pointer = { x: e.clientX, y: e.clientY }
    sample()
  }
  const onVis = (): void => send('visibility')
  const onFocus = (): void => send('focus')
  const onResize = (): void => soon('resize')
  window.addEventListener('pointermove', onMove, { passive: true })
  document.addEventListener('visibilitychange', onVis)
  window.addEventListener('focus', onFocus)
  window.addEventListener('resize', onResize)
  const sampler = setInterval(sample, SAMPLE_MS)
  const beat = setInterval(() => send('heartbeat'), HEARTBEAT_MS)
  const first = setTimeout(() => send('loaded'), 2500) // after the landing flash, so the island box exists
  return () => {
    window.removeEventListener('pointermove', onMove)
    document.removeEventListener('visibilitychange', onVis)
    window.removeEventListener('focus', onFocus)
    window.removeEventListener('resize', onResize)
    clearInterval(sampler)
    clearInterval(beat)
    clearTimeout(first)
    if (timer) clearTimeout(timer)
  }
}

// Installs itself on import (the overlay route only), so one `import './core/islandDiagReport'` is the whole wiring.
installIslandDiagReport()
