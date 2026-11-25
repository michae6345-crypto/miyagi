/**
 * Feature: onboarding. Small pieces the setup views share: the launcher hint (its keycap from bridge.platform.keys,
 * never typed) and the enter motion every view uses.
 *
 * Motion (UI-POLISH-SPEC 5, numbers from core/ui/motion, docs/MOTION.md): a 6 px rise on the house spring with a 180 ms
 * fade, 35 ms stagger, the first 8 children only. MotionConfig reducedMotion="user" (main.tsx) drops the rise and keeps
 * the fade. Transform and opacity only.
 */
import type { ReactNode } from 'react'
import type { Transition, Variants } from 'motion/react'
import { color, copy, spring, type2 } from '../../core/theme'
import { Keycap } from '../../core/ui/Keycap'
import { ease, fade, stagger as motionStagger } from '../../core/ui/motion'

const FADE: Transition = fade.in
/** The house ease-out (core/ui/motion ease.out), kept under the name the onboarding files import. */
export const EASE_OUT = ease.out

/** A parent that staggers its `rise` children (35 ms apart, the first 8 only). */
export function stagger(delay = 0): Variants {
  return { hidden: {}, shown: { transition: { delayChildren: delay, staggerChildren: motionStagger.each } } }
}

/** One child that rises 6 px and fades in (a `stagger` parent sets when). */
export const rise: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { y: spring, opacity: FADE } }
}

export function LauncherHint({ lead }: { lead?: string }): ReactNode {
  return (
    <div className="flex items-center gap-[8px] whitespace-nowrap">
      {lead && <span style={{ fontSize: type2.sm, color: color.label }}>{lead}</span>}
      <Keycap k="launcher" />
      <span style={{ fontSize: type2.sm, color: color.label }}>{copy.launcherPlaceholder}</span>
    </div>
  )
}
