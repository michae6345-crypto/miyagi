/**
 * The Dynamic-Island container. ONE black object that morphs between whatever island modes
 * features register (core/registry.ts → islandModes). The highest-priority active mode wins.
 * Width, height and radius animate together on the spring; content crossfades
 * (old out in 80ms, new in after 60ms, rising 4px). The window never resizes.
 *
 * Owner: core. Features add modes; they don't edit this file.
 */
import { animate, AnimatePresence, motion, useIsPresent, useMotionValue, useReducedMotion, useTransform } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { create } from 'zustand'
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { onUi } from './bus'
import { NO_ACTION, resolveMode, reportedBox, WATCHDOG_TICK_MS, WATCH_REST, watchdogStep } from './islandState'
import { offDock, useIslandOffset, usePillOffset } from './islandPlace'
import { startBuild, useLesson } from './lesson'
import { Boundary } from './ui/Boundary'
import { MiyagiMark } from './ui/Mark'
import { getIslandModes, type IslandMode } from './registry'
import { perf } from './perf'
import { NotchContext } from './notchContext'
import { islandSizeFor, PILL_FALLBACK, type IslandSize } from './islandSize'
import { color, pill, shadows } from './theme'
import {
  EAR_W,
  HOVER,
  isOpenView,
  notchClip,
  notchOf,
  notchSize,
  radiiFor,
  restSize,
  viewWith,
  type NotchView
} from './notchGeometry'
import {
  cfgFor,
  HOVER_IDLE,
  hoverCancel,
  hoverDeadline,
  hoverEnter,
  hoverLeave,
  hoverOpenNow,
  hoverPoint,
  hoverReset,
  hoverTick,
  inHoverZone,
  peekOpen,
  STRETCH,
  STRETCH_IDLE,
  stretchScale,
  stretchWheel,
  type HoverState
} from './hoverIntent'
import { coexistIn, coexistOf, coreMask, coreCut, HOVER_SCALE, islandPlan, NOTCH_SPRING, restViewFor, seamRect, stickyNotch } from './islandRest'
import type { NotchLayout } from '../../../common/notch'
import { beat, ease, fade, instant, sizeMove, spring, springOut } from './ui/motion'

/** After a press on the island, an open card holds still this long (Michael's desktop test 5: the first Install missed). */
const PRESS_HOLD_MS = 1500

/**
 * v2 (W0-5): where the island is right now, in the overlay window's coordinates: its box (size + offset from the
 * notch spot), the winning mode, and whether it's pill-sized. For surfaces that sit beside it or grow out of it
 * (the lesson panel, the recovery card) without measuring the DOM. `visible` false while another surface has it.
 */
export type IslandBox = { x: number; y: number; w: number; h: number; mode?: string; pill: boolean; visible: boolean }
const useIslandBoxStore = create<IslandBox>(() => ({ x: 0, y: 0, w: 0, h: 0, mode: undefined, pill: true, visible: false }))
/** The whole box, or one value of it (`useIslandBox((b) => b.mode)`: re-renders only when that value changes). */
export function useIslandBox(): IslandBox
export function useIslandBox<T>(select: (b: IslandBox) => T): T
export function useIslandBox<T>(select?: (b: IslandBox) => T): T | IslandBox {
  return useIslandBoxStore((select ?? ((b: IslandBox) => b)) as (b: IslandBox) => T | IslandBox)
}
/** The box right now, without subscribing: for an animation target read when the animation starts. */
export const islandBoxNow = (): IslandBox => useIslandBoxStore.getState()

