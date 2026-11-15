/**
 * Building mode, screen-first (mockup 04, Miyagi brand): the engine's screen reader (Apple Vision OCR)
 * finds the target on screen and sends `spotlight {rect, caption}`. We dim everything around it and cut a
 * rounded hole at that rect, edged with a crisp hairline, with a glass caption beside it. Works over
 * any app; never takes a click except on the voice button.
 *
 * Two dims (Michael's audit A6): a text lesson's "type here" target gets the soft one (`scrim.spotlightSoft`), so
 * the learner's own code and terminal stay readable around it; Show me (and video lessons) keep the strong one
 * (`scrim.spotlight`). The two crossfade (opacity only) when a target changes kind.
 *
 * Brand (app/brand/BRAND.md) + Adrian ("less like AI slop, more precise"): the cut-out is edged by ONE white
 * hairline, whatever the state (the pill and the card already carry status color), over a faint
 * `color.onAccent` keyline so it reads over light apps. The caption is a chip on the island's black, one line when
 * it fits (two at most), to the right of the cut-out and centered on it (mockup 01; Michael's audit A7): no eyebrow,
 * no dot, no code (the card has the diff). The speaker shows only while voice is on (tap to turn it off).
 *
 * Animation (FRONTEND-HANDOFF → "Dim overlay + spotlight"):
 *   - the dim fades in over 280ms;
 *   - the hole is ONE set of motion values (x, y, w, h) driven by the spring. The mask cut-out and the
 *     ring read those same values, written straight to the SVG attributes every frame: no React
 *     re-render while it moves;
 *   - the ring pulses once in opacity per new target or state (→ 1 → rest, 1.2s), then stays still;
 *   - reduced motion: no spring, no pulse, crossfades only.
 */
import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject, type SVGProps } from 'react'
import { Volume2 } from 'lucide-react'
import { useLesson, useStatus, type Rect } from '../../core/lesson'
import { useDrawer } from '../drawer/store'
import { useLauncherOpen } from '../launcher/store'
import { color, fill, font, radius, scrim, shadows, spring, text } from '../../core/theme'
import { toggleVoice, useVoice } from '../voice/store'
import { hole, holeRadius, placeCaption, type Side } from './place'
import type { SpotlightMode, SpotlightTarget } from './store'

/** The caption chip hugs its text, up to this width, wrapping to at most CAPTION_LINES lines (one is the aim). */
const CAPTION_MAX_W = 420
const CAPTION_LINES = 2
/** Until the caption has been measured: one line. */
const CAPTION_GUESS = { w: 240, h: 26 }
/** The dim: `scrim.spotlight` (black at .66, Adrian's "more contrast") or `scrim.spotlightSoft`, fading in over 280ms. */
const DIM = { strong: scrim.spotlight, soft: scrim.spotlightSoft, fade: 0.28 } as const
/** The ring: a crisp hairline (no blur) over a faint dark keyline for contrast on light apps. */
const RING = { width: 1, keyline: 3, keylineOpacity: 0.35 } as const
const PULSE = { from: 0.45, peak: 1, rest: 0.9, duration: 1.2 } as const
/** While the ask panel (the launcher) is open, the caption and target labels step back so the panel reads (A13). */
const ASKING_OPACITY = 0.3

type Props = {
  target?: SpotlightTarget
  /** The target in THIS window's coordinates (already offset by layout.origin), unpadded. */
  rect?: Rect
  /** Where the caption may go: the window's work area, in window coordinates. */
  bounds: Rect
  mode: SpotlightMode
  /** The soft dim: a text lesson's "type here" target. false = the strong dim (Show me, video lessons). */
  soft: boolean
  /** Only one window draws the caption when a target straddles two displays. */
  showCaption: boolean
  /** UI outside this window the caption must not cover (the lesson player's window), window coordinates. */
  avoid: Rect[]
  /** The coach's other targets (card/offtrack `targets` beyond the one the spotlight is on), window coordinates. */
  extras: Extra[]
}

/** A secondary target: its own cut-out and hairline, slightly quieter than the main one, with a one-line label. */
export type Extra = { id: string; label: string; rect: Rect }
/** Secondary targets sit a step below the main one. */
const EXTRA_RING_OPACITY = 0.7
const LABEL = { h: 24, gap: 6, maxW: 220 } as const

