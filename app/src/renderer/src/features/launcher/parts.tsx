/**
 * Feature: launcher. Small pieces of the panel: the staggered section entrance, the chips, and the
 * footer actions (text + keycap, Spotlight-style; no filled buttons).
 *
 * Colors are set inline on buttons: styles.css's unlayered `button { color: inherit }` beats
 * Tailwind's layered text-* utilities on <button>.
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Kbd } from '../../core/ui/atoms'
import { color, spring } from '../../core/theme'
import { tint } from './tint'

/** One section of the panel settling into place a beat after the one above it. */
export function Rise({ i, children, className = '' }: { i: number; children: ReactNode; className?: string }): ReactNode {
  const reduce = useReducedMotion()
  const delay = 0.07 + i * 0.04
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ y: { ...spring, delay }, opacity: { duration: 0.2, delay, ease: 'easeOut' } }}
    >
      {children}
    </motion.div>
  )
}

/** A quiet rounded chip: a suggestion to search, or a quick action. */
export function Chip({ icon: I, label, kbd, onClick }: { icon: LucideIcon; label: string; kbd?: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className={`flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] text-[13px] ${kbd ? 'pr-[4px]' : 'pr-[13px]'}`}
      style={{ backgroundColor: tint.chip, borderColor: tint.chipBorder, color: tint.chipText }}
      whileHover={{ backgroundColor: tint.chipHover, color: '#fff' }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={13} strokeWidth={1.8} className="shrink-0" style={{ color: color.faint }} />
      {label}
      {kbd && <Kbd className="!h-[22px] !rounded-full !px-[8px] !text-[11px]">{kbd}</Kbd>}
    </motion.button>
  )
}

/** A footer action: label + keycap. White when it can act, faint when it can't. */
export function Action({
  label,
  keycap,
  enabled,
  strong = false,
  onClick
}: {
  label: string
  keycap: string
  enabled: boolean
  strong?: boolean
  onClick: () => void
}): ReactNode {
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      disabled={!enabled}
      className={`flex h-[30px] shrink-0 cursor-pointer items-center gap-[8px] whitespace-nowrap rounded-[8px] pl-[8px] pr-[4px] text-[13px] disabled:cursor-default ${strong ? 'font-medium' : ''}`}
      style={{ color: enabled ? (strong ? '#fff' : color.label) : color.faint, backgroundColor: 'rgba(255,255,255,0)' }}
      whileHover={enabled ? { backgroundColor: tint.chip, color: '#fff' } : undefined}
      whileTap={enabled ? { scale: 0.97 } : undefined}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
      <Kbd className="!h-[22px] !min-w-[24px] !justify-center !px-[6px] !text-[12px]">{keycap}</Kbd>
    </motion.button>
  )
}
