/**
 * Feature: tips (brief: app/agents/tips.md). First-time guidance that teaches the overlay without a manual.
 *
 * At most ONE small coach mark at a time, only the first time its element appears, beside it (never over it):
 *   check     the panel's Check my work      "Press it when you think you're done. miyagi checks your real work."
 *   help      the panel's Need help row      "Try [Hint] first, then [Show me]." (first Not yet, or from step 2 on)
 *   mini      the Mini pill                  "It keeps your place. Click it to open the panel again."
 *   pill      the step pill, panel closed    "Click it to open your lesson."
 *   launcher  the idle pill                  "Press [⌥Space] in any app to start a lesson."
 *   menubar   the menu bar item              "Open it from the menu bar, even with every window closed."
 * Got it or Esc closes it for good; "..." > Don't show tips turns them all off (store.ts keeps both).
 *
 * Calm by design: a tip waits until its element has held still for STABLE_MS (no tips mid-animation), the app has
 * been up for STARTUP_MS, and COOLDOWN_MS has passed since the last one closed. Nothing shows while another surface
 * has the floor (a card out of the island, the launcher or Settings, the spotlight, a diagram, the pill's menu). If
 * its element leaves, the tip goes too; it counts as seen only if it was up for READ_MS.
 *
 * An overlay layer (z 70, over the island): it reads the real elements from the overlay's DOM each frame and reserves
 * its rect (core/dock reserveRect) so the island's cards step around it.
 */
import { AnimatePresence } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge } from '../../bridge'
import { reserveRect, useDock } from '../../core/dock'
import { useIslandBox, type IslandBox } from '../../core/Island'
import { useLesson } from '../../core/lesson'
import { defineFeature } from '../../core/registry'
import { MiyagiMark } from '../../core/ui/Mark'
import { CoachMark, MARK_W } from './CoachMark'
import { place, sameRect, type Rect } from './place'
import { stageTray, TRAY_CHANNEL } from './stage'
import { dismissTip, markSeen, setTipMenu, showTip, tipsEnabled, turnTipsOff, useTips, withdrawTip } from './store'
import { TIPS, type Anchor, type TipContext, type TipId } from './tips'

/** The element must hold still this long before its tip shows. */
const STABLE_MS = 700
/** No tips in the first moments after the overlay starts. */
const STARTUP_MS = 1500
/** Air between one tip closing and the next one showing. */
const COOLDOWN_MS = 1400
/** A tip up this long counts as read even if its element leaves before Got it. */
const READ_MS = 4000
/** How often to ask "can a tip show?" while none is up (while one is, it follows its element every frame). */
const IDLE_POLL_MS = 250
/** How often to ask main where the menu bar item is (it can move when other items come and go). */
const TRAY_POLL_MS = 5000

/** Something else has the floor: the spotlight's hole, a diagram, a concept, the pill's menu. */
const BUSY = '[data-part="hole"], [data-part="diagram-flyout"], [data-part="drawer-concept"], [data-launch-menu]'

const TIP_BY_ID = new Map(TIPS.map((t) => [t.id, t]))

