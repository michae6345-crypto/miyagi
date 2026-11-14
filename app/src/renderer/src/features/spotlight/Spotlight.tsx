/**
 * Building mode, screen-first (mockup 04, Miyagi brand): the engine's screen reader (Apple Vision OCR)
 * finds the target on screen and sends `spotlight {rect, caption}`. We dim everything to 55% and cut a
 * rounded hole at that rect, edged with a crisp hairline, with a glass caption beside it. Works over
 * any app; never takes a click except on the voice button.
 *
 * Brand (app/brand/BRAND.md): no glows, no blur on the ring, no blue. Color only carries state, like the
 * pill's dot: the hairline is white while Miyagi watches, amber when off track, green when the step
 * passes (a beat, then it fades). It sits over a faint `color.onAccent` keyline so it reads over light apps.
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
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { Volume2 } from 'lucide-react'
import { useLesson, useStatus, type Rect, type Status } from '../../core/lesson'
import { color, font, radius, scrim, shadow, spring, text } from '../../core/theme'
import { toggleVoice, useVoice } from '../voice/store'
import { hole, holeRadius, placeCaption, type Side } from './place'
import type { SpotlightMode, SpotlightTarget } from './store'

const CAPTION_W = 300
/** Until the caption has been measured (mockup 04: 84). */
const CAPTION_H_GUESS = 84
/** The dim: `scrim.spotlight` (black at .66, Adrian's "more contrast"; the handoff said 55%), fading in over 280ms. */
const DIM = { fill: scrim.spotlight, fade: 0.28 } as const
/** The ring: a crisp hairline (no blur) over a faint dark keyline for contrast on light apps. */
const RING = { width: 1.5, keyline: 3.5, keylineOpacity: 0.35 } as const
const PULSE = { from: 0.45, peak: 1, rest: 0.9, duration: 1.2 } as const
/** State colors, the same meaning as the pill's dot. Nothing else in the spotlight has color. */
const RING_COLOR: Record<Status, string> = { watching: color.accent, offtrack: color.amber, passed: color.green }
const DOT_COLOR: Record<Status, string> = { watching: color.gray, offtrack: color.amber, passed: color.green }

type Props = {
  target?: SpotlightTarget
  /** The target in THIS window's coordinates (already offset by layout.origin), unpadded. */
  rect?: Rect
  /** Where the caption may go: the window's work area, in window coordinates. */
  bounds: Rect
  mode: SpotlightMode
  /** Only one window draws the caption when a target straddles two displays. */
  showCaption: boolean
  /** UI outside this window the caption must not cover (the lesson player's window), window coordinates. */
  avoid: Rect[]
}

export function Spotlight({ target, rect, ...rest }: Props): ReactNode {
  return <AnimatePresence>{target && rect && <Scene key="spotlight" target={target} rect={rect} {...rest} />}</AnimatePresence>
}

function Scene({ target, rect, bounds, mode, showCaption, avoid }: Props & { target: SpotlightTarget; rect: Rect }): ReactNode {
  const reduced = useReducedMotion() ?? false
  const cut = hole(rect)
  const register = useAnimatedHole(cut, reduced)
  const status = useStatus()
  const pulse = usePulse(`${status}|${target.caption}|${Math.round(cut.x)},${Math.round(cut.y)},${Math.round(cut.w)},${Math.round(cut.h)}`, reduced)
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
  // Fallback (cut order): the same hairline, no dim.
  const outline = mode === 'outline'

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
            </mask>
          </defs>
        )}
        {!outline && <rect width="100%" height="100%" fill={DIM.fill} mask={`url(#${id}-hole)`} data-part="dim" />}
        <motion.g style={{ opacity: pulse }} data-part="ring">
          <rect ref={register} data-part="keyline" fill="none" style={{ stroke: color.onAccent }} strokeOpacity={RING.keylineOpacity} strokeWidth={RING.keyline} />
          <rect ref={register} data-part="hairline" data-status={status} fill="none" style={{ stroke: RING_COLOR[status], transition: 'stroke 240ms ease-out' }} strokeWidth={RING.width} />
        </motion.g>
      </svg>
      {showCaption && <Caption target={target} hole={cut} bounds={bounds} avoid={avoid} reduced={reduced} status={status} />}
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

function Caption({ target, hole: cut, bounds, avoid: outside, reduced, status }: { target: SpotlightTarget; hole: Rect; bounds: Rect; avoid: Rect[]; reduced: boolean; status: Status }): ReactNode {
  const voiceOn = useVoice((s) => s.on)
  const index = useLesson((s) => Math.max(0, s.steps.findIndex((x) => x.id === s.stepId)))
  const ref = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState(CAPTION_H_GUESS)

  // Measure the real height (captions wrap) so the bottom-edge clamp is exact.
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = (): void => setHeight(el.offsetHeight)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const inOverlay = useOtherUi(ref)
  const at = placeCaption(cut, { w: CAPTION_W, h: height }, bounds, [...inOverlay, ...outside])
  const from = reduced ? { x: 0, y: 0 } : ENTER[at.side]
  const code = target.code ?? target.matched

  return (
    <motion.div
      ref={ref}
      data-ui
      data-side={at.side}
      className="absolute left-0 top-0 border px-[18px] py-[14px]"
      style={{ width: CAPTION_W, borderRadius: radius.card, background: color.glass, borderColor: color.hairline, boxShadow: shadow, backdropFilter: 'blur(30px) saturate(1.4)' }}
      initial={{ opacity: 0, x: at.x + from.x, y: at.y + from.y }}
      animate={{ opacity: 1, x: at.x, y: at.y }}
      transition={reduced ? { duration: 0.2 } : { ...spring, opacity: { duration: 0.2 } }}
    >
      <div className="flex items-center gap-[12px]">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-[7px]" style={{ fontSize: text.xs, color: color.label }}>
            <span data-part="dot" className="h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: DOT_COLOR[status], transition: 'background-color 240ms ease-out' }} />
            <span className="truncate">
              Step {index + 1}
              {target.app ? ` · ${target.app}` : ''}
            </span>
          </div>
          <div className="mt-[2px] font-semibold leading-[20px]" style={{ fontSize: text.sm, color: color.text }}>
            {target.caption}
          </div>
          {code && (
            <div className="mt-[4px] truncate" style={{ fontFamily: font.mono, fontSize: text.xs, color: color.text, opacity: 0.78 }}>
              {code}
            </div>
          )}
        </div>
        {/* Brand: white on dark when on (accent fill + onAccent icon), quiet glass when off. Never blue. */}
        <button
          data-hit
          className="pointer-events-auto grid h-[34px] w-[34px] shrink-0 cursor-pointer place-items-center rounded-full"
          style={{ background: voiceOn ? color.accent : color.hairline, color: voiceOn ? color.onAccent : color.label }}
          onClick={toggleVoice}
          aria-label={voiceOn ? 'Voice on' : 'Voice off'}
          aria-pressed={voiceOn}
        >
          <Volume2 size={16} />
        </button>
      </div>
    </motion.div>
  )
}
