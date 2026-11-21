/**
 * Feature: settings. The Settings sheet, born from the notch island (its own focusable window, route `settings`).
 * v2 (A4): a 912x576 sheet (clamped to the screen) with a sidebar: General, Permissions, Privacy, Your own key, Shortcuts
 * (Shell.tsx). It grows out of the black island, then takes the app windows' surface (surface.window + hairline) and their
 * three window lights, so it reads as one family with Onboarding, Home and Progress. Focus starts on the active section
 * and stays inside the sheet (Tab wraps).
 *
 * Opening: `settings:open {from, section}` (main) / requestOpen (browser stage) carries the island's current size and,
 * from openSettings(section), the section to show. The sheet starts on exactly that shape (top = platform.pillTop,
 * centered, black, shadows.pill or .card) and springs into the sheet; the island hides once the sheet has painted
 * (island:yield). Every exit (Esc, the close dot, click outside, the window losing focus) collapses it onto the
 * island's CURRENT size (it may have shrunk from the overview card back to the pill meanwhile), fades the island's
 * content back in, then island:return + settings:hidden. Reduced motion crossfades at full size instead.
 * Unsaved typing is dropped on close (the Shell mounts once per open).
 */
import { motion, useReducedMotion, type HTMLMotionProps, type TargetAndTransition, type Transition } from 'motion/react'
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { bridge, isElectron } from '../../bridge'
import { onUi } from '../../core/bus'
import { getIslandModes, type IslandMode } from '../../core/registry'
import { color, fill, pill, radius, scrim, shadows, spring, springOut, surface, windowSize } from '../../core/theme'
import { Shell } from './Shell'
import { useSettings, type Size } from './store'

type Phase = 'closed' | 'open' | 'closing'

const PILL: Size = { w: pill.landingWidth, h: pill.height }

const isPillSized = (s: Size): boolean => s.h <= pill.height + 1
/** The island's shape at a given size: a pill is fully round, a card uses the island's card radius. */
const shapeOf = (s: Size): TargetAndTransition => ({
  width: s.w,
  height: s.h,
  borderRadius: isPillSized(s) ? s.h / 2 : radius.island,
  boxShadow: isPillSized(s) ? shadows.pill : shadows.card
})
const validSize = (s: unknown): s is Size => !!s && typeof s === 'object' && (s as Size).w > 0 && (s as Size).h > 0
const round = (s: Size): Size => ({ w: Math.round(s.w), h: Math.round(s.h) })

/** Exits hand the island back once the shape is within a pixel. */
const settle = { restDelta: 1, restSpeed: 30 }
const contentIn: Transition = { duration: 0.2, delay: 0.06, ease: 'easeOut' }
const contentOut: Transition = { duration: 0.08 }
/** Space kept free under the sheet when it would otherwise reach the bottom of the screen, and at each side. */
const BOTTOM_MARGIN = 24
const SIDE_MARGIN = 24

/** Set-General's 912x576, never past the screen: below the pill, with a margin at the bottom and the sides. */
export function sheetSize(layout: Layout): Size {
  return {
    w: Math.max(480, Math.min(windowSize.settings.w, layout.width - 2 * SIDE_MARGIN)),
    h: Math.max(320, Math.min(windowSize.settings.h, layout.height - bridge.platform.pillTop - BOTTOM_MARGIN))
  }
}

/** Which island mode the island is showing right now (core/Island's rule, without hover). */
function useIslandMode(): IslandMode | undefined {
  const modes = getIslandModes()
  const wanted = modes.map((m) => m.useActive(false))
  return modes.find((_, i) => wanted[i])
}

