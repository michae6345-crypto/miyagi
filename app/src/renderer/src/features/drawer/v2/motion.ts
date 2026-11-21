/**
 * Feature: drawer (v2, A1). The lesson panel's enter motion (UI-POLISH-SPEC sections 5 and 9): a new state (Not yet,
 * Hint, Passed) rises 6 px on the house spring with a 180 ms fade; it leaves in 120 ms. Reduced motion keeps the fade
 * and drops the rise (Apple: replace x/y/z transitions with fades). The step slide and the panel's own in/out live in
 * LessonPanel.tsx. The numbers are the core polish tokens (core/theme duration and stagger, as core/ui/motion riseIn).
 */
import type { TargetAndTransition, Transition } from 'motion/react'
import { duration, spring, stagger } from '../../../core/theme'

export const FADE_IN = duration.base
export const FADE_OUT = duration.fast

type V = TargetAndTransition

export function rise(reduced: boolean | null): { initial: V; animate: V; exit: V; transition: Transition } {
  return {
    initial: reduced ? { opacity: 0 } : { opacity: 0, y: stagger.rise },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, transition: { duration: FADE_OUT } },
    transition: { ...spring, opacity: { duration: FADE_IN } }
  }
}
