/**
 * The full-screen, click-through overlay window: every registered overlay layer, with the
 * island at z = 50. Also owns overlay.bounds reporting and click-through.
 *
 * Owner: core. Features add layers via defineFeature({ overlayLayers }).
 *
 * The sign-in gate (core/gate.ts): until main says it is open, the overlay draws nothing (no layer, no island) and
 * ignores global shortcuts, even if main showed the window early. A renderer backstop for main's own gate.
 */
import { useEffect, useRef, type ReactNode } from 'react'
import type { Layout } from '../../../preload/api'
import { cmd } from '../../../common/wire'
import { bridge } from '../bridge'
import { gateIsOpen, useGateOpen } from './gate'
import { Island } from './Island'
import { perf } from './perf'
import { getOverlayLayers } from './registry'
import { triggerShortcut, type ActionShortcut } from './shortcuts'
import { Boundary } from './ui/Boundary'

const ISLAND_Z = 50

export function Overlay({ layout }: { layout: Layout }): ReactNode {
  const root = useRef<HTMLDivElement>(null)
  useReportBounds(root, layout)
  // Global shortcuts arrive from main as a 'shortcut' signal; route them through the shared path (none before the gate).
  useEffect(() => bridge.on('shortcut', (kind) => gateIsOpen() && triggerShortcut(kind as ActionShortcut)), [])
  const open = useGateOpen()
  if (!open) return null
  const overlayLayers = getOverlayLayers()
  return (
    <div ref={root} data-theme="dark" className="absolute inset-0 overflow-hidden" style={{ width: layout.width, height: layout.height }}>
      {overlayLayers
        .filter((l) => l.z < ISLAND_Z)
        .map(({ id, Component }) => (
          <Boundary key={id} name={`layer ${id}`}>
            <Component layout={layout} />
          </Boundary>
        ))}
      {/* Michael's 5 AM shoot: one bad Island render (a stale hot reload) wiped the overlay. Now it comes back in 1 s. */}
      <Boundary name="island" retryMs={1000}>
        <Island top={bridge.platform.pillTop} layout={layout} />
      </Boundary>
      {overlayLayers
        .filter((l) => l.z >= ISLAND_Z)
        .map(({ id, Component }) => (
          <Boundary key={id} name={`layer ${id}`}>
            <Component layout={layout} />
          </Boundary>
        ))}
    </div>
  )
}

/** A main-side feature handle (overlay-raise.ts). Missing in the browser stage and older mains: ignored. */
function tellMain(channel: string, payload: unknown): void {
  try {
    void bridge.invoke(channel, payload).catch(() => {})
  } catch {
    // no handler
  }
}

/** How long a scroll over non-scrolling overlay UI hands the mouse to the app below. */
const PASS_MS = 600

/** Some element from `el` up can still scroll in the wheel's direction (the drawer, a code block). */
function canScroll(el: Element | null, dx: number, dy: number): boolean {
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    const st = getComputedStyle(n)
    if (dy && /(auto|scroll)/.test(st.overflowY) && n.scrollHeight > n.clientHeight + 1) {
      if ((dy < 0 && n.scrollTop > 0) || (dy > 0 && n.scrollTop + n.clientHeight < n.scrollHeight - 1)) return true
    }
    if (dx && /(auto|scroll)/.test(st.overflowX) && n.scrollWidth > n.clientWidth + 1) {
      if ((dx < 0 && n.scrollLeft > 0) || (dx > 0 && n.scrollLeft + n.clientWidth < n.scrollWidth - 1)) return true
    }
  }
  return false
}

/**
 * Tell the engine where our own UI is (`overlay.bounds`, screen points) so its screen reader
 * ignores it. Sampled every 100ms; sent only when it changes. Elements opt in with
 * data-hit (interactive: also stops click-through) or data-ui (display only).
 */
/** A change key for a rect list: a joined string is several times cheaper than JSON.stringify of the objects. */
const keyOf = (rs: { x: number; y: number; w: number; h: number }[]): string => rs.map((r) => `${r.x},${r.y},${r.w},${r.h}`).join(';')

