/**
 * Never look dead (Michael's P0): while the engine thinks about the action this tile sent, the tile's glyph
 * becomes the core Spinner.
 *
 * Rule (CLAUDE.md "Keys and actions"): `useThinking() && usePressed().kind === kind`, plus one guard: the
 * thinking must have started around the press. Show me is answered by a video.seek, which does not clear
 * `usePressed`, so without the guard a later coach run (also `status thinking`) would spin the Show me tile
 * minutes after it was pressed. (Back and Voice never set `usePressed`: core.)
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { create } from 'zustand'
import { useLesson, useThinking } from '../../core/lesson'
import { usePressed, type ActionKind } from '../../core/shortcuts'
import { Spinner } from '../../core/ui/atoms'
import { GlassSpinner } from '../../core/ui/glass'
import { fade } from '../../core/ui/motion'

/** A press owns a thinking spell that starts at most this long after it (2–5 s model calls; allows one queued call). */
const OWN_MS = 6000

/** When the engine last went into `thinking` (0 = not thinking). */
const useSince = create<{ at: number }>(() => ({ at: 0 }))
useLesson.subscribe((s, prev) => {
  const now = s.engineState === 'thinking'
  if (now === (prev.engineState === 'thinking')) return
  useSince.setState({ at: now ? Date.now() : 0 })
})

/** True while the engine is thinking about the action `kind` sent. */
export function useBusy(kind: ActionKind): boolean {
  const thinking = useThinking()
  const since = useSince((s) => s.at)
  const pressedAt = usePressed((p) => (p.kind === kind ? p.at : 0))
  // Pressed while already thinking (since < pressedAt) also counts: the press is waiting on that call.
  return thinking && pressedAt > 0 && since > 0 && since - pressedAt < OWN_MS
}

/**
 * The tile's glyph, or a spinner of the same size while busy: `tone` = the glyph's color, `track` = the ring behind
 * the arc. `glass`: the GlassSpinner (colors via CSS, so theme.glass variables resolve) for neutral / primary tiles;
 * otherwise the core Spinner (ink on a pastel tile).
 */
export function Glyph({ kind, tone, track, glass, size = 19, children }: { kind: ActionKind; tone: string; track?: string; glass?: boolean; size?: number; children: ReactNode }): ReactNode {
  const busy = useBusy(kind)
  return (
    <motion.span
      key={busy ? 'busy' : 'idle'}
      className="flex items-center justify-center"
      style={{ width: size, height: size }}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={fade.tint}
      {...(busy ? { role: 'status', 'aria-label': 'Working', 'data-busy': '' } : {})}
    >
      {busy ? glass ? <GlassSpinner size={size - 2} c={tone} track={track} /> : <Spinner size={size - 2} c={tone} track={track} /> : children}
    </motion.span>
  )
}
