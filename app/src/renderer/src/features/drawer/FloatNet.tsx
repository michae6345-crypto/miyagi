/**
 * Feature: drawer. The live network panel, floating over the screen (Michael, Sun 2:57 AM: "make it so I can drag this
 * around and move it, and it moves smoothly"). Feels like iOS picture-in-picture:
 * - the header is the handle; it tracks the pointer 1:1 (transform only, nothing reflows);
 * - release projects where the fling would come to rest (WWDC18 "Designing Fluid Interfaces": v/1000 · r/(1−r),
 *   r = 0.99, the minor axis damped ×0.5) and snaps to the nearest corner, or back into the drawer, with a spring that
 *   starts at the release velocity (only a real fling overshoots a little);
 * - past the screen edge it rubber-bands (0.12) instead of stopping hard;
 * - reduced motion: no momentum, it jumps straight to the target.
 * The card carries data-hit, and the overlay reads hit boxes from the live DOM, so click-through follows it.
 */
import { animate, motion, useMotionValue, useReducedMotion, type AnimationPlaybackControls } from 'motion/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { useLesson } from '../../core/lesson'
import { glass, radius } from '../../core/theme'
import { useLiveNetwork } from '../diagrams/store'
import { PANEL_W, PANEL_W_LESSON, panelRect } from './geometry'
import { NetBody, NetHeader, useHeaderDrag } from './LiveNet'
import { dock, settle, useNetFloat, type Corner } from './netFloat'
import { useDrawer } from './store'

const INSET = 16
/** Clear of the shortcut bar at the bottom (its 88 px + gap), as the drawer and player dock are. */
const BOTTOM_CLEAR = 112
/** Clear of the notch / island band under the menu bar. */
const TOP_CLEAR = 8
const R = 0.99
const RUBBER = 0.12
const FLING = 400 // px/s: below this a drop settles without bounce

type Pt = { x: number; y: number }
type Target = { kind: 'corner'; corner: Corner; at: Pt } | { kind: 'dock'; at: Pt }

export function FloatNetLayer({ layout }: { layout: Layout }): ReactNode {
  const d = useLiveNetwork()
  const spot = useNetFloat((s) => s.spot)
  const pickup = useNetFloat((s) => s.pickup)
  if (!d || (!spot.floating && !pickup)) return null
  return <FloatNet layout={layout} />
}

