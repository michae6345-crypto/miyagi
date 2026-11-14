/**
 * Building mode, screen-first (mockup 04): the engine's screen reader (Apple Vision OCR) finds the
 * target on screen and sends `spotlight {rect, caption}`. We dim everything to 55% and cut a rounded,
 * glowing hole at that rect, with a glass caption beside it. Works over any app; never takes a click
 * except on the voice button.
 *
 * Animation (FRONTEND-HANDOFF → "Dim overlay + spotlight"):
 *   - the dim fades in over 280ms;
 *   - the hole is ONE set of motion values (x, y, w, h) driven by the spring. The mask cut-out, the glow
 *     and the outline all read those same values, written straight to the SVG attributes every frame:
 *     no React re-render while it moves;
 *   - the glow pulses once per new target (0.6 → 1 → 0.6, 1.2s), then stays still;
 *   - reduced motion: no spring, no pulse, crossfades only.
 */
import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Volume2 } from 'lucide-react'
import { useLesson, type Rect } from '../../core/lesson'
import { color, radius, shadow, spring } from '../../core/theme'
import { toggleVoice, useVoice } from '../voice/store'
import { hole, holeRadius, placeCaption, type Side } from './place'
import type { SpotlightMode, SpotlightTarget } from './store'

const CAPTION_W = 300
/** Until the caption has been measured (mockup 04: 84). */
const CAPTION_H_GUESS = 84
/** The dim is black at 55%: a spec value, not a theme color. */
const DIM = { fill: '#000', opacity: 0.55, fade: 0.28 } as const
const PULSE = { rest: 0.6, peak: 1, duration: 1.2 } as const

/** Derived from the accent token so Adrian's theme carries through. */
const accentSoft = `color-mix(in srgb, ${color.accent} 22%, transparent)`
const accentLight = `color-mix(in srgb, ${color.accent} 62%, white)`

type Props = {
  target?: SpotlightTarget
  /** The target in THIS window's coordinates (already offset by layout.origin), unpadded. */
  rect?: Rect
  /** Where the caption may go: the window's work area, in window coordinates. */
  bounds: Rect
  mode: SpotlightMode
  /** Only one window draws the caption when a target straddles two displays. */
  showCaption: boolean
}

export function Spotlight({ target, rect, ...rest }: Props): ReactNode {
  return <AnimatePresence>{target && rect && <Scene key="spotlight" target={target} rect={rect} {...rest} />}</AnimatePresence>
}

function Scene({ target, rect, bounds, mode, showCaption }: Props & { target: SpotlightTarget; rect: Rect }): ReactNode {
  const reduced = useReducedMotion() ?? false
  const cut = hole(rect)
  const register = useAnimatedHole(cut, reduced)
  const glow = usePulse(`${target.caption}|${Math.round(cut.x)},${Math.round(cut.y)},${Math.round(cut.w)},${Math.round(cut.h)}`, reduced)
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, '')
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
        <defs>
          {!outline && (
            <mask id={`${id}-hole`} maskUnits="userSpaceOnUse" x="0" y="0" width="100%" height="100%">
              {/* Mask luminance: white keeps the dim, black cuts the hole. */}
              <rect width="100%" height="100%" fill="#fff" />
              <rect ref={register} data-part="hole" fill="#000" />
            </mask>
          )}
          {/* Generous region so the blur isn't clipped on a one-line (short) target. */}
          <filter id={`${id}-glow`} x="-50%" y="-150%" width="200%" height="400%">
            <feGaussianBlur stdDeviation={outline ? 7 : 6} />
          </filter>
        </defs>
        {!outline && <rect width="100%" height="100%" fill={DIM.fill} fillOpacity={DIM.opacity} mask={`url(#${id}-hole)`} data-part="dim" />}
        <motion.g style={{ opacity: glow }} data-part="glow">
          <rect ref={register} fill="none" style={{ stroke: color.accent }} strokeWidth={outline ? 5 : 3} filter={`url(#${id}-glow)`} />
        </motion.g>
        <rect ref={register} data-part="ring" fill="none" style={{ stroke: accentLight }} strokeOpacity={0.9} strokeWidth={outline ? 2 : 1.5} />
      </svg>
      {showCaption && <Caption target={target} hole={cut} bounds={bounds} reduced={reduced} />}
    </motion.div>
  )
}

/**
 * The hole's x/y/w/h as motion values, sprung to each new target. Returns a ref callback: every SVG
 * rect registered with it (mask cut-out, glow, ring) gets the current values written to its
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

/** Glow opacity: one pulse (0.6 → 1 → 0.6 over 1.2s) whenever `key` changes, then still. */
function usePulse(key: string, reduced: boolean) {
  const glow = useMotionValue<number>(PULSE.rest)
  useEffect(() => {
    if (reduced) {
      glow.jump(PULSE.rest)
      return
    }
    const run = animate(glow, [PULSE.rest, PULSE.peak, PULSE.rest], { duration: PULSE.duration, ease: 'easeInOut', times: [0, 0.5, 1] })
    return () => run.stop()
  }, [key, reduced, glow])
  return glow
}

/** Slide-in direction: from the hole toward where the caption lands. */
const ENTER: Record<Side, { x: number; y: number }> = {
  right: { x: -8, y: 0 },
  left: { x: 8, y: 0 },
  below: { x: 0, y: -8 },
  above: { x: 0, y: 8 },
  inside: { x: 0, y: 0 }
}

function Caption({ target, hole: cut, bounds, reduced }: { target: SpotlightTarget; hole: Rect; bounds: Rect; reduced: boolean }): ReactNode {
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

  const at = placeCaption(cut, { w: CAPTION_W, h: height }, bounds)
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
          <div className="truncate text-[12px]" style={{ color: color.label }}>
            Step {index + 1}
            {target.app ? ` · ${target.app}` : ''}
          </div>
          <div className="mt-[2px] text-[16px] font-semibold leading-[21px]">{target.caption}</div>
          {code && (
            <div className="mt-[3px] truncate font-mono text-[13px]" style={{ color: accentLight }}>
              {code}
            </div>
          )}
        </div>
        <button
          data-hit
          className="pointer-events-auto grid h-[34px] w-[34px] shrink-0 cursor-pointer place-items-center rounded-full"
          style={{ background: voiceOn ? color.accent : accentSoft, color: voiceOn ? 'white' : accentLight }}
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
