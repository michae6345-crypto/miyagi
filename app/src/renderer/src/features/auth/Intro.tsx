/**
 * Feature: auth. The first-run intro: the bonsai grows up out of its pot in the middle of the window, the wordmark
 * settles under it, then the tree moves up into the login's header (shared layoutId) and the login fades in.
 *
 * PLACEHOLDER until the intro lane's animated miyagi intro (features/onboarding) merges; then this file reuses it.
 * Click or any key skips. Reduced motion: no growth, a short fade.
 */
import { motion, useReducedMotion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { color, spring, type2 } from '../../core/theme'
import { MiyagiMark, MiyagiWordmark } from '../../core/ui/Mark'
import { endIntro } from './store'

/** How long the intro holds before the login takes over (ms). */
const HOLD_MS = 2300
const HOLD_REDUCED_MS = 700

export const MARK_ID = 'auth-mark'

export function Intro(): ReactNode {
  const reduced = useReducedMotion()

  useEffect(() => {
    const t = setTimeout(endIntro, reduced ? HOLD_REDUCED_MS : HOLD_MS)
    const skip = (): void => endIntro()
    addEventListener('keydown', skip)
    return () => {
      clearTimeout(t)
      removeEventListener('keydown', skip)
    }
  }, [reduced])

  return (
    <motion.div
      data-auth-intro
      className="absolute inset-0 flex cursor-default flex-col items-center justify-center gap-[20px]"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, transition: { duration: 0.18 } }}
      onClick={endIntro}
      aria-label={`Welcome to miyagi. Click to continue.`}
      role="button"
      tabIndex={0}
    >
      <motion.div layoutId={MARK_ID} transition={spring}>
        {/* The tree grows from the pot up: a clip that opens from the bottom, with a small rise. */}
        <motion.div
          initial={reduced ? { opacity: 0 } : { clipPath: 'inset(100% 0% 0% 0%)', y: 10, scale: 0.94 }}
          animate={reduced ? { opacity: 1 } : { clipPath: 'inset(0% 0% 0% 0%)', y: 0, scale: 1 }}
          transition={reduced ? { duration: 0.2 } : { clipPath: { duration: 1.1, ease: [0.22, 1, 0.36, 1] }, y: spring, scale: spring }}
        >
          <MiyagiMark size={168} level="full" />
        </motion.div>
      </motion.div>
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ ...spring, delay: reduced ? 0 : 0.9 }} className="flex flex-col items-center gap-[10px]">
        {/* The preflight's img {height:auto} beats the height attribute, so the class pins it. */}
        <MiyagiWordmark height={30} className="h-[30px] w-auto" />
        <span style={{ fontSize: type2.sm, color: color.label }}>Learn anything by doing.</span>
      </motion.div>
    </motion.div>
  )
}