function TipsLayer({ layout }: { layout: Layout }): ReactNode {
  const holder = useRef<HTMLDivElement>(null)
  const card = useRef<HTMLDivElement>(null)
  const active = useTips((s) => s.active)
  const off = useTips((s) => s.off)
  const menu = useTips((s) => s.menu)
  const island = useIslandBox()
  const islandRef = useRef<IslandBox>(island)
  islandRef.current = island
  const panelOpen = useDock((d) => d.open)
  const panelRef = useRef(panelOpen)
  panelRef.current = panelOpen
  const stepIndex = useLesson((s) => Math.max(0, s.steps.findIndex((x) => x.id === s.stepId)))
  const stepRef = useRef(stepIndex)
  stepRef.current = stepIndex

  const [anchor, setAnchor] = useState<Anchor | undefined>()
  const [size, setSize] = useState({ w: MARK_W, h: 128 })
  const menubarSeen = useTips((s) => s.seen.includes('menubar'))
  const tray = useTray(layout, !off && !menubarSeen)
  const trayRef = useRef(tray)
  trayRef.current = tray
  // The stage swaps its desktop picture (with a menu bar) for a plain backdrop during a panel lesson.
  const plainStage = useLesson((s) => s.lesson?.mode === 'lesson')

  useEffect(() => {
    if (!tipsEnabled || off) return
    const mountedAt = Date.now()
    let candidate: { id: TipId; target: Rect; since: number } | undefined
    let shownAt = 0
    let raf = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    const tick = (): void => {
      const root = holder.current?.parentElement
      const s = useTips.getState()
      if (!root || s.off) return
      const box = root.getBoundingClientRect()
      const k = root.offsetWidth ? box.width / root.offsetWidth : 1 // the stage's CSS scale (1 in Electron)
      const toLocal = (r: DOMRect): Rect => ({ x: (r.left - box.left) / k, y: (r.top - box.top) / k, w: r.width / k, h: r.height / k })
      const ctx: TipContext = {
        rect: (sel) => {
          const el = root.querySelector(sel)
          if (!el) return undefined
          const r = el.getBoundingClientRect()
          return r.width > 1 && r.height > 1 ? toLocal(r) : undefined
        },
        el: (sel) => root.querySelector<HTMLElement>(sel),
        island: islandRef.current,
        panelOpen: panelRef.current,
        stepIndex: stepRef.current,
        tray: trayRef.current,
        os: bridge.platform.os,
        seen: (id) => useTips.getState().seen.includes(id),
        height: layout.height
      }
      // Another surface has the floor: a card grew out of the island, the launcher or Settings borrowed it, the
      // spotlight or a diagram is up.
      const busy = !ctx.island.visible || !ctx.island.pill || !!root.querySelector(BUSY)
      const now = Date.now()

      if (s.active) {
        const a = busy ? undefined : TIP_BY_ID.get(s.active)?.anchor(ctx)
        if (!a) {
          withdrawTip(now - shownAt >= READ_MS)
          setAnchor(undefined)
          return
        }
        setAnchor((cur) => (cur && cur.side === a.side && sameRect(cur.target, a.target, 0.5) && sameRect(cur.avoid, a.avoid, 0.5) ? cur : a))
        return
      }

      if (busy || now - mountedAt < STARTUP_MS || now - s.closedAt < COOLDOWN_MS) {
        candidate = undefined
        return
      }
      for (const tip of TIPS) {
        if (s.seen.includes(tip.id)) continue
        const a = tip.anchor(ctx)
        if (!a) continue
        if (!candidate || candidate.id !== tip.id || !sameRect(candidate.target, a.target)) {
          candidate = { id: tip.id, target: a.target, since: now }
        } else if (now - candidate.since >= STABLE_MS) {
          candidate = undefined
          shownAt = now
          setAnchor(a)
          showTip(tip.id)
        }
        return
      }
      candidate = undefined
    }

    // Every frame while a tip is up (it follows its element), a few times a second otherwise.
    const loop = (): void => {
      tick()
      if (useTips.getState().active) raf = requestAnimationFrame(loop)
      else timer = setTimeout(loop, IDLE_POLL_MS)
    }
    loop()
    return () => {
      cancelAnimationFrame(raf)
      if (timer) clearTimeout(timer)
    }
  }, [off, layout.height])

  // The mark's real size, for placing it (its text wraps to 2 or 3 lines).
  useLayoutEffect(() => {
    const el = card.current
    if (!el) return
    const measure = (): void => setSize((s) => (s.w === el.offsetWidth && s.h === el.offsetHeight ? s : { w: el.offsetWidth, h: el.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [active])

  const tip = active ? TIP_BY_ID.get(active) : undefined
  const at = tip && anchor ? place(anchor.side, anchor.target, anchor.avoid ?? anchor.target, size, { w: layout.width, h: layout.height }) : undefined

  // Reserve the mark's rect (screen points) so the island's cards step around it.
  useEffect(() => {
    reserveRect('tips', at ? { x: at.x + layout.origin.x, y: at.y + layout.origin.y, w: size.w, h: size.h } : undefined)
  }, [at?.x, at?.y, size.w, size.h, layout.origin.x, layout.origin.y])
  useEffect(() => () => reserveRect('tips', undefined), [])

  const gotIt = (): void => {
    if (tip?.alsoSeen) tip.alsoSeen.forEach(markSeen)
    dismissTip()
    setAnchor(undefined)
  }

  return (
    <>
      <div ref={holder} className="pointer-events-none absolute left-0 top-0 h-0 w-0" />
      {stageTray && !plainStage && <StageTray x={stageTray.x - layout.origin.x} y={stageTray.y - layout.origin.y} w={stageTray.width} h={stageTray.height} />}
      <AnimatePresence>
        {tip && at && (
          <div key={tip.id} className="pointer-events-none absolute" style={{ left: at.x, top: at.y }}>
            <CoachMark
              ref={card}
              title={tip.title}
              body={tip.body(bridge.platform.os)}
              caret={at.caret}
              caretAt={at.caretAt}
              menu={menu}
              onMenu={setTipMenu}
              onGotIt={gotIt}
              onOff={() => {
                turnTipsOff()
                setAnchor(undefined)
              }}
            />
          </div>
        )}
      </AnimatePresence>
    </>
  )
}

/**
 * Where main's menu bar (or taskbar) item is, in this overlay's coordinates. Core request 2: main/features/launch.ts
 * answers `launch:tray-bounds` with tray.getBounds(). Until then the invoke fails and the menu bar tip never shows.
 */
function useTray(layout: Layout, wanted: boolean): Rect | undefined {
  const [tray, setTray] = useState<Rect | undefined>()
  useEffect(() => {
    if (!wanted || !tipsEnabled) return
    let alive = true
    const ask = (): void => {
      let p: Promise<unknown>
      try {
        p = bridge.invoke<unknown>(TRAY_CHANNEL)
      } catch {
        return
      }
      p.then((r) => {
        if (!alive) return
        const b = r as { x?: unknown; y?: unknown; width?: unknown; height?: unknown } | undefined
        const ok = b && [b.x, b.y, b.width, b.height].every((v) => typeof v === 'number' && Number.isFinite(v)) && (b.width as number) > 0
        const next = ok ? { x: (b.x as number) - layout.origin.x, y: (b.y as number) - layout.origin.y, w: b.width as number, h: b.height as number } : undefined
        setTray((cur) => (next && cur && sameRect(cur, next) ? cur : next))
      }).catch(() => undefined)
    }
    ask()
    const id = setInterval(ask, TRAY_POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [wanted, layout.origin.x, layout.origin.y])
  return tray
}

/** Browser stage only: a stand-in menu bar item (the small tree, as main's Tray draws it) for the menu bar tip to point at. */
function StageTray({ x, y, w, h }: { x: number; y: number; w: number; h: number }): ReactNode {
  return (
    <div aria-hidden data-ui className="pointer-events-none absolute flex items-center justify-center" style={{ left: x, top: y, width: w, height: h }}>
      <MiyagiMark size={16} />
    </div>
  )
}

export default defineFeature({ id: 'tips', overlayLayers: [{ id: 'tips', z: 70, Component: TipsLayer }] })