function FloatNet({ layout }: { layout: Layout }): ReactNode {
  const d = useLiveNetwork()
  const reduced = useReducedMotion() ?? false
  const lessonMode = useLesson((s) => s.lesson?.mode === 'lesson')
  const drawerOpen = useDrawer((s) => s.open)
  const root = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const [w, setW] = useState(lessonMode ? PANEL_W_LESSON : PANEL_W)
  const [h, setH] = useState(300)
  const [dragging, setDragging] = useState(false)
  const [folded, setFolded] = useState(false)
  const anim = useRef<AnimationPlaybackControls[]>([])
  const placed = useRef(false)

  /** Client px → overlay px (the browser stage scales the overlay; Electron is 1:1). */
  const toLocal = useCallback((p: Pt): Pt => {
    const b = root.current?.getBoundingClientRect()
    if (!b || !b.width) return p
    const k = layout.width / b.width
    return { x: (p.x - b.left) * k, y: (p.y - b.top) * k }
  }, [layout.width])

  const bounds = useCallback(() => {
    const wa = layout.workArea
    // workArea is in this window's coordinates (as the drawer's own geometry uses it).
    const minX = wa.x
    const minY = wa.y
    return { minX, minY, maxX: Math.min(layout.width, wa.x + wa.width) - w, maxY: wa.y + wa.height - h }
  }, [layout, w, h])

  const targets = useCallback((): Target[] => {
    const b = bounds()
    const panel = panelRect(layout, lessonMode)
    const left = b.minX + INSET
    let right = b.maxX - INSET
    if (drawerOpen) right = Math.min(right, panel.x - INSET - w) // clear of the drawer column
    right = Math.max(left, right)
    const top = b.minY + INSET + TOP_CLEAR
    const bottom = Math.max(top, b.maxY - BOTTOM_CLEAR)
    const out: Target[] = [
      { kind: 'corner', corner: 'tl', at: { x: left, y: top } },
      { kind: 'corner', corner: 'tr', at: { x: right, y: top } },
      { kind: 'corner', corner: 'bl', at: { x: left, y: bottom } },
      { kind: 'corner', corner: 'br', at: { x: right, y: bottom } }
    ]
    const at = useNetFloat.getState().dockAt
    if (drawerOpen && at) out.push({ kind: 'dock', at: toLocal(at) })
    return out
  }, [bounds, layout, lessonMode, drawerOpen, w, toLocal])

  const stopAnim = (): void => {
    anim.current.forEach((a) => a.stop())
    anim.current = []
  }

  const go = useCallback(
    (t: Target, v: Pt = { x: 0, y: 0 }): void => {
      stopAnim()
      const done = (): void => (t.kind === 'dock' ? dock() : settle(t.corner))
      if (reduced) {
        x.set(t.at.x)
        y.set(t.at.y)
        done()
        return
      }
      const fling = Math.hypot(v.x, v.y) > FLING
      const opts = { type: 'spring' as const, stiffness: 380, damping: fling ? 34 : 40, mass: 1, restDelta: 0.5 }
      const ax = animate(x, t.at.x, { ...opts, velocity: v.x })
      const ay = animate(y, t.at.y, { ...opts, velocity: v.y })
      anim.current = [ax, ay]
      void Promise.all([ax, ay]).then(() => {
        if (anim.current[0] === ax) done()
      })
    },
    [reduced, x, y]
  )

  /** Track the pointer from `start` (a move event) until release, then fling-to-snap. */
  const track = useCallback(
    (start: PointerEvent, offset: Pt): void => {
      stopAnim()
      setDragging(true)
      const samples: { t: number; p: Pt }[] = []
      const place = (e: PointerEvent): Pt => {
        const p = toLocal({ x: e.clientX, y: e.clientY })
        const raw = { x: p.x - offset.x, y: p.y - offset.y }
        const b = bounds()
        const band = (v: number, lo: number, hi: number): number => (v < lo ? lo + (v - lo) * RUBBER : v > hi ? hi + (v - hi) * RUBBER : v)
        x.set(band(raw.x, b.minX, b.maxX))
        y.set(band(raw.y, b.minY, b.maxY))
        samples.push({ t: e.timeStamp, p })
        while (samples.length > 2 && e.timeStamp - samples[0].t > 100) samples.shift()
        return p
      }
      place(start)
      const move = (e: PointerEvent): void => void place(e)
      const up = (e: PointerEvent): void => {
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
        window.removeEventListener('pointercancel', up)
        setDragging(false)
        const p = place(e)
        const first = samples[0]
        const dt = (e.timeStamp - first.t) / 1000
        const v = dt > 0.008 ? { x: (p.x - first.p.x) / dt, y: (p.y - first.p.y) / dt } : { x: 0, y: 0 }
        // Dropped over the drawer: dock.
        const panel = panelRect(layout, lessonMode)
        const all = targets()
        const dockT = all.find((t) => t.kind === 'dock')
        if (dockT && p.x >= panel.x && p.x <= panel.x + panel.w && p.y >= panel.y && p.y <= panel.y + panel.h) return go(dockT, v)
        // Project the resting point; damp the minor axis so a sideways fling keeps its row.
        const k = reduced ? 0 : R / (1 - R) / 1000
        const major = Math.abs(v.x) >= Math.abs(v.y) ? 'x' : 'y'
        const proj = {
          x: x.get() + v.x * k * (major === 'x' ? 1 : 0.5),
          y: y.get() + v.y * k * (major === 'y' ? 1 : 0.5)
        }
        let best = all[0]
        let bestD = Infinity
        for (const t of all) {
          const dd = Math.hypot(t.at.x - proj.x, t.at.y - proj.y)
          if (dd < bestD) {
            bestD = dd
            best = t
          }
        }
        go(best, v)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
      window.addEventListener('pointercancel', up)
    },
    [bounds, go, layout, lessonMode, reduced, targets, toLocal, x, y]
  )

  // Size: follow the card's real height (folding, captions, a new diagram).
  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const ro = new ResizeObserver(() => setH(el.offsetHeight))
    ro.observe(el)
    setH(el.offsetHeight)
    return () => ro.disconnect()
  }, [])

  // First placement: picked up from the drawer (keep tracking that same press), or a remembered corner.
  useLayoutEffect(() => {
    if (placed.current) return
    placed.current = true
    const { pickup, spot } = useNetFloat.getState()
    if (pickup) {
      const at = toLocal({ x: pickup.x, y: pickup.y })
      const ptr = toLocal({ x: pickup.pointerX, y: pickup.pointerY })
      const pw = toLocal({ x: pickup.x + pickup.w, y: 0 }).x - at.x
      if (pw > 40) setW(Math.round(pw))
      x.set(at.x)
      y.set(at.y)
      const offset = { x: ptr.x - at.x, y: ptr.y - at.y }
      track(new PointerEvent('pointermove', { clientX: pickup.pointerX, clientY: pickup.pointerY }), offset)
      return
    }
    if (spot.floating) {
      const t = targets().find((c) => c.kind === 'corner' && c.corner === spot.corner)
      if (t) {
        x.set(t.at.x)
        y.set(t.at.y)
      }
    }
  }, [targets, toLocal, track, x, y])

  // The screen, the drawer or the card's height changed while it rests in a corner: stay in that corner.
  const spot = useNetFloat((s) => s.spot)
  useEffect(() => {
    if (dragging || anim.current.length || !spot.floating) return
    const t = targets().find((c) => c.kind === 'corner' && c.corner === spot.corner)
    if (t && (Math.abs(x.get() - t.at.x) > 1 || Math.abs(y.get() - t.at.y) > 1)) go(t)
  }, [spot, targets, dragging, go, x, y, h])

  const grab = useHeaderDrag((e) => {
    const p = toLocal({ x: e.clientX, y: e.clientY })
    track(e, { x: p.x - x.get(), y: p.y - y.get() })
  })
  const dockNow = (): void => {
    const t = targets().find((c) => c.kind === 'dock')
    if (t) go(t)
    else dock()
  }

  if (!d) return null
  return (
    <div ref={root} className="pointer-events-none absolute inset-0">
      <motion.div
        ref={card}
        data-hit
        data-part="live-net-floating"
        className="pointer-events-auto absolute left-0 top-0 overflow-hidden border px-[18px] pb-[10px]"
        style={{
          x,
          y,
          width: w,
          willChange: 'transform',
          borderRadius: radius.card,
          background: glass.bg,
          borderColor: glass.hairline,
          // A bit more lift than the drawer, and the same opaque inset layer (no blur over other windows).
          boxShadow: `${glass.shadow}, ${glass.shadow}, inset 0 0 0 ${w}px ${glass.bg}`,
          color: glass.text
        }}
        initial={{ opacity: 0.9 }}
        animate={{ opacity: 1 }}
      >
        <NetHeader d={d} folded={folded} onFold={() => setFolded((f) => !f)} grab={grab} dragging={dragging} onDoubleClick={dockNow} />
        {!folded && <NetBody d={d} />}
      </motion.div>
    </div>
  )
}
