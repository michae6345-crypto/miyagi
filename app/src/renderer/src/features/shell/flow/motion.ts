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
import { beat, enter, fade, spring } from '../../../core/ui/motion'
export { MARK_ID } from '../../onboarding/Intro'

export const STRIP_CURRENT = 'flow-strip-current'

/** How long the arrival (flow → home) runs before the flow layer is gone for good (ms). */
export const ARRIVE_MS = 900

/** A phase's view leaving (login, setup, ready): a quick fade and a small lift. */
export const leave: Transition = fade.out
/** A phase's view arriving after the bonsai has started its glide (three beats). */
export const arriveDelay = 3 * beat

/** The strip fading in under the window's top edge once the intro is over. */
export const stripIn: Transition = { y: spring, opacity: fade.slow }

/**
 * The hand-off to home, in two beats so two screens are never drawn over each other:
 *   1. screenOut  the flow's screen (strip, You're ready, its rows, Start) fades out on its own (0 to 120 ms), the
 *                 layer's plain paper stays;
 *   2. layerOut   then the paper fades (from 120 ms, two beats) while the sidebar slides in over it and Home rises
 *                 under it.
 */
export const screenOut: Transition = fade.out
export const layerOut: Transition = { ...fade.slow, delay: 2 * beat }
/** Setup again (reopenFlow): the flow's paper fading in over home, its screen arriving a beat later. */
export const layerIn: Transition = fade.slow
/**
 * The sidebar sliding in from the window's left edge (its own width, on the house spring). Its fade (reduced motion
 * only: there it fades instead of sliding) waits until screenOut is over and runs with the paper's own fade (layerOut),
 * so the sidebar is never drawn beside a You're ready that is still fading out.
 */
export const sidebarIn: Transition = { x: { ...spring, delay: beat }, opacity: { ...fade.slow, delay: 2 * beat } }
/** Home's content arriving once the flow's screen is gone (its cards then rise one after another: library/motion.tsx). */
export const homeIn: Transition = enter(2 * beat, fade.slow)
/** The sidebar's wordmark writing in once the bonsai has landed beside it (flow/SidebarBrand.tsx). */
export const wordIn: Transition = enter(5 * beat, fade.slow)
