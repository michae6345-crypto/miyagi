/**
 * The Dynamic-Island container. ONE black object that morphs between whatever island modes
 * features register (core/registry.ts → islandModes). The highest-priority active mode wins.
 * Width, height and radius animate together on the spring; content crossfades
 * (old out in 80ms, new in after 60ms, rising 4px). The window never resizes.
 *
 * Owner: core. Features add modes; they don't edit this file.
 */
import { AnimatePresence, motion, useIsPresent } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { create } from 'zustand'
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { onUi } from './bus'
import { NO_ACTION, resolveMode, reportedBox, WATCHDOG_TICK_MS, WATCH_REST, watchdogStep } from './islandState'
import { offDock, useIslandOffset, usePillOffset } from './islandPlace'
import { startBuild, useLesson } from './lesson'
import { Boundary } from './ui/Boundary'
import { getIslandModes } from './registry'
import { islandSize, PILL_FALLBACK, type IslandSize } from './islandSize'
import { color, duration, ease, pill, shadows, spring, springOut } from './theme'

/** After a press on the island, an open card holds still this long (Michael's desktop test 5: the first Install missed). */
const PRESS_HOLD_MS = 1500

/**
 * v2 (W0-5): where the island is right now, in the overlay window's coordinates: its box (size + offset from the
 * notch spot), the winning mode, and whether it's pill-sized. For surfaces that sit beside it or grow out of it
 * (the lesson panel, the recovery card) without measuring the DOM. `visible` false while another surface has it.
 */
export type IslandBox = { x: number; y: number; w: number; h: number; mode?: string; pill: boolean; visible: boolean }
const useIslandBoxStore = create<IslandBox>(() => ({ x: 0, y: 0, w: 0, h: 0, mode: undefined, pill: true, visible: false }))
export function useIslandBox(): IslandBox {
  return useIslandBoxStore()
}

