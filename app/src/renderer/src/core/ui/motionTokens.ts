/**
 * Core: the motion TOKENS, the numbers every animation uses (docs/MOTION.md). Plain values with no DOM types, so the
 * main process (which imports core/theme) can compile them too. Feature code imports them from core/ui/motion, which
 * re-exports them next to the helpers; core/theme re-exports them for older imports.
 */
import type { Transition } from 'motion/react'

/** The house spring: everything that moves. ~90% there in 0.13 s, settled in ~0.35 s, a hair of overshoot. */
export const spring = { type: 'spring', stiffness: 420, damping: 34, mass: 0.9 } as const satisfies Transition
/** Leaving and collapsing: the same stiffness, critically damped, so a thing that goes away never bounces. */
export const springOut = { type: 'spring', stiffness: 420, damping: 38, mass: 0.9 } as const satisfies Transition

/** Tween lengths (seconds) for fades and tints. Never for movement. */
export const duration = { instant: 0.08, fast: 0.12, base: 0.18, slow: 0.24 } as const
/** ease.out: enter fast, settle slow (never ease-in on an enter). inOut: only for a there-and-back flash. */
export const ease = { out: [0.23, 1, 0.32, 1], inOut: [0.77, 0, 0.175, 1] } as const

/** One step of a sequence (seconds). Two beats is the most anything waits for something else on screen. */
export const beat = 0.06

/** Fades. A leaving thing is always quicker than an arriving one, so two states never sit on top of each other. */
export const fade = {
  in: { duration: duration.base, ease: ease.out },
  out: { duration: duration.fast, ease: ease.out },
  /** A big surface (a panel, a window's layer) arriving: a touch longer so its shadow doesn't pop. */
  slow: { duration: duration.slow, ease: ease.out },
  /** Tint layers and hover fills. */
  tint: { duration: duration.fast, ease: ease.out },
  /** Anything that must just be gone now (a layer swapped out under a morph). */
  instant: { duration: duration.instant, ease: ease.out }
} as const satisfies Record<string, Transition>

/** Press: scale .97 on the house spring and back. Big tiles .96; never below .95. */
export const press = { scale: 0.97, scaleLarge: 0.96, transition: spring } as const

/** Lists: each child rises 6 px, 35 ms apart; children past the 8th arrive with the 8th. */
export const stagger = { each: 0.035, cap: 8, rise: 6 } as const

/** No animation at all (reduced motion for things that would travel or resize). */
export const instant = { duration: 0 } as const satisfies Transition

