/**
 * The Voice tile while Miyagi speaks: three bars in the glyph's place, each looping on its own rhythm.
 * Reads only `on` / `speaking` from the voice store: voice uses the computer's own voice, which can't be metered,
 * so the bars animate on their own while `speaking`. Transform only (scaleY from the bottom), no glow.
 * Reduced motion: the rest shape, still.
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { useVoice } from '../voice/store'

/** Rest shape and loop of each bar, as a fraction of the glyph height. */
const BARS = [
  { rest: 0.45, loop: [0.35, 0.95, 0.5, 0.8, 0.35], delay: 0 },
  { rest: 0.8, loop: [0.6, 0.4, 1, 0.55, 0.6], delay: 0.12 },
  { rest: 0.6, loop: [0.45, 0.85, 0.3, 0.9, 0.45], delay: 0.24 }
]

/** Voice tile state, read from the voice feature's store (on, speaking). */
export function useVoiceTile(): { on: boolean; speaking: boolean } {
  const on = useVoice((v) => v.on)
  const speaking = useVoice((v) => v.on && v.speaking)
  return { on, speaking }
}

export function Equalizer({ tone, size = 19 }: { tone: string; size?: number }): ReactNode {
  const still = useReducedMotion()
  const bar = size <= 16 ? 2.5 : 3
  return (
    <span className="flex items-end justify-center" style={{ width: size, height: size, gap: bar }} data-equalizer="">
      {BARS.map((b, i) => (
        <motion.i
          key={i}
          className="block h-full rounded-full"
          style={{ width: bar, background: tone, originY: 1 }}
          initial={{ scaleY: b.rest }}
          animate={{ scaleY: still ? b.rest : b.loop }}
          transition={still ? { duration: 0 } : { repeat: Infinity, duration: 0.9, delay: b.delay, ease: 'easeInOut' }}
        />
      ))}
    </span>
  )
}
