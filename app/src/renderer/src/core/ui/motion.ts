/**
 * Core (polish, UI-POLISH-SPEC.md): the shared press and enter motions, so every control dips the same way and every
 * list arrives the same way. Transform and opacity only, on the house spring. MotionConfig reducedMotion="user"
 * (main.tsx) turns the transforms off for reduced motion and keeps the fades.
 *
 *   <motion.button {...pressMotion(disabled)} className="mg-press ...">        scale .97 on press, spring back
 *   <motion.ul variants={staggerList} initial="hidden" animate="shown">       children: <motion.li variants={riseItem}>
 *   <motion.div {...riseIn}>                                                  one block rising into place
 */
import type { MotionProps, Variants } from 'motion/react'
import { duration, press, spring, stagger } from '../theme'

/** whileTap scale on the house spring. `large` for big tiles (.96). No dip at all when disabled. */
export function pressMotion(disabled?: boolean, large?: boolean): Pick<MotionProps, 'whileTap' | 'transition'> {
  return {
    whileTap: disabled ? undefined : { scale: large ? press.scaleLarge : press.scale },
    transition: press.transition
  }
}

/**
 * A container whose children rise in one after another. Polish: the stagger stops growing at stagger.cap, so child 9
 * and on arrive with child 8 and a long list never makes the learner wait. (motion v14 calls delayChildren per child
 * with its index in document order.)
 */
export const staggerList: Variants = {
  hidden: {},
  shown: { transition: { delayChildren: (i: number) => 0.02 + Math.min(i, stagger.cap - 1) * stagger.each } }
}

/** A child of staggerList. */
export const riseItem: Variants = {
  hidden: { opacity: 0, y: stagger.rise },
  shown: { opacity: 1, y: 0, transition: { ...spring, opacity: { duration: duration.base } } }
}

/** One block rising into place on mount (and fading out on exit inside AnimatePresence). */
export const riseIn: Pick<MotionProps, 'initial' | 'animate' | 'exit' | 'transition'> = {
  initial: { opacity: 0, y: stagger.rise },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -stagger.rise / 2, transition: { duration: duration.fast } },
  transition: { ...spring, opacity: { duration: duration.base } }
}
