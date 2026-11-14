/**
 * The Voice tile while voice audio plays: three bars in the glyph's place.
 * Reads the voice store: `speaking` drives it. Each bar loops on its own rhythm inside an envelope that follows
 * `level` (0..1 while speaking, the voice player's meter), so loud speech fills the tile and a pause sinks it.
 * When `level` can't be measured (undefined) the envelope is full and the bars just loop.
 * Transform only (scaleY from the bottom), no glow. Reduced motion: the rest shape, scaled by the envelope.
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

/** Voice tile state, read from the voice feature's store (on, speaking, optional level). */
export function useVoiceTile(): { on: boolean; speaking: boolean } {
  const on = useVoice((v) => v.on)
  const speaking = useVoice((v) => v.on && v.speaking)
  return { on, speaking }
}

/** Envelope height for a level: a floor so a quiet clip still reads as sound, full at about 0.5. */
const envelope = (level?: number): number => (level === undefined ? 1 : Math.max(0.3, Math.min(1, 0.35 + 1.3 * level)))

export function Equalizer({ tone, size = 19 }: { tone: string; size?: number }): ReactNode {
  const env = useVoice((v) => envelope(v.level))
  const still = useReducedMotion()
  const bar = size <= 16 ? 2.5 : 3
  return (
    <span className="flex items-end justify-center" style={{ width: size, height: size, gap: bar }} data-equalizer="">
      {BARS.map((b, i) => (
        <motion.span key={i} className="flex h-full items-end" style={{ originY: 1 }} animate={{ scaleY: env }} transition={{ duration: 0.08, ease: 'linear' }}>
          <motion.i
            className="block h-full rounded-full"
            style={{ width: bar, background: tone, originY: 1 }}
            initial={{ scaleY: b.rest }}
            animate={{ scaleY: still ? b.rest : b.loop }}
            transition={still ? { duration: 0 } : { repeat: Infinity, duration: 0.9, delay: b.delay, ease: 'easeInOut' }}
          />
        </motion.span>
      ))}
    </span>
  )
}