export function Spotlight({ target, rect, ...rest }: Props): ReactNode {
  return <AnimatePresence>{target && rect && <Scene key="spotlight" target={target} rect={rect} {...rest} />}</AnimatePresence>
}

function Scene({ target, rect, bounds, mode, soft, showCaption, avoid, extras }: Props & { target: SpotlightTarget; rect: Rect }): ReactNode {
  const reduced = useReducedMotion() ?? false
  const cut = hole(rect)
  const register = useAnimatedHole(cut, reduced)
  const status = useStatus()
  // Pulse per new target or state, not per move: a moving ring that re-pulses reads as flicker.
  const pulse = usePulse(`${status}|${target.caption}`, reduced)
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  // Fallback (cut order): the same hairline, no dim.
  const outline = mode === 'outline'
  const asking = useLauncherOpen()
  const more = extras.map((e) => ({ ...e, cut: hole(e.rect), key: `${e.id}:${Math.round(e.rect.x)},${Math.round(e.rect.y)},${Math.round(e.rect.w)},${Math.round(e.rect.h)}` }))
  // The caption keeps clear of the other targets and their labels too.
  const keepClear = [...avoid, ...more.map((e) => ({ x: e.cut.x, y: e.cut.y - LABEL.h - LABEL.gap, w: e.cut.w, h: e.cut.h + LABEL.h + LABEL.gap }))]

  return (
    <motion.div
      className="pointer-events-none absolute inset-0"
      data-spotlight={mode}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: DIM.fade, ease: 'easeOut' }}
    >
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        {!outline && (
          <defs>
            <mask id={`${id}-hole`} maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%">
              {/* Mask luminance: white keeps the dim, black cuts the hole. */}
              <rect width="100%" height="100%" fill="#fff" />
              <rect ref={register} data-part="hole" fill="#000" />
              {more.map((e) => (
                <motion.g key={e.key} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: DIM.fade }}>
                  <StaticRect box={e.cut} fill="#000" />
                </motion.g>
              ))}
            </mask>
          </defs>
        )}
        {!outline &&
          (['strong', 'soft'] as const).map((k) => (
            <motion.rect
              key={k}
              width="100%"
              height="100%"
              fill={DIM[k]}
              mask={`url(#${id}-hole)`}
              data-part="dim"
              data-dim={k}
              initial={false}
              animate={{ opacity: (k === 'soft') === soft ? 1 : 0 }}
              transition={{ duration: DIM.fade, ease: 'easeOut' }}
            />
          ))}
        <motion.g style={{ opacity: pulse }} data-part="ring">
          <rect ref={register} data-part="keyline" fill="none" style={{ stroke: color.onAccent }} strokeOpacity={RING.keylineOpacity} strokeWidth={RING.keyline} />
          <rect ref={register} data-part="hairline" data-status={status} fill="none" style={{ stroke: color.text }} strokeWidth={RING.width} />
        </motion.g>
        {more.map((e) => (
          <motion.g key={e.key} data-part="extra" initial={{ opacity: 0 }} animate={{ opacity: EXTRA_RING_OPACITY }} transition={{ duration: DIM.fade }}>
            <StaticRect box={e.cut} fill="none" style={{ stroke: color.onAccent }} strokeOpacity={RING.keylineOpacity} strokeWidth={RING.keyline} />
            <StaticRect box={e.cut} fill="none" style={{ stroke: color.text }} strokeWidth={RING.width} />
          </motion.g>
        ))}
      </svg>
      <motion.div className="absolute inset-0" initial={false} animate={{ opacity: asking ? ASKING_OPACITY : 1 }} transition={{ duration: 0.2 }}>
        {more.map((e) => e.label && <TargetLabel key={e.key} text={e.label} hole={e.cut} bounds={bounds} />)}
        {showCaption && <Caption target={target} hole={cut} bounds={bounds} avoid={keepClear} reduced={reduced} />}
      </motion.div>
    </motion.div>
  )
}

/** A rect that doesn't move (secondary targets): same rounding as the main hole. */
function StaticRect({ box: r, ...rest }: { box: Rect } & SVGProps<SVGRectElement>): ReactNode {
  const rr = holeRadius(r)
  return <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={rr} ry={rr} {...rest} />
}

