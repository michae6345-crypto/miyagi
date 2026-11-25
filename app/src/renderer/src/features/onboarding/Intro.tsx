/**
 * Feature: onboarding. The branded intro: about 2.5 s on the first launch, before guided setup.
 *
 *   0.00 s  the colored bonsai (full cut, brand files) grows in: it scales up from its pot and a cover the window's
 *           color slides up off it, so the pot shows first, then the trunk, then the pads (transform only)
 *   0.95 s  the "miyagi" wordmark (brand file, never retyped) fades up
 *   1.30 s  one calm line
 *   2.50 s  it hands over to setup: the tree travels into the setup header (shared layoutId, a transform)
 *
 * Any key or click skips it. Reduced motion: one static frame (nothing moves), held a little shorter.
 * `hold` (the stage's ?onb=intro) keeps the last frame up until a key or click.
 */
import { useEffect, useRef, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { color, font, spring, type2, v4c } from '../../core/theme'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { EASE_OUT } from './parts'

export const INTRO_MS = 2500
const INTRO_REDUCED_MS = 1600
export const TREE = 148
/** The shared layoutId: the intro's tree becomes the setup header's tree. */
export const MARK_ID = 'onb-mark'

export function Intro({ onDone, hold }: { onDone: () => void; hold?: boolean }): ReactNode {
  const reduce = useReducedMotion() ?? false
  const done = useRef(false)
  const finish = useRef(onDone)
  finish.current = onDone

  useEffect(() => {
    const end = (): void => {
      if (done.current) return
      done.current = true
      finish.current()
    }
    const onKey = (e: KeyboardEvent): void => {
      // Modifier presses alone (Cmd-Tab away, a screenshot shortcut) aren't a skip.
      if (['Meta', 'Control', 'Alt', 'Shift', 'CapsLock'].includes(e.key)) return
      e.preventDefault()
      end()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', end)
    const t = hold ? undefined : setTimeout(end, reduce ? INTRO_REDUCED_MS : INTRO_MS)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', end)
      clearTimeout(t)
    }
  }, [hold, reduce])

  return (
    <motion.div
      data-onb-view="intro"
      role="dialog"
      aria-label="Welcome to miyagi"
      className="absolute inset-0 flex cursor-default flex-col items-center justify-center"
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2, ease: EASE_OUT } }}
    >
      {/* The window's top strip still drags it (the traffic lights live there). */}
      <div data-drag className="absolute left-0 right-0 top-0 h-[28px]" />
      <motion.div
        layoutId={MARK_ID}
        className="relative overflow-hidden"
        style={{ width: TREE, height: TREE, originY: 1 }}
        initial={reduce ? false : { opacity: 0, scale: 0.86 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ scale: spring, opacity: { duration: 0.4, ease: EASE_OUT }, layout: spring }}
      >
        <MiyagiMark size={TREE} />
        {/* The grow: a cover in the window's color slides up and off the tree (pot, trunk, then pads). */}
        {!reduce && (
          <motion.span
            aria-hidden
            className="absolute inset-0 block"
            style={{ background: v4c.page }}
            initial={{ y: '0%' }}
            animate={{ y: '-101%' }}
            transition={{ duration: 1.05, delay: 0.08, ease: EASE_OUT }}
          />
        )}
      </motion.div>
      <motion.div
        className="mt-[28px]"
        initial={reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ y: { ...spring, delay: 0.95 }, opacity: { duration: 0.3, delay: 0.95, ease: EASE_OUT } }}
      >
        <MiyagiWordmark height={44} className="block h-[44px] w-auto" />
      </motion.div>
      <motion.p
        className="m-0 mt-[20px]"
        style={{ fontFamily: font.ui, fontSize: type2.lg, lineHeight: '24px', color: color.label }}
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ y: { ...spring, delay: 1.3 }, opacity: { duration: 0.3, delay: 1.3, ease: EASE_OUT } }}
      >
        Learn by doing, in the apps you already use.
      </motion.p>
      <motion.span
        aria-hidden
        className="absolute bottom-[28px]"
        style={{ fontSize: type2.xs, color: color.faint }}
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.7 }}
      >
        Press any key to skip
      </motion.span>
    </motion.div>
  )
}
