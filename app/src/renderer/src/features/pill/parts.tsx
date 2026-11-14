/**
 * The pill's small pieces, sized to mockup 01 (measured at 1×: ring 16px / 2.25 stroke, dot 7px).
 * Brand: the ring is the accent (white), green only for passed, amber only for off track, no glows.
 * The shared atoms in core/ui stay as they are for the cards; these are tuned for the 34px pill.
 */
import { AnimatePresence, motion, useAnimate, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLesson } from '../../core/lesson'
import { color, spring } from '../../core/theme'
import { pulsedOfftrack, ring } from './store'

export type Mark = 'watching' | 'offtrack' | 'passed' | 'check' | 'done'

/** Lesson progress ring: completed steps / total. Advances on the spring when a step passes. */
export function PillRing({
  fraction,
  complete = false,
  size = 16,
  stroke = 2.25
}: {
  fraction: number
  /** The lesson is done: the closed ring turns green. */
  complete?: boolean
  size?: number
  stroke?: number
}): ReactNode {
  const r = (size - stroke) / 2
  // Start from what was last drawn (0 on a fresh lesson → the ring draws in on first appearance).
  const from = useRef(ring.shown)
  useEffect(() => {
    ring.shown = fraction
  }, [fraction])
  const on = fraction > 0.001
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0 -rotate-90">
      {/* Track: the arc's own color, dimmed (like the Activity rings). */}
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color.accent} strokeOpacity={0.22} strokeWidth={stroke} />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={stroke}
        strokeLinecap="round"
        initial={{ pathLength: Math.max(0.001, from.current), opacity: from.current > 0.001 ? 1 : 0, stroke: complete ? color.green : color.accent }}
        animate={{ pathLength: Math.max(0.001, fraction), opacity: on ? 1 : 0, stroke: complete ? color.green : color.accent }}
        // A beat after the check pops, so the eye travels check → ring.
        transition={{ pathLength: { ...spring, delay: 0.08 }, opacity: { duration: 0.15 }, stroke: { duration: 0.4, delay: 0.2 } }}
      />
    </svg>
  )
}

/**
 * The status slot: a 7px dot (gray watching · amber off-track · green passed) that becomes a
 * 16px green check while a step pass is being celebrated, then settles back into a dot.
 * Off-track: the dot eases to amber and pulses twice (scale 1 → 1.35 → 1). Once per episode. No glow, no halo.
 */
export function StatusMark({ mark }: { mark: Mark }): ReactNode {
  const tone = mark === 'offtrack' ? color.amber : mark === 'watching' ? color.gray : color.green
  const off = useLesson((s) => s.offtrack)
  const reduced = useReducedMotion()
  const [dot, animate] = useAnimate<HTMLSpanElement>()
  useEffect(() => {
    if (mark !== 'offtrack' || !off || pulsedOfftrack.has(off)) return
    // Two calm beats while the color eases to amber. No shake, no red.
    if (!reduced) animate(dot.current, { scale: [1, 1.35, 1, 1.35, 1] }, { duration: 1.1, ease: 'easeInOut', delay: 0.15 })
    // Count the episode as seen only if we stayed on screen for the beats. When offtrack arrives the
    // card takes the island at once and this pill is only fading out: it pulses on its next mount.
    const seen = setTimeout(() => pulsedOfftrack.add(off), 700)
    return () => clearTimeout(seen)
  }, [mark, off, reduced, animate, dot])

  return (
    <span className="relative inline-block h-[7px] w-[7px] shrink-0" data-mark={mark}>
      <span ref={dot} className="absolute inset-0 rounded-full" style={{ backgroundColor: tone, transition: 'background-color .3s ease' }} />
      <AnimatePresence>
        {mark === 'check' && (
          <motion.svg
            key="check"
            width="16"
            height="16"
            viewBox="0 0 16 16"
            className="absolute left-1/2 top-1/2 -ml-[8px] -mt-[8px]"
            initial={{ scale: 7 / 16, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, transition: spring }}
            exit={{ scale: 7 / 16, opacity: 0, transition: { duration: 0.2, ease: 'easeIn' } }}
          >
            <circle cx="8" cy="8" r="8" fill={color.green} />
            <motion.path
              d="M4.6 8.3 L6.9 10.5 L11.4 5.7"
              fill="none"
              stroke={color.island}
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.25, ease: 'easeOut', delay: 0.08 }}
            />
          </motion.svg>
        )}
      </AnimatePresence>
    </span>
  )
}

/**
 * A text slot whose width springs between old and new text, so the island (which hugs its content)
 * grows smoothly and the icon / ring / dot glide instead of jumping. Old text leaves upward, new
 * text arrives from below, with almost no overlap (no doubled text mid-swap).
 */
export function SwapText({ id, children, className = '' }: { id: string; children: ReactNode; className?: string }): ReactNode {
  const measure = useRef<HTMLSpanElement>(null)
  // First measurement lands instantly (no growing from 0 on mount); later ones spring.
  const [w, setW] = useState<{ px: number; instant: boolean }>()
  useLayoutEffect(() => {
    const el = measure.current
    if (!el) return
    const read = (): void => {
      const px = el.offsetWidth + 1 // layout px (immune to the stage's CSS scale); +1 for the rounded-off fraction
      setW((prev) => (prev?.px === px ? prev : { px, instant: !prev }))
    }
    read()
    const ro = new ResizeObserver(read) // fonts can land late
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <motion.span
      className="relative block h-[34px] shrink-0 overflow-hidden"
      initial={false}
      animate={{ width: w?.px }}
      transition={w?.instant ? { duration: 0 } : spring}
    >
      <span ref={measure} aria-hidden className={`invisible absolute left-0 top-0 whitespace-nowrap ${className}`}>
        {children}
      </span>
      <AnimatePresence initial={false}>
        <motion.span
          key={id}
          className={`absolute left-0 top-[8px] whitespace-nowrap leading-[18px] ${className}`}
          initial={{ opacity: 0, y: 7 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.24, ease: 'easeOut', delay: 0.11 } }}
          exit={{ opacity: 0, y: -7, transition: { duration: 0.1, ease: 'easeIn' } }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </motion.span>
  )
}

/** Thin build-progress line along the bottom of the building pill (lesson.building.progress). */
export function BuildLine({ progress }: { progress: number }): ReactNode {
  return (
    <motion.span
      className="pointer-events-none absolute bottom-[4px] left-[17px] right-[17px] h-[2px] overflow-hidden rounded-full"
      style={{ background: color.hairline }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      <motion.span
        className="absolute inset-0 origin-left rounded-full"
        style={{ background: color.accent }}
        initial={{ scaleX: 0 }}
        animate={{ scaleX: Math.min(1, Math.max(0, progress)) }}
        transition={spring}
      />
    </motion.span>
  )
}