function useReportBounds(root: React.RefObject<HTMLDivElement | null>, layout: Layout): void {
  useEffect(() => {
    let last = ''
    let lastHits = ''
    const tick = (): void => {
      // A hidden window (the stage tab in the background) has nothing new to say.
      if (typeof document !== 'undefined' && document.hidden) return
      const el = root.current
      if (!el) {
        // Nothing drawn (the sign-in gate closed again): clear what main and the engine last heard, once.
        if (lastHits && lastHits !== '[]') {
          lastHits = '[]'
          tellMain('overlay:hits', [])
        }
        if (last && last !== '[]') {
          last = '[]'
          bridge.send(cmd('overlay.bounds', { rects: [] }))
        }
        return
      }
      const box = el.getBoundingClientRect()
      if (!box.width) return
      const k = layout.width / box.width // undo the browser stage's CSS scale (1 in Electron)
      const toScreen = (r: DOMRect): { x: number; y: number; w: number; h: number } => ({
        x: Math.round((r.left - box.left) * k + layout.origin.x),
        y: Math.round((r.top - box.top) * k + layout.origin.y),
        w: Math.round(r.width * k),
        h: Math.round(r.height * k)
      })
      const nodes = Array.from(el.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .map((n) => ({ n, r: n.getBoundingClientRect() }))
        .filter(({ r }) => r.width > 1 && r.height > 1)
      perf.count('bounds.sampled')
      const rects = nodes.map(({ r }) => toScreen(r))
      // Desktop test 9, A1: main's click-catching poll grabs the mouse only over controls (data-hit). Passive UI
      // (data-ui: the spotlight caption, the loupe callout) stays click- and scroll-through.
      const hits = nodes.filter(({ n }) => n.hasAttribute('data-hit')).map(({ r }) => toScreen(r))
      const hitKey = keyOf(hits)
      if (hitKey !== lastHits) {
        lastHits = hitKey
        perf.count('hits.sent')
        tellMain('overlay:hits', hits)
      }
      const key = keyOf(rects)
      if (key === last) return
      last = key
      perf.count('bounds.sent')
      bridge.send(cmd('overlay.bounds', { rects }))
    }
    // 100 ms, not 300: main's click-catching poll (main/features/overlay-raise.ts) reads these rects, and a card that had
    // just opened or moved wasn't in them yet, so a quick move-and-click on its Hint went through to VS Code (test 8).
    const id = setInterval(tick, 100)
    return () => clearInterval(id)
  }, [root, layout])
}

/**
 * Electron only: the window ignores the mouse (clicks fall through to the app below) except while
 * the cursor is over something marked data-hit. Mouse moves are still forwarded, so we can tell.
 */
export function useClickThrough(): void {
  useEffect(() => {
    let on = false
    const set = (hit: boolean): void => {
      if (hit === on) return
      on = hit
      bridge.emit('overlay:interactive', hit)
    }
    let x = -1
    let y = -1
    const move = (e: MouseEvent): void => {
      x = e.clientX
      y = e.clientY
      set(!!(e.target as Element | null)?.closest?.('[data-hit]'))
    }
    const out = (): void => set(false)
    // A control can vanish under a still cursor (card closes, island shrinks): no mousemove fires,
    // so without this the whole-screen overlay keeps eating every click. Re-check what's under the cursor.
    const watchdog = setInterval(() => {
      if (!on) return
      const el = x < 0 ? null : document.elementFromPoint(x, y)
      if (!el?.closest?.('[data-hit]')) set(false)
    }, 250)
    // Desktop test 9, A1: a scroll over overlay UI that can't scroll itself (a card, the bar) goes to the app below:
    // hand the mouse back for a moment so the next wheel ticks reach it (main holds its grab off as well).
    const wheel = (e: WheelEvent): void => {
      if (canScroll(e.target as Element | null, e.deltaX, e.deltaY)) return
      set(false)
      tellMain('overlay:pass', PASS_MS)
    }
    window.addEventListener('wheel', wheel, { passive: true })
    window.addEventListener('mousemove', move)
    document.addEventListener('mouseleave', out)
    window.addEventListener('blur', out)
    return () => {
      clearInterval(watchdog)
      window.removeEventListener('wheel', wheel)
      window.removeEventListener('mousemove', move)
      document.removeEventListener('mouseleave', out)
      window.removeEventListener('blur', out)
    }
  }, [])
}
