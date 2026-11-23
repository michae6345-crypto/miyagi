/**
 * Feature: library. Home's motion, on UI-POLISH-SPEC section 5 (enter, stagger) and section 3 (hover, press), built on
 * the shared helpers in core/ui/motion (docs/MOTION.md).
 *
 *   rise      enter: up 6 px on the house spring, fade 180 ms. Exit 120 ms. Never from scale 0.
 *   stagger   35 ms per child, only the first 8 children are staggered (the rest arrive with the 8th).
 *   Press     a button with a hover tint layer (opacity only) and a 0.97 dip on the house spring.
 * Reduced motion: main.tsx wraps the app in MotionConfig reducedMotion="user", which drops the transforms and keeps
 * the fades (Apple: replace movement with fades). Everything here animates transform and opacity only.
 */
import { motion, useReducedMotion, type HTMLMotionProps, type Variants } from 'motion/react'
import { forwardRef, type CSSProperties, type ReactNode } from 'react'
import { color, fill, radius2 } from '../../core/theme'
import { enter, fade, press, spring, stagger, staggerDelay } from '../../core/ui/motion'

export const rise: Variants = {
  hidden: { opacity: 0, y: stagger.rise },
  shown: (i: number = 0) => ({ opacity: 1, y: 0, transition: enter(staggerDelay(i)) }),
  gone: { opacity: 0, transition: fade.out }
}

/** A block that rises in as the i-th of its group (i caps at 8). */
export function Rise({ i = 0, children, className = '', style, as = 'div', ...rest }: { i?: number; children: ReactNode; className?: string; style?: CSSProperties; as?: 'div' | 'section' | 'li' } & Record<`data-${string}`, string | undefined>): ReactNode {
  // Content never waits on an animation: with reduced motion the block starts shown (no hidden frame to get stuck in).
  const reduce = useReducedMotion()
  const M = as === 'section' ? motion.section : as === 'li' ? motion.li : motion.div
  return (
    <M custom={i} variants={rise} initial={reduce ? false : 'hidden'} animate="shown" exit="gone" className={className} style={style} {...rest}>
      {children}
    </M>
  )
}

/**
 * The white focus ring for the core buttons (PrimaryButton, QuietButton) until core gives them one (agents/library.md,
 * Core request 0(a)): without it Chromium draws its own orange ring. Same ring as Press: 2 px solid, offset 2, at once.
 * The span is display: contents, so it never changes the layout around the button.
 */
export function Ring({ children }: { children: ReactNode }): ReactNode {
  return (
    <span
      className="contents [&>button:focus-visible]:outline-2 [&>button:focus-visible]:outline-offset-2 [&>button:focus-visible]:outline-solid [&>button:focus-visible]:outline-[color:var(--home-ring)]"
      style={{ '--home-ring': color.text } as CSSProperties}
    >
      {children}
    </span>
  )
}

/**
 * A card that lifts 2 px on hover and settles back on the house spring (transform only). Reduced motion: no lift.
 * Use it on cards that are not themselves buttons (a Press is already pressable).
 */
export function Lift({ children, className = '', style }: { children: ReactNode; className?: string; style?: CSSProperties }): ReactNode {
  const reduce = useReducedMotion()
  return (
    <motion.div whileHover={reduce ? undefined : { y: -2 }} transition={spring} className={className} style={style}>
      {children}
    </motion.div>
  )
}

/**
 * A card born in the page's stagger: it rises in as the i-th of its group AND lifts on hover. One wrapper so every
 * page's cards enter and respond the same way (Home, Progress, Account).
 */
export function Tile({ i = 0, children, className = '', style, ...rest }: { i?: number; children: ReactNode; className?: string; style?: CSSProperties } & Record<`data-${string}`, string | undefined>): ReactNode {
  return (
    <Rise i={i} className={className} style={style} {...rest}>
      <Lift className="h-full">{children}</Lift>
    </Rise>
  )
}

/**
 * A skeleton card: an opacity pulse (styles.css .mg-skeleton: no sweep and no travel, so it is already reduced-motion
 * safe; the pulse is opacity only and the page waits on it, never on a transform). `lines` placeholder lines inside.
 */
export function SkeletonCard({ h = 120, lines = 0 }: { h?: number; lines?: number }): ReactNode {
  return (
    <div aria-hidden className="mg-skeleton flex flex-col" style={{ height: h, borderRadius: radius2.group, background: fill.skeleton, padding: lines ? 20 : 0, gap: 12 }}>
      {Array.from({ length: lines }, (_, k) => (
        <div key={k} style={{ height: 10, width: `${80 - k * 18}%`, borderRadius: radius2.round, background: fill.skeleton }} />
      ))}
    </div>
  )
}

/** The hover / press tint: a layer over the control that only changes opacity. */
const tint: Variants = { rest: { opacity: 0, transition: fade.tint }, hover: { opacity: 1, transition: fade.tint }, press: { opacity: 1, transition: fade.press } }

type PressProps = Omit<HTMLMotionProps<'button'>, 'children'> & { children: ReactNode; /** big tiles dip a little more (press.scaleLarge, .96) */ large?: boolean; tintColor?: string }

/**
 * A neutral pressable surface (cards, rows): hover lightens it by white .06, press dips it on the spring. Focus draws
 * the white ring at once (focus-visible only, no transition, no blur).
 */
export const Press = forwardRef<HTMLButtonElement, PressProps>(function Press({ children, large, tintColor = fill.tile, disabled, className = '', style, ...rest }, ref) {
  return (
    <motion.button
      ref={ref}
      type="button"
      disabled={disabled}
      initial="rest"
      animate="rest"
      whileHover={disabled ? undefined : 'hover'}
      whileTap={disabled ? undefined : 'press'}
      variants={{ rest: { scale: 1, transition: spring }, hover: { scale: 1 }, press: { scale: large ? press.scaleLarge : press.scale, transition: spring } }}
      className={`relative cursor-pointer overflow-hidden text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid disabled:cursor-default ${className}`}
      style={{ outlineColor: color.text, ...style }}
      {...rest}
    >
      <motion.span aria-hidden variants={tint} className="pointer-events-none absolute inset-0" style={{ background: tintColor, borderRadius: 'inherit' }} />
      {children}
    </motion.button>
  )
})