export function Island({ top, layout }: { top: number; layout: Layout }): ReactNode {
  // Hover is a pure state machine (./hoverIntent.ts): `drive` applies one transition and arms its one timer.
  const [hi, setHi] = useState<HoverState>(HOVER_IDLE)
  const hiRef = useRef<HoverState>(HOVER_IDLE)
  // Declared first: coexist depends on being in the notch at all (a pill below the bar has nothing to share).
  const lastNm = useRef<NotchLayout | undefined>(undefined)
  const nm = stickyNotch(layout, lastNm.current)
  if (notchOf(layout)) lastNm.current = notchOf(layout)
  const coexist = coexistIn(nm, layout.notch)
  const cfgRef = useRef(cfgFor(coexist))
  cfgRef.current = cfgFor(coexist)
  const hover = peekOpen(hi)
  // Reduce Motion: the shape snaps to its new size (MotionConfig drops transforms, not sizes); the content still fades.
  const reduced = useReducedMotion()
  const [landing, setLanding] = useState(false)
  /** The first spring after a landing must start from rest: the one-frame snap leaves a big velocity that made the pill balloon (~540–830px) before settling. */
  const [justLanded, setJustLanded] = useState(false)
  /** The launcher (its own focusable window) has grown out of the island: hide until it hands back. */
  const [yielded, setYielded] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const drive = (fn: (s: HoverState, now: number) => HoverState): void => {
    const next = fn(hiRef.current, Date.now())
    if (next === hiRef.current) return
    hiRef.current = next
    setHi(next)
    clearTimeout(hoverTimer.current)
    const at = hoverDeadline(next, cfgRef.current)
    if (at !== undefined) hoverTimer.current = setTimeout(() => driveRef.current((s, now) => hoverTick(s, now, cfgRef.current)), Math.max(0, at - Date.now()))
  }
  const driveRef = useRef(drive)
  driveRef.current = drive
  const cancelHover = (): void => drive((s) => hoverCancel(s))
  const [stretch, setStretch] = useState(1)
  const stretchRef = useRef(STRETCH_IDLE)
  const stretchTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const islandEl = useRef<HTMLDivElement>(null)
  const wrapper = useRef<HTMLDivElement>(null)
  const passFlash = useLesson((s) => s.passFlash)
  /** The pointer is on the island, or pressed it in the last PRESS_HOLD_MS: an open card holds still (islandPlace.ts). */
  const [pointerIn, setPointerIn] = useState(false)
  const [pressHold, setPressHold] = useState(false)
  const pressTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const landedTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Ask every registered mode whether it wants the island. (Stable array → stable hook order.)
  const islandModes = getIslandModes()
  const wanted = islandModes.map((m) => m.useActive(hover))
  // Open without the pointer on it: a hover peek must stay under the pointer, so only these cards move (islandPlace.ts).
  const held = islandModes.map((m) => m.useActive(false))
  const at = resolveMode(wanted)
  const mode = at < 0 ? undefined : islandModes[at]
  // In the notch (layout.notch.place 'notch'): the island is anchored at the display top and drawn in the notch shape.
  // Undefined = the pill below the menu bar, which is exactly what this file did before.
  // A notched display never loses its notch for a moment (full screen, a display change): the last good one stands in.
  const nmKey = nm ? `${nm.x},${nm.width},${nm.height}` : ''
  const views = islandModes.map((m): NotchView => (m.notch ? m.notch.useView() : 'drop'))
  // Moving into the notch: at rest the island is invisible on the hardware notch, so the move would look like nothing
  // happened. Show the ears (bonsai + status) for a moment so the learner sees miyagi land there.
  const [notchLanding, setNotchLanding] = useState(false)
  const inNotch = !!nm
  useEffect(() => {
    if (!inNotch) return
    setNotchLanding(true)
    const t = setTimeout(() => setNotchLanding(false), 1800)
    return () => clearTimeout(t)
  }, [inNotch])
  const modeView: NotchView = at < 0 ? 'rest' : views[at]
  const baseView: NotchView = notchLanding && modeView === 'rest' ? restViewFor({ connected: false, lessonLoaded: false, landing: true }) : modeView
  /** The active mode's layer shows nothing (or its Boundary fell back): the island is the pill, not a card-wide bar. */
  const [layerEmpty, setLayerEmpty] = useState(false)
  // In the notch an empty card stays a card (its zero-height content sizes it to the notch): flipping it to a pill would
  // unmount its layer, and the layer's reset would flip it back.
  const isPill = !mode || mode.width === undefined || (!nm && layerEmpty)
  /** What a pill-sized mode shows in the notch now: the pointer over a rest or ears view opens the peek. */
  const view: NotchView = nm && isPill ? viewWith(baseView, hover) : 'drop'
  const kind = isPill ? 'pill' : 'card'
  const showLayer = !nm || !isPill || view === 'drop' || view === 'ears+drop'
  const showEars = !!nm && isPill && (view === 'ears' || view === 'ears+drop')
  // Log-only (islandDiagReport, island.log seen=...): what the island decided this render.
  ;(window as unknown as { __miyagiIsland?: unknown }).__miyagiIsland = { nm: nm ? `${nm.x},${nm.width}x${nm.height}` : null, mode: mode?.id ?? null, view, kind, showLayer, showEars, coexist }
  // A card the learner closed under the pointer (its ✕, a button) must not hand the island straight to a hover card:
  // the pointer is still on the island, so the hover overview (or an off-track peek) grew out of it at once, and the
  // island "expanded" on the very click that closed it (Michael, Nov 21). Hover waits for the pointer to leave and come
  // back. Set during render (React's "previous render" pattern), so the hover card never commits for a frame.
  const heldCard = mode && !isPill && held[at] ? mode.id : undefined
  const [lastHeld, setLastHeld] = useState(heldCard)
  if (heldCard !== lastHeld) {
    setLastHeld(heldCard)
    if (lastHeld && !heldCard && hover) {
      clearTimeout(hoverTimer.current)
      hiRef.current = hoverCancel(hiRef.current)
      setHi(hiRef.current)
    }
  }

  // The one idempotent way back to rest: hover, pointer and press holds cleared, timers cancelled, the size re-derived
  // from the live layer (a pill-sized or absent mode snaps its size state to the pill; the spring carries the shape, so
  // an interrupted morph is never left half-way and the window itself is never resized). Safe to call at any time, any
  // number of times: it only ever sets rest values. Called by the watchdog, a disconnect, sleep/wake, a display change,
  // the window going hidden or losing focus, and main's 'island:collapse'.
  const collapseAll = (): void => {
    clearTimeout(pressTimer.current)
    drive((s) => hoverReset(s))
    setPointerIn(false)
    setPressHold(false)
    setEpoch((n) => n + 1)
  }
  const collapseRef = useRef(collapseAll)
  collapseRef.current = collapseAll

  // The launcher just shrank onto our exact pixels: appear at its size, then spring to ours.
  useEffect(() => {
    const offs = [
      bridge.on('pill:receive', () => {
        startBuild()
        setYielded(false)
        setLanding(true)
        setJustLanded(true)
        requestAnimationFrame(() => requestAnimationFrame(() => setLanding(false)))
        clearTimeout(landedTimer.current)
        landedTimer.current = setTimeout(() => setJustLanded(false), 700)
      }),
      bridge.on('launcher:open', () => setYielded(true)),
      bridge.on('launcher:closed', () => setYielded(false)),
      // Any other surface born from the island (settings…): same hand-over.
      bridge.on('island:yield', () => setYielded(true)),
      bridge.on('island:return', () => setYielded(false)),
      // Main: wake from sleep, unlock, a display change, a hung overlay renderer.
      bridge.on('island:collapse', () => collapseRef.current()),
      // Main: the pointer is in the other notch app's open panel: step back to rest (the mute then holds hover off).
      bridge.onFeature('overlay:other-open', (open) => {
        if (open === true) collapseRef.current()
      })
    ]
    return () => {
      offs.forEach((off) => off())
      clearTimeout(landedTimer.current)
    }
  }, [])

  // Measure the active mode's live layer; the container springs to its size (Michael's review A1). The layer is found
  // by data-island-layer, which only a present layer carries: a mode that comes back under the same key while its exit
  // still runs keeps its old node and gets no new ref, so a ref bound on mount could point at a node that was leaving
  // (measured 0 once gone: the island collapsed to nothing for 35 s).
  // A 0 measurement (or a layer never found) no longer keeps the last size (Michael, Nov 21: a card's ✕ left a big empty
  // black box at the top centre, still eating clicks): a pill stays pill-tall at its last pill width, an empty card
  // falls back to the pill. ./islandSize.ts.
  const [size, setSize] = useState<IslandSize>(PILL_FALLBACK)
  /** The first real measurement is in: until then the island is invisible and snaps (no 120 px pill springing wider at launch). */
  const [sized, setSized] = useState(false)
  const pillW = useRef(PILL_FALLBACK.w)
  /** Bumped by collapseAll: re-runs the measurement so the size is re-derived from what is actually mounted. */
  const [epoch, setEpoch] = useState(0)
  const modeId = mode?.id
  const fixed = mode?.width
  useLayoutEffect(() => {
    // No mode owns the island: it is at rest, not at the last card's size (the watchdog's reset lands here too).
    if (nm && !modeId) {
      const r = restSize(nm)
      return void setSize((s) => (s.w === r.w && s.h === r.h ? s : r))
    }
    if (!modeId) return void setSize((s) => (s.w === pillW.current && s.h === PILL_FALLBACK.h ? s : { w: pillW.current, h: PILL_FALLBACK.h }))
    if (nm && isPill && (view === 'rest' || view === 'ears')) {
      // Nothing to measure: the notch itself, or the notch with its ears.
      const r = notchSize(nm, 'pill', view, undefined, undefined)
      setSize((s) => (s.w === r.w && s.h === r.h ? s : r))
      return void setSized(true)
    }
    const root = islandEl.current
    if (!root) return
    let ro: ResizeObserver | undefined
    let raf = 0
    let tries = 0
    const apply = (m: { w: number; h: number } | undefined): void => {
      if (nm) {
        const r = notchSize(nm, kind, view, fixed, m)
        setSize((s) => (s.w === r.w && s.h === r.h ? s : r))
        return void setSized(true)
      }
      const next = islandSizeFor(fixed, layerEmpty, m, pillW.current)
      if ((fixed === undefined || layerEmpty) && m && m.w > 0) pillW.current = next.w
      setSize((s) => (s.w === next.w && s.h === next.h ? s : next))
      setSized(true)
    }
    const measure = (el: HTMLElement): void => {
      // Motion (docs/MOTION.md): a text slot inside a pill (pill/parts SwapText) springs its own width and says where it
      // is going (data-swap-w). Measure the layer at that width, so the island springs once, in step with the slot,
      // instead of re-measuring, re-rendering and re-aiming on every frame of the slot's spring. A card's width is fixed.
      let grow = 0
      if (!nm && (fixed === undefined || layerEmpty)) for (const slot of el.querySelectorAll<HTMLElement>('[data-swap-w]')) grow += Number(slot.dataset.swapW) - slot.offsetWidth
      apply({ w: el.offsetWidth + (Number.isFinite(grow) ? grow : 0), h: el.offsetHeight })
    }
    const bind = (): void => {
      const el = root.querySelector<HTMLElement>(`[data-island-layer="${CSS.escape(modeId)}"]`)
      if (!el) {
        if (++tries < 30) raf = requestAnimationFrame(bind)
        else apply(undefined)
        return
      }
      measure(el)
      ro = new ResizeObserver(() => measure(el))
      ro.observe(el)
    }
    bind()
    return () => {
      cancelAnimationFrame(raf)
      ro?.disconnect()
    }
  }, [modeId, fixed, layerEmpty, epoch, nmKey, view, kind])

  // An open card steps off the spotlight's hole, the coach's and its own targets (Michael's desktop test 3, item 3) and
  // out of the engine's avoid rects (screen.avoid: VS Code's quick-pick, test 9, A3), decided as it opens and then held
  // still (a new avoid rect is the one exception), never moved under the pointer or just after a press (desktop test 5).
  // Transform only.
  const card = mode && !isPill && held[at] ? { id: mode.id, w: size.w, h: size.h } : undefined
  const cardOffset = useIslandOffset(card, top, layout, wrapper, pointerIn || pressHold)
  // The pill slides beside what the engine says must stay visible (VS Code's quick-pick, test 9, A4).
  const peek = !!mode && !isPill && !held[at]
  const pillOffset = usePillOffset(mode && isPill ? { w: size.w, h: size.h } : undefined, peek, top, layout, pointerIn || pressHold)
  // A hover card (a peek) clears the docked video panel sideways (test 11: it clipped "Bu|ild…" under the panel), but is
  // never pushed down under VS Code's toolbar rows: the pointer is on the pill, and a card that opened 112 px lower lost
  // the pointer, closed, and opened again in a loop (MIC-83). Held cards keep the toolbar rule (useIslandOffset).
  const playerOn = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
  const peekAt = { x: (layout.width - size.w) / 2, y: top, w: size.w, h: size.h }
  // In the notch the island never steps aside: it is attached to the notch, and a card grows down from it.
  const cx = nm ? nm.x + nm.width / 2 - layout.width / 2 : 0
  const offset = nm ? { x: cx, y: 0 } : card ? cardOffset : peek ? offDock(peekAt, pillOffset, playerOn, layout, false) : pillOffset

  // Tell main (or the browser bus) our current size, so the launcher can grow out of exactly this shape, and where we
  // are (dx/dy from the notch spot: main's click-through poll covers the island there).
  // One message per animation frame at most (a size and an offset that change together send once), and `shown: false` while no mode
  // owns the island, so main's click poll stops grabbing a ghost card-size rect over the page (the last size stays for the
  // launcher's hand-off).
  const hasMode = !!modeId
  useEffect(() => {
    if (landing) return
    perf.count('island.size.requested')
    const raf = requestAnimationFrame(() => {
      perf.count('island.size.sent')
      // `shown` false = nothing is drawn (no mode, or the launcher has it): main's click poll must not grab a ghost box.
      bridge.emit('island:size', {
        ...reportedBox(hasMode && !yielded, size, offset.x, offset.y),
        // The notch: main grabs from the display top and the launcher / Settings start from this exact shape.
        ...(nm ? { top: 0, place: 'notch' as const, radii: radiiFor(isOpenView(kind, view), size.h) } : {})
      })
    })
    return () => cancelAnimationFrame(raf)
  }, [size, landing, offset.x, offset.y, hasMode, yielded, nmKey, kind, view])
  // v2: the same box for in-window readers (useIslandBox).
  useEffect(() => {
    const next: IslandBox = { x: Math.round((layout.width - size.w) / 2 + offset.x), y: Math.round(top + offset.y), w: size.w, h: size.h, mode: modeId, pill: isPill, visible: !!modeId && !yielded }
    const cur = useIslandBoxStore.getState()
    if ((Object.keys(next) as (keyof IslandBox)[]).some((k) => cur[k] !== next[k])) useIslandBoxStore.setState(next)
  }, [layout.width, size.w, size.h, offset.x, offset.y, top, modeId, isPill, yielded])

  const enter = (): void => {
    setPointerIn(true)
    drive((s, now) => hoverEnter(s, now, cfgRef.current))
  }
  const leave = (): void => {
    setPointerIn(false)
    drive((s, now) => hoverLeave(s, now, cfgRef.current))
  }
  const press = (): void => {
    clearTimeout(pressTimer.current)
    setPressHold(true)
    pressTimer.current = setTimeout(() => setPressHold(false), PRESS_HOLD_MS)
  }
  useEffect(
    () => () => {
      clearTimeout(pressTimer.current)
      clearTimeout(hoverTimer.current)
      clearTimeout(stretchTimer.current)
    },
    []
  )
  // Esc or a ✕ (the 'dismiss' UI event) closes surfaces; it never opens the hover card, even with the pointer resting on
  // the island (or its hover timer still running). Hover comes back on the next entry.
  useEffect(
    () =>
      onUi('dismiss', () => driveRef.current((s) => hoverCancel(s))),
    []
  )

  // The pointer left without a mouseleave (click-through forwarding can drop it): the next move outside, or the
  // pointer leaving the window, ends it. So does the island going away under it.
  useEffect(() => {
    if (!pointerIn) return
    if (!mode) return void setPointerIn(false)
    const move = (e: MouseEvent): void => {
      if (!islandEl.current?.contains(e.target as Node)) setPointerIn(false)
    }
    const out = (): void => setPointerIn(false)
    window.addEventListener('mousemove', move)
    document.addEventListener('mouseleave', out)
    return () => {
      window.removeEventListener('mousemove', move)
      document.removeEventListener('mouseleave', out)
    }
  }, [pointerIn, mode])

  // The hover card must not outstay the pointer (Michael's audit A8): a mouseleave that never came (click-through
  // forwarding can drop it) is caught on the next move outside; the window losing focus or the pointer leaving it,
  // or any shortcut (a bar press, a key: a card is on its way), collapses it at once.
  useEffect(() => {
    if (!hover) return
    const collapse = (): void => cancelHover()
    // When the notch is shared the pointer position (not DOM enter/leave) decides: see the effect below.
    const move = (e: MouseEvent): void => {
      if (!cfgRef.current.coexist && hiRef.current.inside && !islandEl.current?.contains(e.target as Node)) leave()
    }
    const offShortcut = onUi('shortcut', () => void collapse())
    window.addEventListener('mousemove', move)
    window.addEventListener('blur', collapse)
    document.addEventListener('mouseleave', collapse)
    return () => {
      offShortcut()
      window.removeEventListener('mousemove', move)
      window.removeEventListener('blur', collapse)
      document.removeEventListener('mouseleave', collapse)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover])

  // A shared notch: another app owns the core, so DOM enter/leave on our (partly ungrabbed) shape can't be trusted. The
  // pointer's position decides instead (hoverIntent.inHoverZone: the ears and the strip under the notch, plus the open
  // island itself), and a pointer that dwells in the core mutes the island while the other app's panel is open.
  const boxRef = useRef<{ x: number; y: number; w: number; h: number }>({ x: 0, y: 0, w: 0, h: 0 })
  boxRef.current = { x: (layout.width - size.w) / 2 + (nm ? nm.x + nm.width / 2 - layout.width / 2 : 0), y: 0, w: size.w, h: size.h }
  useEffect(() => {
    if (!nm || !coexist) return
    const notch = { x: nm.x, width: nm.width, height: nm.height }
    const move = (e: MouseEvent): void => {
      const p = { x: e.clientX, y: e.clientY }
      const zone = inHoverZone(p, notch, hiRef.current.open ? boxRef.current : undefined)
      const was = hiRef.current.inside
      drive((s, now) => {
        const c = hoverPoint(s, now, cfgRef.current, p, notch)
        return zone && !c.inside ? hoverEnter(c, now, cfgRef.current) : !zone && c.inside ? hoverLeave(c, now, cfgRef.current) : c
      })
      if (zone !== was) setPointerIn(zone)
    }
    const out = (): void => {
      setPointerIn(false)
      drive((s, now) => hoverLeave(hoverPoint(s, now, cfgRef.current, { x: -1e6, y: -1e6 }, notch), now, cfgRef.current))
    }
    window.addEventListener('mousemove', move)
    document.addEventListener('mouseleave', out)
    return () => {
      window.removeEventListener('mousemove', move)
      document.removeEventListener('mouseleave', out)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coexist, nmKey])

  // Safety net (core/islandState.ts): an extended size with no card mode claiming it, or a hover card whose pointer is
  // gone or has been still for a long time, collapses on its own. The snapshot ref keeps one interval for the island's life.
  const lastActivity = useRef(Date.now())
  const dropOk = !!nm && isPill && (view === 'drop' || view === 'ears+drop')
  const snap = useRef({ mode, size, hover, pointerIn, restH: nm?.height, dropOk })
  snap.current = { mode, size, hover, pointerIn, restH: nm?.height, dropOk }
  useEffect(() => {
    const bump = (): void => void (lastActivity.current = Date.now())
    window.addEventListener('mousemove', bump)
    window.addEventListener('pointerdown', bump)
    let state = WATCH_REST
    const id = setInterval(() => {
      const r = watchdogStep(state, { ...snap.current, lastActivity: lastActivity.current, now: Date.now() })
      state = r.state
      if (r.action !== NO_ACTION) {
        if (r.action.clearHover) driveRef.current((s) => hoverCancel(s))
        if (r.action.resetSize) collapseRef.current()
      }
    }, WATCHDOG_TICK_MS)
    return () => {
      clearInterval(id)
      window.removeEventListener('mousemove', bump)
      window.removeEventListener('pointerdown', bump)
    }
  }, [])
  // The engine dropped: whatever the pointer was doing, the island starts over from rest (stores drop their own cards).
  const connected = useLesson((s) => s.connected)
  const wasConnected = useRef(connected)
  useEffect(() => {
    if (wasConnected.current && !connected) collapseRef.current()
    wasConnected.current = connected
  }, [connected])
  // The display changed, or the page came back from hidden (sleep, a Space or full-screen switch): rAF springs may have
  // stalled mid-morph, so re-derive from rest.
  const firstLayout = useRef(true)
  useEffect(() => {
    // Not on mount: the island is already at rest, and a needless remeasure would churn its first morph.
    if (firstLayout.current) return void (firstLayout.current = false)
    collapseRef.current()
  }, [layout.width, layout.height])
  useEffect(() => {
    const visible = (): void => {
      if (document.visibilityState === 'visible') collapseRef.current()
    }
    document.addEventListener('visibilitychange', visible)
    return () => document.removeEventListener('visibilitychange', visible)
  }, [])

  if (!mode) return nm ? <RestingIsland top={0} layout={layout} notch={nm} /> : null
  const { Content } = mode

  const open = nm ? isOpenView(kind, view) : false
  const muted = hi.muted
  /** The down-wheel over a closed island leans it open; past STRETCH.commit it opens (./hoverIntent.ts). */
  const onWheel = (e: React.WheelEvent): void => {
    if (!nm || open || muted) return
    const r = stretchWheel(stretchRef.current, e.deltaY)
    stretchRef.current = r.state
    setStretch(stretchScale(r.state))
    clearTimeout(stretchTimer.current)
    stretchTimer.current = setTimeout(() => {
      stretchRef.current = STRETCH_IDLE
      setStretch(1)
    }, STRETCH.endMs)
    if (r.commit) drive((s, now) => hoverOpenNow(s, now, cfgRef.current))
  }
  const plan = nm ? islandPlan({ nm, coexist, view, open, hovering: hi.light, w: size.w, h: size.h }) : undefined
  const radii = radiiFor(open, size.h)
  const shown = landing && nm ? restSize(nm) : size
  const layers = (
    <NotchContext.Provider value={!!nm}>
      {/* Step passed: the island flashes green (tint 0 → .25 → 0 over 600ms). */}
      <motion.div
        key={passFlash}
        className="pointer-events-none absolute inset-0"
        style={{ background: color.green }}
        initial={{ opacity: 0 }}
        animate={{ opacity: passFlash ? [0, 0.25, 0] : 0 }}
        transition={{ duration: 0.6, ease: ease.inOut }}
      />
      {showEars && <NotchEars key="ears" mode={mode} top={0} h={nm!.height} notchW={nm!.width} />}
      <AnimatePresence initial={false}>
        {showLayer && (
          <Layer key={mode.id} id={mode.id} width={mode.width} onEmpty={setLayerEmpty} top={nm ? nm.height : 0} quiet={!!nm}>
            {/* A mode that throws renders nothing: the island falls back to the pill (./islandSize.ts) and the mode gets a
                fresh try a second later, so a crashed card isn't an empty black shape until another mode takes over. */}
            <Boundary name={`island mode ${mode.id}`} retryMs={1000} fallback={nm ? null : <RestingPill />}>
              <Content />
            </Boundary>
          </Layer>
        )}
      </AnimatePresence>
    </NotchContext.Provider>
  )

  return (
    <motion.div
      ref={wrapper}
      className="pointer-events-none absolute inset-x-0 flex justify-center"
      style={{ top }}
      initial={false}
      animate={{ x: offset.x, y: offset.y }}
      transition={spring}
    >
      <div
        ref={islandEl}
        // Hidden while another surface has it (launcher, settings): not a click target either, or the invisible island
        // keeps eating clicks through overlay.bounds / main's click-catching poll.
        data-hit={!nm && !yielded ? true : undefined}
        data-stretch={nm && !open && !muted ? true : undefined}
        className={`${yielded ? 'pointer-events-none' : 'pointer-events-auto'} relative`}
        // In the notch the hover zone is the island plus a margin (HOVER.margin) either side and below; the margin is
        // transparent and only catches the pointer. Main's grab clamps to the same +-6 / +12 (features/overlay-raise.ts).
        style={nm ? { padding: `0 ${HOVER.margin}px ${HOVER.margin}px`, margin: `0 -${HOVER.margin}px`, opacity: yielded || !sized || muted ? 0 : 1, transition: 'opacity .15s ease-out' } : undefined}
        onMouseEnter={coexist ? undefined : enter}
        onMouseLeave={coexist ? undefined : leave}
        // A link dragged onto the notch opens it (the home panel takes the drop), like Boring Notch's shelf. preventDefault
        // so the drop lands in the page instead of the window trying to open the link.
        onDragEnter={nm && !coexist ? enter : undefined}
        onDragOver={nm ? (e) => e.preventDefault() : undefined}
        onWheel={onWheel}
        onPointerDownCapture={press}
      >
        {nm ? (
          <NotchShape w={shown.w} h={shown.h} rt={radii.top} rb={radii.bottom} tp={radii.taper} open={open} nm={nm} coexist={coexist} shadow={plan!.shadow} scale={open ? 1 : stretch !== 1 ? stretch : hi.light ? HOVER_SCALE : 1} snap={landing || !sized} reduced={!!reduced} lift={justLanded} hit={!yielded && !muted}>
            {layers}
          </NotchShape>
        ) : (
          <motion.div
            className="relative overflow-hidden text-white"
            style={{
              background: color.island,
              boxShadow: isPill ? shadows.pill : shadows.card,
              transformOrigin: '50% 0%',
              opacity: yielded || !sized ? 0 : 1
            }}
            initial={false}
            animate={{
              width: landing ? pill.landingWidth : size.w,
              height: landing ? pill.height : size.h,
              borderRadius: isPill ? pill.height / 2 : 24
            }}
            transition={landing || !sized ? instant : sizeMove(reduced, { ...(isPill ? springOut : spring), ...(justLanded ? { velocity: 0 } : {}) })}
          >
            {layers}
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}

/**
 * The notch shape: black, clipped to a path with concave top "ears" and convex bottom corners. Width, height and both
 * radii spring together inside the fixed overlay window (the window never resizes): opening on a livelier spring,
 * closing critically damped; the clip path is rebuilt from the live values every frame. The shape is its own compositing
 * layer (filter and will-change on the wrapper) before the hover lean scales it from the top. Open or hovered it
 * gets a soft shadow; at rest there is none, so it fuses with the hardware notch. When another notch app shares the
 * notch, the core band is masked out: nothing of ours is drawn there. A 1 px seam sits inside the top of the shape.
 * It is plain notch black at every size: the green glow an open, tall shape had (Nov 22) and the mint gradient that
 * replaced it for a day (Nov 25) are gone (Adrian, MIC-83: a gradient, and it sat behind "Not yet" and the error
 * cards, where green should mean passed).
 */
function NotchShape({ w, h, rt, rb, tp, open, nm, coexist, shadow, scale, snap, reduced, lift, hit, children }: { w: number; h: number; rt: number; rb: number; tp: number; open: boolean; nm: NotchLayout; coexist: boolean; shadow: string; scale: number; snap: boolean; reduced: boolean; lift: boolean; hit: boolean; children: ReactNode }): ReactNode {
  const W = useMotionValue(w)
  const H = useMotionValue(h)
  const RT = useMotionValue(rt)
  const RB = useMotionValue(rb)
  const TP = useMotionValue(tp)
  useEffect(() => {
    const t = snap || reduced ? instant : open ? NOTCH_SPRING.open : NOTCH_SPRING.close
    const to = lift ? { ...t, velocity: 0 } : t
    const runs = [animate(W, w, to), animate(H, h, to), animate(RT, rt, to), animate(RB, rb, to), animate(TP, tp, to)]
    return () => runs.forEach((r) => r.stop())
  }, [w, h, rt, rb, tp, open, snap, reduced, lift, W, H, RT, RB, TP])
  const clip = useTransform([W, H, RT, RB, TP], ([cw, ch, ct, cb, ctp]: number[]) => notchClip(cw, ch, ct, cb, 0, ctp))
  const mask = useTransform(W, (cw) => (coexist ? coreMask(coreCut(cw, nm)) : 'none'))
  const seam = useTransform([W, RT], ([cw, ct]: number[]) => seamRect(cw, ct))
  const seamLeft = useTransform(seam, (r) => r.left)
  const seamWidth = useTransform(seam, (r) => r.width)
  return (
    <motion.div
      style={{ filter: shadow, transformOrigin: '50% 0%', willChange: 'transform, filter' }}
      initial={false}
      animate={{ scale }}
      transition={reduced ? instant : NOTCH_SPRING.hover}
    >
      <motion.div data-hit={hit ? true : undefined} className="relative overflow-hidden text-white" style={{ width: W, height: H, background: color.island, clipPath: clip, mask, WebkitMask: mask }}>
        <motion.span aria-hidden className="pointer-events-none absolute" style={{ top: 0, height: 1, left: seamLeft, width: seamWidth, background: color.island }} />
        {children}
      </motion.div>
    </motion.div>
  )
}

/**
 * The ears: the bonsai on the left (or the mode's own mark), the mode's status mark on the right. Each sits in the
 * middle of its ear, which is EAR_W wide and starts at the hardware notch's edge, whatever width the island has
 * (a drop is wider than the notch plus its ears).
 */
function NotchEars({ mode, top, h, notchW }: { mode: IslandMode; top: number; h: number; notchW: number }): ReactNode {
  const Left = mode.notch?.Left
  const Right = mode.notch?.Right
  const off = notchW / 2 + EAR_W / 2
  const mark = (side: 1 | -1): CSSProperties => ({ position: 'absolute', top: (h - 16) / 2, left: `calc(50% + ${side * off}px - 8px)`, width: 16, height: 16 })
  return (
    <motion.div
      data-ui
      data-ears
      className="pointer-events-none absolute inset-x-0"
      style={{ top, height: h }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { ...fade.in, delay: beat } }}
      exit={{ opacity: 0, transition: fade.instant }}
    >
      <span className="grid place-items-center" style={mark(-1)}>{Left ? <Left /> : <MiyagiMark size={16} />}</span>
      <span className="grid place-items-center" style={mark(1)}>{Right ? <Right /> : null}</span>
    </motion.div>
  )
}

/**
 * One mode's content layer. Only a present layer carries data-island-layer, so a leaving one is never measured.
 * Polish (UI-POLISH-SPEC 8, the pill morph): while the black shape springs to its new size, the old content shrinks a
 * hair and fades out fast (80 ms) and the new content grows in from .96 at the top center on the same spring, its
 * fade a touch late (60 ms) so the two never sit on top of each other. Transform and opacity only; with reduced
 * motion, the fades alone.
 */
function Layer({ id, width, onEmpty, top = 0, quiet = false, children }: { id: string; width?: number; onEmpty: (empty: boolean) => void; top?: number; quiet?: boolean; children: ReactNode }): ReactNode {
  const present = useIsPresent()
  const layer = useRef<HTMLDivElement>(null)
  const body = useRef<HTMLDivElement>(null)
  const [empty, setEmpty] = useState(false)
  /** The body already holds the resting pill (a Boundary fallback): don't add a second. */
  const [bodyResting, setBodyResting] = useState(false)
  const zeroTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  // Tell the island, and clear it when this layer goes (a mode change must not inherit its predecessor's emptiness).
  useEffect(() => {
    if (present) onEmpty(empty)
  }, [empty, present, onEmpty])
  // Only the live layer may reset it: a leaving layer unmounting after its successor reported must not clobber that.
  const presentRef = useRef(present)
  presentRef.current = present
  useEffect(
    () => () => {
      if (presentRef.current) onEmpty(false)
    },
    [onEmpty]
  )
  // Never an empty black shape. Two ways a live layer shows nothing, and both get a safe default:
  //  - its content renders nothing (a mode with no content, a hidden child): the resting pill mark fills in;
  //  - its fade-in never ran (the renderer's rAF stalls while macOS treats the transparent panel as occluded, after
  //    a Space change, sleep or lock), so it sits at opacity 0 over the black: force it visible.
  useEffect(() => {
    if (!present) return
    // A zero-size body must persist EMPTY_DEBOUNCE_MS before it counts (a card whose content mounts a frame late
    // would flash the pill and back); the resting pill (a Boundary fallback) counts at once; non-empty clears at once.
    const measure = (): void => {
      const b = body.current
      const resting = !!b?.querySelector('[data-resting]')
      const zero = !b || b.offsetWidth === 0 || b.offsetHeight === 0
      clearTimeout(zeroTimer.current)
      setBodyResting(resting)
      if (resting) setEmpty(true)
      else if (!zero) setEmpty(false)
      else zeroTimer.current = setTimeout(() => setEmpty(true), EMPTY_DEBOUNCE_MS)
    }
    measure()
    // Empty-ness follows the body's size (no polling); the fade check polls only until the layer is seen visible.
    const ro = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(measure)
    if (body.current) ro?.observe(body.current)
    const born = Date.now()
    const unstick = (): void => {
      const el = layer.current
      if (!el || Date.now() - born < FADE_GRACE_MS) return
      if (Number(getComputedStyle(el).opacity) < 0.99) el.style.opacity = '1'
      else clearInterval(iv)
    }
    const t = setTimeout(() => {
      measure()
      unstick()
    }, FADE_GRACE_MS)
    const iv = setInterval(unstick, 500)
    return () => {
      clearTimeout(zeroTimer.current)
      clearTimeout(t)
      clearInterval(iv)
      ro?.disconnect()
    }
  }, [present])
  return (
    <motion.div
      ref={layer}
      data-island-layer={present ? id : undefined}
      className="absolute left-1/2"
      style={{ top, x: '-50%', width: empty && present ? 'max-content' : (width ?? 'max-content'), transformOrigin: '50% 0%' }}
      // In the notch the content settles down out of the notch, unblurring as the shape opens (Boring Notch's feel); below
      // the menu bar it rises in as before.
      initial={quiet ? { opacity: 0, y: -8, scale: 0.97, filter: 'blur(4px)' } : { opacity: 0, y: 4, scale: 0.96 }}
      animate={
        quiet
          ? { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)', transition: { ...spring, opacity: { ...fade.in, delay: beat }, filter: { duration: 0.28, ease: 'easeOut', delay: beat } } }
          : { opacity: 1, y: 0, scale: 1, transition: { ...spring, opacity: { ...fade.in, delay: beat } } }
      }
      exit={{ opacity: 0, scale: 0.98, transition: fade.instant }}
    >
      <div ref={body}>{children}</div>
      {empty && present && !bodyResting && !quiet && <RestingPill />}
    </motion.div>
  )
}

/** A layer that should be fully visible by now (the spring and fade take ~300 ms). */
const FADE_GRACE_MS = 700
/** A zero-size body counts as empty only after it has stayed that way this long. */
const EMPTY_DEBOUNCE_MS = 150

/** The island's resting content: the bonsai, on the notch black. What shows when a mode has nothing (or fails) to show. */
export function RestingPill(): ReactNode {
  return (
    <div data-ui data-resting className="mx-auto flex items-center justify-center" style={{ width: PILL_FALLBACK.w, height: PILL_FALLBACK.h }}>
      <MiyagiMark size={14} />
    </div>
  )
}

/**
 * The whole island failed (its render threw): a static resting pill under the menu bar, so the top of the screen is
 * never just empty and the real one gets its retry a second later (Overlay.tsx's Boundary).
 */
export function RestingIsland({ top, layout, notch }: { top: number; layout?: Layout; notch?: NotchLayout }): ReactNode {
  // `notch` is the island's sticky notch (it outlives a momentary invalid layout); without it, derive from the layout.
  const nm = notch ?? notchOf(layout)
  // In the notch: just the notch rect in notch black (it sits on the hardware notch, so it is invisible there).
  // (Nothing when the notch is shared: the core is the other app's.)
  if (nm)
    return coexistOf(layout?.notch) ? null : (
      <div className="pointer-events-none absolute flex justify-center" style={{ top: 0, left: nm.x, width: nm.width }}>
        <div style={{ width: nm.width, height: nm.height, background: color.island, clipPath: notchClip(nm.width, nm.height, radiiFor(false).top, radiiFor(false).bottom, 0) }} />
      </div>
    )
  return (
    <div className="pointer-events-none absolute inset-x-0 flex justify-center" style={{ top }}>
      <div className="overflow-hidden" style={{ background: color.island, borderRadius: PILL_FALLBACK.h / 2, boxShadow: shadows.pill }}>
        <RestingPill />
      </div>
    </div>
  )
}
