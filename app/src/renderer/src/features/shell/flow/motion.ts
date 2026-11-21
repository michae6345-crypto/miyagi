/**
 * Feature: shell / flow. The first run's motion, in one place (the spec is app/agents/onboarding.md, "One window:
 * motion spec"). Everything that moves uses the house spring (core/theme `spring`); fades are short tweens on
 * `ease.out`. Transform and opacity only. Reduced motion (MotionConfig reducedMotion="user" in main.tsx) drops every
 * transform and layout move and keeps the fades, so each hand-off becomes a crossfade.
 *
 * Shared elements (motion layoutId, one LayoutGroup around the shell):
 *   MARK_ID        the bonsai: intro (148) → login header (56) → the strip's step indicator (18) → the sidebar logo (20)
 *   STRIP_CURRENT  the strip's current-step pill, sliding from one step to the next
 */
import type { Transition } from 'motion/react'
import { duration, ease, spring } from '../../../core/theme'
export { MARK_ID } from '../../onboarding/Intro'

export const STRIP_CURRENT = 'flow-strip-current'

/** How long the arrival (flow → home) runs before the flow layer is gone for good (ms). */
export const ARRIVE_MS = 900

/** A phase's view leaving (login, setup, ready): a quick fade and a small lift. */
export const leave: Transition = { duration: duration.fast, ease: ease.out }
/** A phase's view arriving after the bonsai has started its glide. */
export const arriveDelay = 0.16

/** The strip fading in under the window's top edge once the intro is over. */
export const stripIn: Transition = { y: spring, opacity: { duration: duration.slow, ease: ease.out } }

/** The flow layer handing the window to home: its paper fades while the sidebar slides in over it. */
export const layerOut: Transition = { duration: 0.22, ease: ease.out }
/** The sidebar sliding in from the window's left edge (its own width, on the house spring). */
export const sidebarIn: Transition = { x: { ...spring, delay: 0.04 }, opacity: { duration: duration.base, ease: ease.out } }
/** Home's content arriving a beat after the sidebar (its cards then rise one after another: library/motion.tsx). */
export const homeIn: Transition = { opacity: { duration: duration.slow, delay: 0.12, ease: ease.out }, y: { ...spring, delay: 0.12 } }
