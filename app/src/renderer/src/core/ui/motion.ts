/**
 * Core: the ONE motion vocabulary (docs/MOTION.md is the spec). Every animation in the app takes its numbers from
 * here; core/theme.ts re-exports the tokens so older imports keep working.
 *
 *   MOVE   anything that travels, scales or morphs: `spring` in, `springOut` out (same speed, no overshoot).
 *   FADE   opacity and tint layers only: `fade.in` (180 ms) arriving, `fade.out` (120 ms) leaving, on `ease.out`.
 *   BEAT   one step of a sequence (content after its frame, a tick after its circle): `beat` (60 ms).
 *   LOOP   only waiting indicators loop (dots, skeleton, spinner: styles.css), never decoration.
 *
 * Rules: transform and opacity only (a size morph is the one measured exception: MOTION.md, "Size"); a leaving thing
 * is always faster than an arriving one; every enter starts from where the element is now (springs retarget, so a
 * click halfway through just turns the motion around); nothing starts from scale 0.
 *
 * Reduce Motion (macOS Reduce Motion, Windows "Show animations" off: Chromium maps both to prefers-reduced-motion):
 * MotionConfig reducedMotion="user" (main.tsx) drops transform and `layout` animations and keeps fades. What it does
 * NOT cover is handled by the helpers here: size morphs snap (`sizeMove`), path draws become fades (`draw`), and
 * `rise` / `textSwap` fade without travel.
 *
 *   <motion.button {...pressMotion(disabled)} className="mg-press ...">        scale .97 on press, spring back
 *   <motion.ul variants={staggerList} initial="hidden" animate="shown">       children: <motion.li variants={riseItem}>
 *   <motion.div {...riseIn}>                                                  one block rising into place
 *   <motion.div {...rise(reduced, { delay: beat })}>                          the same, reduced-motion aware, later
 */
import type { MotionProps, TargetAndTransition, Transition, Variants } from 'motion/react'

export { beat, duration, ease, fade, instant, press, spring, springOut, stagger } from './motionTokens'
import { beat, duration, ease, fade, instant, press, spring, stagger } from './motionTokens'

// ---------------------------------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------------------------------

/** A fade in that waits `delay` seconds. */
export const fadeIn = (delay = 0): Transition => (delay ? { ...fade.in, delay } : fade.in)

/** Move on the spring and fade on its own clock: the house enter. `delay` holds both. */
export function enter(delay = 0, opacity: Transition = fade.in): Transition {
  return delay ? { ...spring, delay, opacity: { ...opacity, delay } } : { ...spring, opacity }
}

/** A size morph (width / height): the spring, or a snap with reduced motion (MotionConfig does not cover sizes). */
export const sizeMove = (reduced: boolean | null | undefined, t: Transition = spring): Transition => (reduced ? instant : t)

/** whileTap scale on the house spring. `large` for big tiles (.96). No dip at all when disabled. */
export function pressMotion(disabled?: boolean, large?: boolean): Pick<MotionProps, 'whileTap' | 'transition'> {
  return {
    whileTap: disabled ? undefined : { scale: large ? press.scaleLarge : press.scale },
    transition: press.transition
  }
}

type V = TargetAndTransition

/**
 * One block rising into place: up `y` px (6) on the spring with a 180 ms fade, out in 120 ms. Reduced motion: the
 * fade alone. `delay` holds the arrival (a beat after its frame, say).
 */
export function rise(reduced: boolean | null | undefined, { y = stagger.rise, delay = 0 }: { y?: number; delay?: number } = {}): { initial: V; animate: V; exit: V; transition: Transition } {
  return {
    initial: reduced ? { opacity: 0 } : { opacity: 0, y },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, transition: fade.out },
    transition: enter(delay)
  }
}

/** The same rise as a static object (MotionConfig drops the travel with reduced motion). Mount and exit. */
export const riseIn: Pick<MotionProps, 'initial' | 'animate' | 'exit' | 'transition'> = {
  initial: { opacity: 0, y: stagger.rise },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -stagger.rise / 2, transition: fade.out },
  transition: enter()
}

/**
 * A container whose children rise in one after another; the stagger stops growing at stagger.cap. (motion v14 calls
 * delayChildren per child with its index in document order.)
 */
export const staggerList: Variants = {
  hidden: {},
  shown: { transition: { delayChildren: (i: number) => 0.02 + Math.min(i, stagger.cap - 1) * stagger.each } }
}

/** A child of staggerList. */
export const riseItem: Variants = {
  hidden: { opacity: 0, y: stagger.rise },
  shown: { opacity: 1, y: 0, transition: enter() }
}

/** The delay of the i-th item of a group that staggers by hand (custom index), capped like staggerList. */
export const staggerDelay = (i: number): number => Math.min(Math.max(0, i), stagger.cap) * stagger.each

/**
 * A line of text replaced in place (the pill's lines, the Mini title): the old one leaves up in 120 ms, the new one
 * arrives from below a beat later, so the two are never both readable. Reduced motion: a crossfade.
 */
export const textSwap = {
  initial: { opacity: 0, y: 7 },
  animate: { opacity: 1, y: 0, transition: enter(beat) },
  exit: { opacity: 0, y: -7, transition: fade.out }
} as const satisfies Pick<MotionProps, 'initial' | 'animate' | 'exit'>

/**
 * A stroke that draws in (the passed tick): pathLength over 240 ms on ease.out, `delay` after its circle. pathLength
 * is not a transform, so MotionConfig would still play it: reduced motion fades the stroke in instead.
 */
export function draw(reduced: boolean | null | undefined, delay = beat): Pick<MotionProps, 'initial' | 'animate' | 'transition'> {
  return reduced
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: fadeIn(delay) }
    : { initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration: duration.slow, ease: ease.out, delay, opacity: { ...fade.instant, delay } } }
}

/**
 * The off-track dot's two calm beats (no shake, no hue): scale 1 → 1.35 twice over a second. A scale, so
 * MotionConfig drops it with Reduce Motion and the dot just changes.
 */
export const twoBeats = { keyframes: [1, 1.35, 1, 1.35, 1], transition: { duration: 1, ease: ease.inOut } } as const

/** A glyph that pops into place (the passed circle, a status ring): from .6 on the spring, never from 0. */
export function pop(reduced: boolean | null | undefined, from = 0.6): Pick<MotionProps, 'initial' | 'animate' | 'transition'> {
  return { initial: reduced ? { opacity: 0 } : { opacity: 0, scale: from }, animate: { opacity: 1, scale: 1 }, transition: enter() }
}
