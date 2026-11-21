/**
 * Core: glass twins of the island atoms (StatusDot, CheckIcon, Spinner, PrimaryButton) for glass panels that follow
 * Settings → Appearance (player, drawer, shortcut bar). From the player agent (core request 6).
 *
 * The player is a glass panel: it follows Settings → Appearance (theme.glass CSS variables flip on
 * <html data-appearance>). The core atoms (StatusDot, CheckIcon, PrimaryButton, Spinner) are tuned for
 * the black island, so these are their glass twins, local to the player. (Core request: a `tone="glass"`
 * on the atoms would let every glass panel share them.)
 *
 * Colors go through `style` (CSS properties), never SVG presentation attributes, so var() always resolves.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { Status } from '../lesson'
import { color, glass, spring } from '../theme'

/** Status on glass: gray watching, apricot off track, green passed (both deeper on light). */
export function GlassDot({ status, size = 7 }: { status: Status; size?: number }): ReactNode {
  const c = status === 'offtrack' ? glass.offTrack : status === 'passed' ? glass.pass : color.gray
  const ring = status === 'offtrack'
  return (
    <motion.span
      key={status}
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: ring ? 'transparent' : c, boxShadow: ring ? `inset 0 0 0 1.5px ${c}` : undefined }}
      initial={{ scale: 1 }}
      animate={{ scale: status === 'offtrack' ? [1, 1.35, 1, 1.35, 1] : 1 }}
      transition={{ duration: 0.9, ease: 'easeInOut' }}
    />
  )
}

/** A passed check: a filled pass circle whose mark is cut out in the panel color, drawn on mount. */
export function GlassCheck({ size = 18 }: { size?: number }): ReactNode {
  return (
    <motion.svg width={size} height={size} viewBox="0 0 18 18" className="shrink-0" initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={spring}>
      <circle cx="9" cy="9" r="9" style={{ fill: glass.pass }} />
      <motion.path
        d="M5.2 9.3 L7.8 11.8 L12.9 6.4"
        fill="none"
        style={{ stroke: glass.bg }}
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.25, ease: 'easeOut', delay: 0.05 }}
      />
    </motion.svg>
  )
}

/** Spinning arc for "working on it", in glass colors. */
export function GlassSpinner({ size = 18, c = glass.label, track = glass.rule }: { size?: number; c?: string; track?: string }): ReactNode {
  return (
    <motion.svg width={size} height={size} viewBox="0 0 18 18" className="shrink-0" animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
      <circle cx="9" cy="9" r="7.5" fill="none" style={{ stroke: track }} strokeWidth="1.6" />
      <path d="M9 1.5 A7.5 7.5 0 0 1 16.5 9" fill="none" style={{ stroke: c }} strokeWidth="1.6" strokeLinecap="round" />
    </motion.svg>
  )
}

/** The one primary action on a glass panel: white on dark, ink on light. */
export function GlassPrimary({ label, icon: I, onClick, disabled }: { label: string; icon?: LucideIcon; onClick: () => void; disabled?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      disabled={disabled}
      className="flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full px-[13px] text-[13px] font-medium disabled:cursor-default"
      style={{ backgroundColor: glass.button, color: glass.buttonText, opacity: disabled ? 0.4 : 1 }}
      whileHover={disabled ? undefined : { filter: 'brightness(0.96)' }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {I && <I size={13} strokeWidth={1.8} className="shrink-0" />}
      {label}
    </motion.button>
  )
}

/** A neutral pill (chrome, not an option or the primary): Replay / Skip next to the one primary. */
export function GlassQuiet({ label, icon: I, onClick, busy }: { label: string; icon: LucideIcon; onClick: () => void; busy?: boolean }): ReactNode {
  return (
    <motion.button
      type="button"
      className="flex h-[30px] shrink-0 cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full bg-[var(--glass-field)] px-[13px] text-[13px] font-medium hover:bg-[var(--glass-field-hover)]"
      style={{ color: glass.text }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {busy ? <GlassSpinner size={13} c={glass.text} /> : <I size={13} strokeWidth={1.8} className="shrink-0" />}
      {label}
    </motion.button>
  )
}

// v2 (W0-3): the dark card for v2 surfaces, under the glass module too.
export { GlassCard, type GlassSurface } from './GlassCard'