/** A secondary target's label: one line on the island's black, just above its cut-out (below if there's no room). */
function TargetLabel({ text: label, hole: cut, bounds }: { text: string; hole: Rect; bounds: Rect }): ReactNode {
  const above = cut.y - LABEL.gap - LABEL.h
  const y = above >= bounds.y + 8 ? above : cut.y + cut.h + LABEL.gap
  const x = Math.max(bounds.x + 8, Math.min(cut.x, bounds.x + bounds.w - LABEL.maxW - 8))
  return (
    <motion.div
      data-ui
      data-part="label"
      className="absolute left-0 top-0 truncate px-[9px] font-medium"
      style={{ x, y, maxWidth: LABEL.maxW, height: LABEL.h, lineHeight: `${LABEL.h}px`, fontSize: text.xs, color: color.text, background: color.island, borderRadius: radius.chip, boxShadow: shadows.card }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: DIM.fade }}
      title={label}
    >
      {label}
    </motion.div>
  )
}

/**
 * The hole's x/y/w/h as motion values, sprung to each new target. Returns a ref callback: every SVG
 * rect registered with it (mask cut-out, keyline, hairline) gets the current values written to its
 * attributes on each animation frame, so they move as one object without re-rendering React.
 */
function useAnimatedHole(to: Rect, reduced: boolean): (el: SVGRectElement | null) => void | (() => void) {
  const x = useMotionValue(to.x)
  const y = useMotionValue(to.y)
  const w = useMotionValue(to.w)
  const h = useMotionValue(to.h)
  const els = useRef(new Set<SVGRectElement>())

  const write = useCallback((): void => {
    const r = { x: x.get(), y: y.get(), w: Math.max(0, w.get()), h: Math.max(0, h.get()) }
    const rr = String(holeRadius(r))
    for (const el of els.current) {
      el.setAttribute('x', String(r.x))
      el.setAttribute('y', String(r.y))
      el.setAttribute('width', String(r.w))
      el.setAttribute('height', String(r.h))
      el.setAttribute('rx', rr)
      el.setAttribute('ry', rr)
    }
  }, [x, y, w, h])

  // One spring per axis, same target and timing → the rect moves as one. A new target mid-flight
  // starts from the current values and velocity, so retargeting stays smooth.
  useEffect(() => {
    const goal = [to.x, to.y, to.w, to.h]
    const values = [x, y, w, h]
    if (reduced) {
      values.forEach((v, i) => v.jump(goal[i]))
      return
    }
    const runs = values.map((v, i) => animate(v, goal[i], spring))
    return () => runs.forEach((r) => r.stop())
  }, [to.x, to.y, to.w, to.h, reduced, x, y, w, h])

  useEffect(() => {
    const offs = [x, y, w, h].map((v) => v.on('change', write))
    return () => offs.forEach((off) => off())
  }, [x, y, w, h, write])

  return useCallback(
    (el: SVGRectElement | null) => {
      if (!el) return
      els.current.add(el)
      write()
      return () => {
        els.current.delete(el)
      }
    },
    [write]
  )
}

/** Ring opacity: one pulse (→ 1 → rest over 1.2s) whenever `key` changes, then still. */
function usePulse(key: string, reduced: boolean) {
  const pulse = useMotionValue<number>(PULSE.from)
  useEffect(() => {
    if (reduced) {
      pulse.jump(PULSE.rest)
      return
    }
    const run = animate(pulse, [Math.min(pulse.get(), PULSE.from), PULSE.peak, PULSE.rest], { duration: PULSE.duration, ease: 'easeInOut', times: [0, 0.45, 1] })
    return () => run.stop()
  }, [key, reduced, pulse])
  return pulse
}

/**
 * The overlay's other UI (shortcut bar, pill, cards: everything marked data-hit / data-ui, the same set
 * core reports as overlay.bounds), in window coordinates, so the caption doesn't slide under it.
 * Read from the DOM every 400ms; state changes only when something moved.
 * Local workaround: see "Core requests" in agents/spotlight.md.
 */
