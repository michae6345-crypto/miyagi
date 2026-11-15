/**
 * The full-screen, click-through overlay window: every registered overlay layer, with the
 * island at z = 50. Also owns overlay.bounds reporting and click-through.
 *
 * Owner: core. Features add layers via defineFeature({ overlayLayers }).
 */
import { useEffect, useRef, type ReactNode } from 'react'
import type { Layout } from '../../../preload/api'
import { cmd } from '../../../common/wire'
import { bridge } from '../bridge'
import { Island } from './Island'
import { getOverlayLayers } from './registry'
import { triggerShortcut, type ActionShortcut } from './shortcuts'

const ISLAND_Z = 50

export function Overlay({ layout }: { layout: Layout }): ReactNode {
  const root = useRef<HTMLDivElement>(null)
  useReportBounds(root, layout)
  // Global shortcuts arrive from main as a 'shortcut' signal; route them through the shared path.
  useEffect(() => bridge.on('shortcut', (kind) => triggerShortcut(kind as ActionShortcut)), [])
  const overlayLayers = getOverlayLayers()
  return (
    <div ref={root} className="absolute inset-0 overflow-hidden" style={{ width: layout.width, height: layout.height }}>
      {overlayLayers
        .filter((l) => l.z < ISLAND_Z)
        .map(({ id, Component }) => (
          <Component key={id} layout={layout} />
        ))}
      <Island top={bridge.platform.pillTop} layout={layout} />
      {overlayLayers
        .filter((l) => l.z >= ISLAND_Z)
        .map(({ id, Component }) => (
          <Component key={id} layout={layout} />
        ))}
    </div>
  )
}

/**
 * Tell the engine where our own UI is (`overlay.bounds`, screen points) so its screen reader
 * ignores it. Sampled every 300ms; sent only when it changes. Elements opt in with
 * data-hit (interactive: also stops click-through) or data-ui (display only).
 */
function useReportBounds(root: React.RefObject<HTMLDivElement | null>, layout: Layout): void {
  useEffect(() => {
    let last = ''
    const tick = (): void => {
      const el = root.current
      if (!el) return
      const box = el.getBoundingClientRect()
      if (!box.width) return
      const k = layout.width / box.width // undo the browser stage's CSS scale (1 in Electron)
      const rects = Array.from(el.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .map((n) => n.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1)
        .map((r) => ({
          x: Math.round((r.left - box.left) * k + layout.origin.x),
          y: Math.round((r.top - box.top) * k + layout.origin.y),
          w: Math.round(r.width * k),
          h: Math.round(r.height * k)
        }))
      const key = JSON.stringify(rects)
      if (key === last) return
      last = key
      bridge.send(cmd('overlay.bounds', { rects }))
    }
    const id = setInterval(tick, 300)
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
    window.addEventListener('mousemove', move)
    document.addEventListener('mouseleave', out)
    window.addEventListener('blur', out)
    return () => {
      clearInterval(watchdog)
      window.removeEventListener('mousemove', move)
      document.removeEventListener('mouseleave', out)
      window.removeEventListener('blur', out)
    }
  }, [])
}