export function Settings({ layout }: { layout: Layout }): ReactNode {
  const [phase, setPhaseState] = useState<Phase>('closed')
  const phaseRef = useRef(phase)
  const setPhase = useCallback((p: Phase) => {
    phaseRef.current = p
    setPhaseState(p)
  }, [])
  const [from, setFrom] = useState<Size>(PILL)
  /** Where the collapse lands: the island's size when closing started. */
  const [to, setTo] = useState<Size>(PILL)
  const [gen, setGen] = useState(0)
  const [handoff, setHandoff] = useState(false)

  const openReq = useSettings((s) => s.open)
  const closeReq = useSettings((s) => s.close)
  const islandMode = useIslandMode()
  const reduce = useReducedMotion()

  // ---- open / close ---------------------------------------------------------------------------

  useEffect(() => {
    if (!openReq.seq || phaseRef.current !== 'closed') return
    const f = validSize(openReq.from) ? round(openReq.from) : PILL
    setFrom(f)
    setTo(f)
    setHandoff(true)
    setGen((g) => g + 1)
    setPhase('open')
  }, [openReq, setPhase])

  const close = useCallback(() => {
    if (phaseRef.current !== 'open') return
    // Land on the island as it is now; fall back to where we came from.
    const land = (s: unknown): void => {
      if (phaseRef.current !== 'open') return
      setTo(validSize(s) ? round(s) : from)
      setPhase('closing')
    }
    bridge.invoke<Size | undefined>('settings:island').then(land, () => land(undefined))
  }, [from, setPhase])

  /** End of the collapse (or its safety timer): hand the island back exactly once. */
  const finish = useCallback(() => {
    if (phaseRef.current !== 'closing') return
    setPhase('closed')
    bridge.emit('island:return')
    bridge.invoke('settings:hidden').catch(() => {})
  }, [setPhase])

  useEffect(() => {
    if (closeReq) close()
  }, [closeReq]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const offs = [
      onUi('dismiss', () => void close()),
      onUi('reset', (p) => {
        if ((p as { scope?: string } | undefined)?.scope !== 'lesson') close()
      })
    ]
    return () => offs.forEach((off) => off())
  }, [close])

  // The island hides once the sheet has painted on top of it (rAF doesn't run in a hidden tab: timer fallback).
  useEffect(() => {
    if (phase !== 'open') return
    let done = false
    const yieldIsland = (): void => {
      if (done) return
      done = true
      bridge.emit('island:yield')
    }
    const t = setTimeout(yieldIsland, 50)
    const raf = requestAnimationFrame(() => requestAnimationFrame(yieldIsland))
    return () => {
      clearTimeout(t)
      cancelAnimationFrame(raf)
    }
  }, [phase, gen])

  useEffect(() => {
    if (!handoff) return
    const t = setTimeout(() => setHandoff(false), 160)
    return () => clearTimeout(t)
  }, [handoff, gen])

  // If the collapse can't finish (the window stops painting), don't leave the island hidden.
  useEffect(() => {
    if (phase !== 'closing') return
    const t = setTimeout(finish, 1200)
    return () => clearTimeout(t)
  }, [phase, finish])

  // Electron: Esc anywhere in this window. (The stage's own Esc emits 'dismiss'.) A section that uses Esc first
  // (the shortcut recorder, the delete confirm) stops it before it gets here.
  useEffect(() => {
    if (!isElectron || phase !== 'open') return
    const onKey = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape' && !e.defaultPrevented) close()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [phase, close])

  const onKey = (e: KeyboardEvent<HTMLDivElement>): void => {
    // Focus stays inside the sheet: Tab past the last control comes back to the first (and Shift+Tab the other way).
    if (e.key === 'Tab') {
      const all = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])')).filter(
        (el) => !el.hasAttribute('disabled') && el.tabIndex >= 0 && el.offsetParent !== null
      )
      if (!all.length) return
      const first = all[0]
      const last = all[all.length - 1]
      const at = document.activeElement
      const inside = !!at && e.currentTarget.contains(at)
      if (e.shiftKey && (at === first || !inside)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (at === last || !inside)) {
        e.preventDefault()
        first.focus()
      }
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation() // the stage's Esc would also dismiss cards
      close()
    }
  }

  if (phase === 'closed') return null

  // ---- motion targets -------------------------------------------------------------------------

  const size = sheetSize(layout)
  const exiting = phase === 'closing'
  const grown: TargetAndTransition = { width: size.w, height: size.h, borderRadius: radius.island, boxShadow: shadows.card }
  /** Reduced motion: crossfade at full size. Exit targets keep every key (a dropped key ends the animation early). */
  const faded = { ...grown, opacity: 0 }
  const target: TargetAndTransition = exiting ? (reduce ? faded : { ...shapeOf(to), opacity: 1 }) : { ...grown, opacity: 1 }
  const transition: Transition = exiting ? (reduce ? { duration: 0.2 } : { ...springOut, ...settle }) : spring

  return (
    <div key={gen} className="absolute inset-0" data-settings={phase}>
      {/* A light dim; click anywhere outside to collapse back into the island. */}
      <motion.div
        className="absolute inset-0"
        style={{ background: scrim.launcher }}
        initial={{ opacity: 0 }}
        animate={{ opacity: phase === 'open' ? 1 : 0 }}
        transition={{ duration: phase === 'open' ? 0.16 : 0.24, ease: 'easeOut' }}
        onClick={close}
      />

      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        // Neutral focus rings (the browser default is blue, and blue is not ours), in the theme's label color through
        // --focus-ring, so no color is hard-coded here. Sidebar's tabs read the same variable.
        className="absolute left-1/2 overflow-hidden [&_*:focus-visible]:outline-2 [&_*:focus-visible]:outline-offset-2 [&_*:focus-visible]:outline-[color:var(--focus-ring)]"
        style={{
          top: bridge.platform.pillTop,
          x: '-50%',
          background: color.island,
          color: color.text,
          transformOrigin: '50% 0%',
          ['--focus-ring' as string]: color.label
        }}
        initial={reduce ? faded : { ...shapeOf(from), opacity: 1 }}
        animate={target}
        transition={transition}
        onAnimationComplete={() => exiting && finish()}
        onKeyDown={onKey}
      >
        {/*
          The window surface (the same dark gray and hairline as Onboarding, Home and Progress) fades in over the island's
          black as the sheet grows, and back out as it collapses, so it still lands on the black pill.
        */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{ background: surface.window, boxShadow: `inset 0 0 0 1px ${fill.hairline}`, borderRadius: 'inherit' }}
          initial={{ opacity: reduce ? 1 : 0 }}
          animate={{ opacity: exiting && !reduce ? 0 : 1 }}
          transition={{ duration: exiting ? 0.12 : 0.22, ease: 'easeOut' }}
        />
        {/* The island's own content, handed over: fades out as the sheet grows… */}
        {handoff && phase === 'open' && !reduce && islandMode && (
          <IslandContent mode={islandMode} initial={{ opacity: 1 }} animate={{ opacity: 0 }} transition={contentOut} />
        )}
        {/* …and back in as the sheet collapses onto the island's shape. */}
        {exiting && !reduce && islandMode && (
          <IslandContent mode={islandMode} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.14, delay: 0.12, ease: 'easeOut' }} />
        )}

        <motion.div
          // Laid out at the full sheet size from the first frame, centered: the shape grows over it, never reflows it.
          className="relative"
          style={{ width: size.w, height: size.h, marginLeft: `calc(50% - ${size.w / 2}px)` }}
          initial={{ opacity: 0, y: 4 }}
          animate={exiting ? { opacity: 0, y: 0, transition: contentOut } : { opacity: 1, y: 0, transition: contentIn }}
        >
          <Shell live={phase === 'open'} onClose={close} />
        </motion.div>
      </motion.div>
    </div>
  )
}

/** An island mode's content, positioned exactly as core/Island positions it (top-center of the shape). */
function IslandContent({ mode, ...motionProps }: { mode: IslandMode } & Pick<HTMLMotionProps<'div'>, 'initial' | 'animate' | 'transition'>): ReactNode {
  const { Content } = mode
  return (
    <motion.div className="pointer-events-none absolute left-1/2 top-0" style={{ x: '-50%', width: mode.width ?? 'max-content' }} {...motionProps}>
      <Content />
    </motion.div>
  )
}
