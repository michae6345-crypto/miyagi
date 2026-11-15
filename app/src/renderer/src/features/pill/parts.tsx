/**
 * The pill's small pieces, sized to mockup 01 (measured at 1×: dot 7px; the step count is 13px text).
 * Brand: green only for passed, no hue for off track (a white ring), gray watching, no glows.
 * The shared atoms in core/ui stay as they are for the cards; these are tuned for the 34px pill.
 */
import { AnimatePresence, motion, useAnimate, useReducedMotion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import treeSmall from '../../assets/brand/tree-small-dark.svg'
import { useLesson, useThinking } from '../../core/lesson'
import { color, spring } from '../../core/theme'
import { Spinner } from '../../core/ui/atoms'
import { pulsedOfftrack } from './store'

/** offline: a hollow gray dot (no connection). pending: the next part is still building (spinner, no dot). */
export type Mark = 'watching' | 'offtrack' | 'passed' | 'check' | 'done' | 'offline' | 'pending'

/**
 * The bonsai as a one-color template glyph, like a menu-bar icon: white on the black pill. Adrian's call:
 * the tree is monochrome everywhere in the app (the green pads are for the app icon and external surfaces).
 * Same file and geometry as MiyagiMark's small cut (the SVG is the mask), so nothing is redrawn.
 * 16px: the art is ~10.5×12 inside the box, the optical size of mockup 01's icon.
 */
export function MonoMark({ size = 16, tone = color.text, className = '' }: { size?: number; tone?: string; className?: string }): ReactNode {
  const mask = `url("${treeSmall}") center / contain no-repeat`
  return (
    <span
      aria-hidden
      className={`inline-block shrink-0 ${className}`}
      style={{ width: size, height: size, backgroundColor: tone, WebkitMask: mask, mask }}
    />
  )
}

/**
 * The lead glyph: the bonsai, or the small core Spinner while the engine is thinking (an explain, a hint,
 * a diagram: 2-5 s), so a shortcut never looks dead. Both sit in the same 16px box: no layout change,
 * a 150ms crossfade only when thinking actually starts or stops.
 */
export function LeadMark(): ReactNode {
  const thinking = useThinking()
  return (
    <span className="relative mr-[8px] inline-block h-[16px] w-[16px] shrink-0" data-thinking={thinking || undefined}>
      <motion.span className="absolute inset-0" initial={false} animate={{ opacity: thinking ? 0 : 1 }} transition={{ duration: 0.15 }}>
        <MonoMark />
      </motion.span>
      <AnimatePresence initial={false}>
        {thinking && (
          <motion.span
            key="thinking"
            className="absolute inset-0 grid place-items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <Spinner size={14} />
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}

/**
 * Where the learner is: "4/8" (this step / steps) in tabular figures, so the width holds as the digits change.
 * It replaced the progress ring (Michael's audit A5): at 0 the ring was a hollow circle beside the status dot, and
 * part-filled it read as a spinner. Muted like the "Step 4 ·" label; the number crossfades in place on a change.
 */
export function StepCount({ n, total }: { n: number; total: number }): ReactNode {
  const label = `${n}/${total}`
  return (
    <span className="inline-grid shrink-0 tabular-nums leading-[18px]" style={{ color: color.label }} aria-label={`Step ${n} of ${total}`} data-count={label}>
      <AnimatePresence initial={false}>
        <motion.span
          key={label}
          style={{ gridArea: '1 / 1' }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: 0.24, ease: 'easeOut', delay: 0.11 } }}
          exit={{ opacity: 0, transition: { duration: 0.1, ease: 'easeIn' } }}
        >
          {label}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}

/**
 * The status slot: a 7px dot (gray watching · amber off-track · green passed) that becomes a
 * 16px green check while a step pass is being celebrated, then settles back into a dot.
 * Off-track: the dot eases to amber and pulses twice (scale 1 → 1.35 → 1). Once per episode. No glow, no halo.
 */
export function StatusMark({ mark }: { mark: Mark }): ReactNode {
  // Green only ever means passed, amber only off track; everything else (watching, offline) is gray.
  const tone = mark === 'offtrack' ? color.amber : mark === 'passed' || mark === 'check' || mark === 'done' ? color.green : color.gray
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
      <span
        ref={dot}
        className="absolute inset-0 rounded-full"
        title={mark === 'offline' ? 'Offline' : undefined}
        style={{
          // Offline: the same dot, hollow and gray. Off track: hollow and white (no hue, Adrian Sat 5 PM).
          backgroundColor: mark === 'offline' || mark === 'offtrack' ? 'transparent' : tone,
          boxShadow: `inset 0 0 0 ${mark === 'offline' || mark === 'offtrack' ? 1.5 : 0}px ${mark === 'offtrack' ? tone : color.gray}`,
          transition: 'background-color .3s ease, box-shadow .3s ease'
        }}
      />
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
 * grows smoothly and the icon / count / dot glide instead of jumping. Old text leaves upward, new
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

/**
 * SwapText for the building pill (Michael's desktop test 3, item 9: "Setting up your project fo…"). Same crossfade
 * (old text up and out, new text in from below), but the slot can never be narrower than the text it shows: old and
 * new text stack in one grid cell, both in flow, so the slot is the wider of the two during the swap and then exactly
 * the new text. No measured or animated width that can lag a stage behind and clip the label mid-word; the island
 * (which hugs its content) springs its own width around it.
 */
export function FitSwap({ id, children }: { id: string; children: ReactNode }): ReactNode {
  return (
    <span className="grid h-[34px] shrink-0 overflow-hidden" data-fit>
      <AnimatePresence initial={false}>
        <motion.span
          key={id}
          className="whitespace-nowrap pt-[8px] leading-[18px]"
          style={{ gridArea: '1 / 1' }}
          initial={{ opacity: 0, y: 7 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.24, ease: 'easeOut', delay: 0.11 } }}
          exit={{ opacity: 0, y: -7, transition: { duration: 0.1, ease: 'easeIn' } }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
