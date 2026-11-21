/**
 * Feature: onboarding. Small pieces the setup views share: the "N of M ready" count, the footer with the one primary,
 * the launcher hint (its keycap from bridge.platform.keys, never typed) and the enter motion every view uses.
 *
 * Motion (UI-POLISH-SPEC 5, kept local until core/ui/motion.ts lands): a 6 px rise on the house spring with a 180 ms
 * fade, 35 ms stagger, the first 8 children only. MotionConfig reducedMotion="user" (main.tsx) drops the rise and keeps
 * the fade. Transform and opacity only.
 */
import type { ReactNode } from 'react'
import type { Transition, Variants } from 'motion/react'
import { color, copy, fill, spring, type2 } from '../../core/theme'
import { PrimaryButton } from '../../core/ui/buttons'
import { Keycap } from '../../core/ui/Keycap'
import type { Summary } from './rows'
import { startLearning } from './store'

const FADE: Transition = { duration: 0.18, ease: [0.23, 1, 0.32, 1] }
export const EASE_OUT = [0.23, 1, 0.32, 1] as const

/** A parent that staggers its `rise` children (35 ms apart, the first 8 only). */
export function stagger(delay = 0): Variants {
  return { hidden: {}, shown: { transition: { delayChildren: delay, staggerChildren: 0.035 } } }
}

/** One child that rises 6 px and fades in (a `stagger` parent sets when). */
export const rise: Variants = {
  hidden: { opacity: 0, y: 6 },
  shown: { opacity: 1, y: 0, transition: { y: spring, opacity: FADE } }
}

export function ReadyCount({ sum }: { sum: Summary }): ReactNode {
  return (
    <span data-onb-count className="tabular-nums" style={{ fontSize: type2.sm, color: color.label }}>
      {sum.ready} of {sum.total} ready
    </span>
  )
}

/** The bottom bar: what's left (or `left`) and the one primary. */
/** `onStart`: what the primary does (the setup window's startLearning by default; the one-window flow hands over to home). */
/** `always`: the primary works whatever is left (setup again's Done, which only goes back to home). */
export function Footer({ sum, left, border = true, label = 'Start learning', onStart = startLearning, always }: { sum: Summary; left?: ReactNode; border?: boolean; label?: string; onStart?: () => void; always?: boolean }): ReactNode {
  return (
    <div className="flex items-center justify-between gap-[24px] pt-[24px]" style={{ borderTop: border ? `1px solid ${fill.hairline}` : undefined }}>
      {left ?? (
        <span data-onb-hint style={{ fontSize: type2.sm, lineHeight: '20px', color: color.label }}>
          {sum.hint}
        </span>
      )}
      <span data-onb-primary>
        <PrimaryButton size="lg" label={label} disabled={!always && !sum.canStart} onClick={onStart} />
      </span>
    </div>
  )
}

export function LauncherHint({ lead }: { lead?: string }): ReactNode {
  return (
    <div className="flex items-center gap-[8px]">
      {lead && <span style={{ fontSize: type2.sm, color: color.label }}>{lead}</span>}
      <Keycap k="launcher" />
      <span style={{ fontSize: type2.sm, color: color.label }}>{copy.launcherPlaceholder}</span>
    </div>
  )
}
