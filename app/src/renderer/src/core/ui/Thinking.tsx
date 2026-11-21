/**
 * Core (polish, UI-POLISH-SPEC 6): waiting, without looking dead and without a show.
 *
 *   ThinkingDots  three small dots that breathe in turn (opacity only, styles.css .mg-thinking-dot). For a line of text
 *                 that is waiting on the engine ("Running the checks for this step"). A button that is busy keeps the
 *                 core Spinner (CLAUDE.md "never look dead"); a check row keeps its spinner. They appear after
 *                 150 ms, so a fast answer never flashes them. Reduced motion: the three pulse together, slower, never frozen.
 *   Skeleton      a block in the skeleton fill that pulses (.mg-skeleton, opacity 1 to .4 over 2 s) while its content loads. No shimmer sweep:
 *                 a sweep is a moving gradient, and the brand has none.
 *
 * Neutral only: the dots take the text color around them (currentColor), never a hue.
 */
import type { CSSProperties, ReactNode } from 'react'
import { fill, radius2 } from '../theme'

export function ThinkingDots({
  size = 4,
  gap = 3,
  label = 'Working'
}: {
  size?: number
  gap?: number
  /** What a screen reader hears; null = decorative (the words beside the dots already say it), hidden from it. */
  label?: string | null
}): ReactNode {
  const a11y = label === null ? { 'aria-hidden': true } : { role: 'img', 'aria-label': label }
  return (
    <span {...a11y} data-thinking className="mg-thinking inline-flex shrink-0 items-center align-middle" style={{ gap }}>
      {[0, 1, 2].map((i) => (
        <span key={i} className="mg-thinking-dot block shrink-0" style={{ width: size, height: size, borderRadius: radius2.round, background: 'currentColor' }} />
      ))}
    </span>
  )
}

export function Skeleton({ width = '100%', height = 12, radius = radius2.keycap, style }: { width?: number | string; height?: number | string; radius?: number; style?: CSSProperties }): ReactNode {
  return <span aria-hidden data-skeleton className="mg-skeleton block" style={{ width, height, borderRadius: radius, background: fill.skeleton, ...style }} />
}