export function Island({ top, layout }: { top: number; layout: Layout }): ReactNode {
  const [hover, setHover] = useState(false)
  const [landing, setLanding] = useState(false)
  /** The first spring after a landing must start from rest: the one-frame snap leaves a big velocity that made the pill balloon (~540–830px) before settling. */
  const [justLanded, setJustLanded] = useState(false)
  /** The launcher (its own focusable window) has grown out of the island: hide until it hands back. */
  const [yielded, setYielded] = useState(false)
  const hoverTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  /** A leave is pending (the 300ms grace): the outside-move check below doesn't restart it. */
  const leaving = useRef(false)
  const islandEl = useRef<HTMLDivElement>(null)
  const wrapper = useRef<HTMLDivElement>(null)
  const passFlash = useLesson((s) => s.passFlash)
  /** The pointer is on the island, or pressed it in the last PRESS_HOLD_MS: an open card holds still (islandPlace.ts). */
  const [pointerIn, setPointerIn] = useState(false)
  const [pressHold, setPressHold] = useState(false)
  const pressTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Ask every registered mode whether it wants the island. (Stable array → stable hook order.)
  const islandModes = getIslandModes()
  const wanted = islandModes.map((m) => m.useActive(hover))
  // Open without the pointer on it: a hover peek must stay under the pointer, so only these cards move (islandPlace.ts).
  const held = islandModes.map((m) => m.useActive(false))
  const at = resolveMode(wanted)
  const mode = at < 0 ? undefined : islandModes[at]
  const isPill = !mode || mode.width === undefined

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
      setHover(false)
    }
  }

  // The one idempotent way back to rest: hover, pointer and press holds cleared, timers cancelled, the size re-derived
  // from the live layer (a pill-sized or absent mode snaps its size state to the pill; the spring carries the shape, so
  // an interrupted morph is never left half-way and the window itself is never resized). Safe to call at any time, any
  // number of times: it only ever sets rest values. Called by the watchdog, a disconnect, sleep/wake, a display change,
  // the window going hidden or losing focus, and main's 'island:collapse'.
  const collapseAll = (): void => {
    clearTimeout(hoverTimer.current)
    clearTimeout(pressTimer.current)
    leaving.current = false
    setHover(false)
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
        setTimeout(() => setJustLanded(false), 700)
      }),
      bridge.on('launcher:open', () => setYielded(true)),
      bridge.on('launcher:closed', () => setYielded(false)),
      // Any other surface born from the island (settings…): same hand-over.
      bridge.on('island:yield', () => setYielded(true)),
      bridge.on('island:return', () => setYielded(false)),
      // Main: wake from sleep, unlock, a display change, a hung overlay renderer.
      bridge.on('island:collapse', () => collapseRef.current())
    ]
    return () => offs.forEach((off) => off())
  }, [])

  // Measure the active mode's live layer; the container springs to its size (Michael's review A1). The layer is found
  // by data-island-layer, which only a present layer carries: a mode that comes back under the same key while its exit
  // still runs keeps its old node and gets no new ref, so a ref bound on mount could point at a node that was leaving
  // (measured 0 once gone: the island collapsed to nothing for 35 s).
  // A 0 measurement (or a layer never found) no longer keeps the last size (Michael, Nov 21: a card's ✕ left a big empty
  // black box at the top centre, still eating clicks): a pill stays pill-tall at its last pill width, an empty card
  // falls back to the pill. ./islandSize.ts.
  const [size, setSize] = useState<IslandSize>(PILL_FALLBACK)
  const pillW = useRef(PILL_FALLBACK.w)
  /** Bumped by collapseAll: re-runs the measurement so the size is re-derived from what is actually mounted. */
  const [epoch, setEpoch] = useState(0)
  const modeId = mode?.id
  const fixed = mode?.width
  useLayoutEffect(() => {
    // No mode owns the island: it is at rest, not at the last card's size (the watchdog's reset lands here too).
    if (!modeId) return void setSize((s) => (s.w === pillW.current && s.h === PILL_FALLBACK.h ? s : { w: pillW.current, h: PILL_FALLBACK.h }))
    const root = islandEl.current
    if (!root) return
    let ro: ResizeObserver | undefined
    let raf = 0
    let tries = 0
    const apply = (m: { w: number; h: number } | undefined): void => {
      const next = islandSize(fixed, m, pillW.current)
      if (fixed === undefined && m && m.w > 0) pillW.current = next.w
      setSize((s) => (s.w === next.w && s.h === next.h ? s : next))
    }
    const measure = (el: HTMLElement): void => apply({ w: el.offsetWidth, h: el.offsetHeight })
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
  }, [modeId, fixed, epoch])

  // An open card steps off the spotlight's hole, the coach's and its own targets (Michael's desktop test 3, item 3) and
  // out of the engine's avoid rects (screen.avoid: VS Code's quick-pick, test 9, A3), decided as it opens and then held
  // still (a new avoid rect is the one exception), never moved under the pointer or just after a press (desktop test 5).
  // Transform only.
  const card = mode && !isPill && held[at] ? { id: mode.id, w: size.w, h: size.h } : undefined
  const cardOffset = useIslandOffset(card, top, layout, wrapper, pointerIn || pressHold)
  // The pill slides beside what the engine says must stay visible (VS Code's quick-pick, test 9, A4).
  const peek = !!mode && !isPill && !held[at]
  const pillOffset = usePillOffset(mode && isPill ? { w: size.w, h: size.h } : undefined, peek, top, layout, pointerIn || pressHold)
  // A step card that opens on its own (a peek) clears the docked video panel and VS Code's toolbar too (test 11: it
  // clipped "Bu|ild…" under the panel).
  const playerOn = useLesson((s) => !!s.lesson && s.lesson.mode !== 'lesson')
  const peekAt = { x: (layout.width - size.w) / 2, y: top, w: size.w, h: size.h }
  const offset = card ? cardOffset : peek ? offDock(peekAt, pillOffset, playerOn, layout) : pillOffset

  // Tell main (or the browser bus) our current size, so the launcher can grow out of exactly this shape, and where we
  // are (dx/dy from the notch spot: main's click-through poll covers the island there).
  useEffect(() => {
    // `shown` false = nothing is drawn (no mode, or the launcher has it): main's click poll must not grab a ghost box.
    if (!landing) bridge.emit('island:size', reportedBox(!!modeId && !yielded, size, offset.x, offset.y))
  }, [size, landing, offset.x, offset.y, modeId, yielded])
  // v2: the same box for in-window readers (useIslandBox).
  useEffect(() => {
    const next: IslandBox = { x: Math.round((layout.width - size.w) / 2 + offset.x), y: Math.round(top + offset.y), w: size.w, h: size.h, mode: modeId, pill: isPill, visible: !!modeId && !yielded }
    const cur = useIslandBoxStore.getState()
    if ((Object.keys(next) as (keyof IslandBox)[]).some((k) => cur[k] !== next[k])) useIslandBoxStore.setState(next)
  }, [layout.width, size.w, size.h, offset.x, offset.y, top, modeId, isPill, yielded])

  const enter = (): void => {
    clearTimeout(hoverTimer.current)
    leaving.current = false
    setPointerIn(true)
    hoverTimer.current = setTimeout(() => setHover(true), 150)
  }
  const leave = (): void => {
    clearTimeout(hoverTimer.current)
    leaving.current = true
    setPointerIn(false)
    hoverTimer.current = setTimeout(() => setHover(false), 300)
  }
  const press = (): void => {
    clearTimeout(pressTimer.current)
    setPressHold(true)
    pressTimer.current = setTimeout(() => setPressHold(false), PRESS_HOLD_MS)
  }
  useEffect(() => () => clearTimeout(pressTimer.current), [])
  // Esc or a ✕ (the 'dismiss' UI event) closes surfaces; it never opens the hover card, even with the pointer resting on
  // the island (or its hover timer still running). Hover comes back on the next entry.
  useEffect(
    () =>
      onUi('dismiss', () => {
        clearTimeout(hoverTimer.current)
        setHover(false)
      }),
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
    const collapse = (): void => {
      clearTimeout(hoverTimer.current)
      setHover(false)
    }
    const move = (e: MouseEvent): void => {
      if (!leaving.current && !islandEl.current?.contains(e.target as Node)) leave()
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

  // Safety net (core/islandState.ts): an extended size with no card mode claiming it, or a hover card whose pointer is
  // gone or has been still for a long time, collapses on its own. The snapshot ref keeps one interval for the island's life.
  const lastActivity = useRef(Date.now())
  const snap = useRef({ mode, size, hover, pointerIn })
  snap.current = { mode, size, hover, pointerIn }
  useEffect(() => {
    const bump = (): void => void (lastActivity.current = Date.now())
    window.addEventListener('mousemove', bump)
    window.addEventListener('pointerdown', bump)
    let state = WATCH_REST
    const id = setInterval(() => {
      const r = watchdogStep(state, { ...snap.current, lastActivity: lastActivity.current, now: Date.now() })
      state = r.state
      if (r.action !== NO_ACTION) {
        if (r.action.clearHover) {
          clearTimeout(hoverTimer.current)
          setHover(false)
        }
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

  if (!mode) return null
  const { Content } = mode

  return (
    <motion.div
      ref={wrapper}
      className="pointer-events-none absolute inset-x-0 flex justify-center"
      style={{ top }}
      initial={false}
      animate={{ x: offset.x, y: offset.y }}
      transition={spring}
    >
      <motion.div
        ref={islandEl}
        // Hidden while another surface has it (launcher, settings): not a click target either, or the invisible island
        // keeps eating clicks through overlay.bounds / main's click-catching poll.
        data-hit={yielded ? undefined : true}
        className={`${yielded ? 'pointer-events-none' : 'pointer-events-auto'} relative overflow-hidden text-white`}
        style={{
          background: color.island,
          boxShadow: isPill ? shadows.pill : shadows.card,
          transformOrigin: '50% 0%',
          opacity: yielded ? 0 : 1
        }}
        initial={false}
        animate={{
          width: landing ? pill.landingWidth : size.w,
          height: landing ? pill.height : size.h,
          borderRadius: isPill ? pill.height / 2 : 24
        }}
        transition={landing ? { duration: 0 } : { ...(isPill ? springOut : spring), ...(justLanded ? { velocity: 0 } : {}) }}
        onMouseEnter={enter}
        onMouseLeave={leave}
        onPointerDownCapture={press}
      >
        {/* Step passed: the island flashes green (tint 0 → .25 → 0 over 600ms). */}
        <motion.div
          key={passFlash}
          className="pointer-events-none absolute inset-0"
          style={{ background: color.green }}
          initial={{ opacity: 0 }}
          animate={{ opacity: passFlash ? [0, 0.25, 0] : 0 }}
          transition={{ duration: 0.6, ease: 'easeInOut' }}
        />
        <AnimatePresence initial={false}>
          <Layer key={mode.id} id={mode.id} width={mode.width}>
            {/* A mode that throws renders nothing: the island falls back to the pill (./islandSize.ts) and the mode gets a
                fresh try a second later, so a crashed card isn't an empty black shape until another mode takes over. */}
            <Boundary name={`island mode ${mode.id}`} retryMs={1000}>
              <Content />
            </Boundary>
          </Layer>
        </AnimatePresence>
      </motion.div>
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
function Layer({ id, width, children }: { id: string; width?: number; children: ReactNode }): ReactNode {
  const present = useIsPresent()
  return (
    <motion.div
      data-island-layer={present ? id : undefined}
      className="absolute left-1/2 top-0"
      style={{ x: '-50%', width: width ?? 'max-content', transformOrigin: '50% 0%' }}
      initial={{ opacity: 0, y: 4, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1, transition: { ...spring, opacity: { duration: duration.base, delay: 0.06, ease: ease.out } } }}
      exit={{ opacity: 0, scale: 0.98, transition: { duration: duration.instant } }}
    >
      {children}
    </motion.div>
  )
}
