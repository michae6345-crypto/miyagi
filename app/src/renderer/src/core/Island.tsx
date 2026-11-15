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
import type { Layout } from '../../../preload/api'
import { bridge } from '../bridge'
import { onUi } from './bus'
import { useIslandOffset } from './islandPlace'
import { startBuild, useLesson } from './lesson'
import { Boundary } from './ui/Boundary'
import { getIslandModes } from './registry'
import { color, pill, shadows, spring, springOut } from './theme'

/** After a press on the island, an open card holds still this long (Michael's desktop test 5: the first Install missed). */
const PRESS_HOLD_MS = 1500

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
  const at = wanted.indexOf(true)
  const mode = at < 0 ? undefined : islandModes[at]
  const isPill = !mode || mode.width === undefined

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
      bridge.on('island:return', () => setYielded(false))
    ]
    return () => offs.forEach((off) => off())
  }, [])

  // Measure the active mode's live layer; the container springs to its size (Michael's review A1). The layer is found
  // by data-island-layer, which only a present layer carries: a mode that comes back under the same key while its exit
  // still runs keeps its old node and gets no new ref, so a ref bound on mount could point at a node that was leaving
  // (measured 0 once gone: the island collapsed to nothing for 35 s). A 0 measurement never wins: the last good size stays.
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 120, h: pill.height })
  const modeId = mode?.id
  const fixed = mode?.width
  useLayoutEffect(() => {
    const root = islandEl.current
    if (!root || !modeId) return
    let ro: ResizeObserver | undefined
    let raf = 0
    let tries = 0
    const measure = (el: HTMLElement): void => {
      const w = fixed ?? Math.ceil(el.offsetWidth)
      const h = fixed ? Math.ceil(el.offsetHeight) : pill.height
      if (w > 0 && h > 0) setSize((s) => (s.w === w && s.h === h ? s : { w, h }))
    }
    const bind = (): void => {
      const el = root.querySelector<HTMLElement>(`[data-island-layer="${CSS.escape(modeId)}"]`)
      if (!el) {
        if (++tries < 30) raf = requestAnimationFrame(bind)
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
  }, [modeId, fixed])

  // An open card steps off the spotlight's hole, the coach's and its own targets (Michael's desktop test 3, item 3) and
  // out of the engine's avoid rects (screen.avoid: VS Code's quick-pick, test 9, A3), decided as it opens and then held
  // still (a new avoid rect is the one exception), never moved under the pointer or just after a press (desktop test 5).
  // Transform only.
  const card = mode && !isPill && held[at] ? { id: mode.id, w: size.w, h: size.h } : undefined
  const offset = useIslandOffset(card, top, layout, wrapper, pointerIn || pressHold)

  // Tell main (or the browser bus) our current size, so the launcher can grow out of exactly this shape, and where we
  // are (dx/dy from the notch spot: main's click-through poll covers the island there).
  useEffect(() => {
    if (!landing) bridge.emit('island:size', { w: size.w, h: size.h, dx: offset.x, dy: offset.y })
  }, [size, landing, offset.x, offset.y])

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
        data-hit
        className="pointer-events-auto relative overflow-hidden text-white"
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
            <Boundary name={`island mode ${mode.id}`}>
              <Content />
            </Boundary>
          </Layer>
        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}

/** One mode's content layer. Only a present layer carries data-island-layer, so a leaving one is never measured. */
function Layer({ id, width, children }: { id: string; width?: number; children: ReactNode }): ReactNode {
  const present = useIsPresent()
  return (
    <motion.div
      data-island-layer={present ? id : undefined}
      className="absolute left-1/2 top-0"
      style={{ x: '-50%', width: width ?? 'max-content' }}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0, transition: { duration: 0.2, delay: 0.06, ease: 'easeOut' } }}
      exit={{ opacity: 0, transition: { duration: 0.08 } }}
    >
      {children}
    </motion.div>
  )
}
