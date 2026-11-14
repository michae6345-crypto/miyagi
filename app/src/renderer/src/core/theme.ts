/** Design tokens (FRONTEND-HANDOFF.md → "Design tokens" + "Animation spec"). */
import type { Transition } from 'motion/react'

/** The one spring used everywhere. */
export const spring: Transition = { type: 'spring', stiffness: 420, damping: 34, mass: 0.9 }
/** Collapse is the reverse, slightly faster. */
export const springOut: Transition = { type: 'spring', stiffness: 420, damping: 38, mass: 0.9 }

export const color = {
  accent: '#0A84FF',
  amber: '#FFB020',
  green: '#30D158',
  gray: '#8E8E93',
  label: 'rgba(255,255,255,.6)',
  faint: 'rgba(255,255,255,.42)',
  hairline: 'rgba(255,255,255,.12)',
  island: '#000000',
  glass: 'rgba(28,29,34,.90)'
} as const

export const radius = { chip: 14, card: 20, island: 24, pill: 17, launcher: 28 } as const

export const shadow = '0 20px 60px rgba(0,0,0,.45)'

/** Pill geometry. Collapsed pill is ~300×34; cards grow downward from its center. */
export const pill = { height: 34, landingWidth: 300, maxCardWidth: 520 } as const

/** Launcher: top edge at 22% of the screen height, 720 wide. */
export const launcher = { topRatio: 0.22, width: 720 } as const

/** "0:00" style timestamps. */
export function clock(t: number): string {
  const s = Math.max(0, Math.round(t))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
