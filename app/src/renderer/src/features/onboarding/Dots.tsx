/**
 * Feature: onboarding. Setup progress as small dots (Apple's setup assistant): one dot per step, the current one a
 * little longer and white, a step done is a green dot (green only means done), a step ahead is faint. No labels on
 * screen (they are named for screen readers), nothing to click. Width and color are the only things that move.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { color, fill, radius2, spring, status as tone } from '../../core/theme'

export type DotState = 'current' | 'done' | 'next'
export type DotItem = { id: string; label: string; state: DotState }

export function Dots({ items, label = 'Setup progress' }: { items: readonly DotItem[]; label?: string }): ReactNode {
  const at = items.findIndex((i) => i.state === 'current')
  return (
    <ol aria-label={label} data-onb-dots={at >= 0 ? items[at].id : undefined} className="m-0 flex list-none items-center gap-[7px] p-0">
      {items.map((it) => (
        <li key={it.id} data-onb-dot={it.id} data-state={it.state} aria-current={it.state === 'current' ? 'step' : undefined} className="flex">
          <motion.span
            aria-hidden
            className="block"
            style={{ height: 6, borderRadius: radius2.round, background: it.state === 'current' ? color.text : it.state === 'done' ? tone.passed : fill.trackNext, transition: 'background-color 180ms' }}
            initial={false}
            animate={{ width: it.state === 'current' ? 18 : 6 }}
            transition={spring}
          />
          <span className="sr-only">
            {it.label}
            {it.state === 'done' ? ', done' : it.state === 'current' ? ', current' : ''}
          </span>
        </li>
      ))}
    </ol>
  )
}