function useOtherUi(caption: RefObject<HTMLElement | null>): Rect[] {
  const [rects, setRects] = useState<Rect[]>([])
  useLayoutEffect(() => {
    let last = ''
    const read = (): void => {
      const mine = caption.current?.parentElement // the spotlight scene
      const root = mine?.parentElement // the overlay root
      if (!mine || !root) return
      const box = root.getBoundingClientRect()
      if (!box.width) return
      const k = root.offsetWidth / box.width // undo the browser stage's CSS scale (1 in Electron)
      const next = Array.from(root.querySelectorAll<HTMLElement>('[data-hit],[data-ui]'))
        .filter((el) => !mine.contains(el))
        .map((el) => el.getBoundingClientRect())
        .filter((r) => r.width > 1 && r.height > 1)
        .map((r) => ({ x: Math.round((r.left - box.left) * k), y: Math.round((r.top - box.top) * k), w: Math.round(r.width * k), h: Math.round(r.height * k) }))
      const key = JSON.stringify(next)
      if (key !== last) {
        last = key
        setRects(next)
      }
    }
    read()
    const id = setInterval(read, 400)
    return () => clearInterval(id)
  }, [caption])
  return rects
}

/** Slide-in direction: from the hole toward where the caption lands. */
const ENTER: Record<Side, { x: number; y: number }> = {
  right: { x: -8, y: 0 },
  left: { x: 8, y: 0 },
  below: { x: 0, y: -8 },
  above: { x: 0, y: 8 },
  inside: { x: 0, y: 0 }
}

/** spotlight.snippet: the code to type at the target, shown as-is (whitespace kept), up to 8 lines. */
function Snippet({ code }: { code: string }): ReactNode {
  return (
    <pre
      className="mb-[3px] mt-[6px] max-h-[144px] overflow-hidden whitespace-pre rounded-[10px] px-[10px] py-[7px] text-[12.5px] leading-[18px]"
      style={{ fontFamily: font.mono, background: fill.field, color: color.text }}
    >
      {code.replace(/\s+$/, '')}
    </pre>
  )
}

function Caption({ target, hole: cut, bounds, avoid: outside, reduced }: { target: SpotlightTarget; hole: Rect; bounds: Rect; avoid: Rect[]; reduced: boolean }): ReactNode {
  const voiceOn = useVoice((s) => s.on)
  // The code lives in one place (Michael's desktop test, item 5): a "Just teach me" lesson or an open drawer has it
  // in the drawer, so the caption shows only the words.
  const textLesson = useLesson((s) => s.lesson?.mode === 'lesson')
  const drawerOpen = useDrawer((s) => s.open)
  const showCode = !textLesson && !drawerOpen
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<{ w: number; h: number }>(CAPTION_GUESS)

  // Measure the real size (the caption hugs its line) so it sits exactly beside the cut-out.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = (): void => setSize((s) => (s.w === el.offsetWidth && s.h === el.offsetHeight ? s : { w: el.offsetWidth, h: el.offsetHeight }))
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const inOverlay = useOtherUi(ref)
  const at = placeCaption(cut, size, bounds, [...inOverlay, ...outside])
  const from = reduced ? { x: 0, y: 0 } : ENTER[at.side]

  return (
    <motion.div
      ref={ref}
      data-ui
      data-side={at.side}
      className={`absolute left-0 top-0 py-[4px] pl-[11px] ${voiceOn ? 'pr-[4px]' : 'pr-[11px]'}`}
      style={{ maxWidth: CAPTION_MAX_W, borderRadius: radius.chip, background: color.island, boxShadow: shadows.card }}
      initial={{ opacity: 0, x: at.x + from.x, y: at.y + from.y }}
      animate={{ opacity: 1, x: at.x, y: at.y }}
      transition={reduced ? { duration: 0.2 } : { ...spring, opacity: { duration: 0.2 } }}
    >
      <div className="flex items-center gap-[8px]">
        {/* A one-line chip; up to two lines, then clamped (Michael: one line cut off "Type this in the VS Code terminal (use python…"). */}
        <div
          className="min-w-0 overflow-hidden font-medium leading-[18px]"
          style={{ fontSize: text.xs, color: color.text, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: CAPTION_LINES }}
          title={target.caption}
        >
          {target.caption}
        </div>
        {/* Only while voice is on: white, like every toggle that's on. Tap to turn it off. */}
        {voiceOn && (
          <button
            data-hit
            className="pointer-events-auto -my-[1px] grid h-[20px] w-[20px] shrink-0 cursor-pointer place-items-center rounded-full"
            style={{ background: color.accent, color: color.onAccent }}
            onClick={toggleVoice}
            aria-label="Turn voice off"
          >
            <Volume2 size={12} />
          </button>
        )}
      </div>
      {/* The code to type there ("Just teach me" steps, Show me): monospace under the caption, like the cards' diff. */}
      {showCode && target.snippet?.trim() && <Snippet code={target.snippet} />}
    </motion.div>
  )
}
