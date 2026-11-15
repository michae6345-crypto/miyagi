/**
 * Feature: launcher. Small pieces of the panel: the staggered section entrance, the chips, and the
 * footer actions (text + keycap, Spotlight-style). The primary action is the brand's button when it can act:
 * white on the dark island with ink text (color.accent / color.onAccent); otherwise a quiet label.
 *
 * Colors are set inline on buttons because they animate (hover, enabled ↔ disabled).
 */
import { motion, useReducedMotion } from 'motion/react'
import type { ReactNode } from 'react'
import { GraduationCap, Play, type LucideIcon } from 'lucide-react'
import { Kbd } from '../../core/ui/atoms'
import { color, fill, spring } from '../../core/theme'

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

/**
 * A rounded chip: a suggestion to search, or a quick action. With `tone` it's a solid pastel option (fill and border in
 * the tone, ink text and icon); without, a quiet neutral chip. Colors are inline because they animate on hover.
 */
export function Chip({ icon: I, label, kbd, tone, onClick }: { icon: LucideIcon; label: string; kbd?: string; tone?: string; onClick: () => void }): ReactNode {
  const ink = color.onAccent
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      className={`flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] text-[13px] ${tone ? 'font-medium' : ''} ${kbd ? 'pr-[4px]' : 'pr-[13px]'}`}
      style={tone ? { backgroundColor: tone, borderColor: tone, color: ink, filter: 'brightness(1)' } : { backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText }}
      whileHover={tone ? { filter: 'brightness(1.06)' } : { backgroundColor: fill.chipHover, color: color.text }}
      whileTap={{ scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={13} strokeWidth={1.8} className="shrink-0" style={{ color: tone ? ink : color.faint }} />
      {label}
      {kbd &&
        (tone ? (
          <span className="inline-flex h-[22px] items-center rounded-full px-[8px] text-[11px] font-medium" style={{ background: fill.onAccentKey, color: ink }}>
            {kbd}
          </span>
        ) : (
          <Kbd className="!h-[22px] !rounded-full !px-[8px] !text-[11px]">{kbd}</Kbd>
        ))}
    </motion.button>
  )
}

/** How the learner wants to learn the topic they typed (Michael, "two ways to learn"). */
export type How = 'video' | 'lesson'

/**
 * The two ways to learn, under the query: "Watch a video" (search, preflight, gated player) or "Just teach me"
 * (no video: a text lesson over the full-screen editor). Monochrome chrome, not pastel options and not a second white
 * primary (the footer's Search / Start lesson is the one primary): the picked one is a lit chip (brighter fill, ring
 * border, full-white text), the other a quiet chip. Tab switches, Enter picks, ⌘/Ctrl+Enter is "Just teach me".
 */
export function HowChoice({ how, teachKey, onPick }: { how: How; teachKey: string; onPick: (h: How) => void }): ReactNode {
  const options: { id: How; label: string; Icon: LucideIcon; kbd?: string }[] = [
    { id: 'video', label: 'Watch a video', Icon: Play },
    { id: 'lesson', label: 'Just teach me', Icon: GraduationCap, kbd: teachKey }
  ]
  return (
    <div className="flex flex-wrap gap-[8px]" role="radiogroup" aria-label="How do you want to learn this?">
      {options.map(({ id, label, Icon, kbd }) => {
        const on = id === how
        return (
          <motion.button
            key={id}
            type="button"
            tabIndex={-1}
            role="radio"
            aria-checked={on}
            className={`flex h-[30px] cursor-pointer items-center gap-[7px] whitespace-nowrap rounded-full border pl-[11px] text-[13px] font-medium ${kbd ? 'pr-[4px]' : 'pr-[13px]'}`}
            initial={false}
            animate={
              on
                ? { backgroundColor: fill.chipHover, borderColor: fill.ring, color: color.text }
                : { backgroundColor: fill.chip, borderColor: fill.chipBorder, color: fill.chipText }
            }
            whileHover={on ? undefined : { backgroundColor: fill.chipHover, color: color.text }}
            whileTap={{ scale: 0.97 }}
            transition={{ duration: 0.14 }}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(id)}
          >
            <Icon size={13} strokeWidth={1.8} className="shrink-0" />
            {label}
            {kbd && <Kbd className="!h-[22px] !rounded-full !px-[8px] !text-[11px]">{kbd}</Kbd>}
          </motion.button>
        )
      })}
    </div>
  )
}

/** A passive key hint in the footer, e.g. "Choose ↑↓": same shape as an Action, not clickable. */
export function Hint({ label, keycap }: { label: string; keycap: string }): ReactNode {
  return (
    <span className="flex h-[30px] shrink-0 items-center gap-[8px] whitespace-nowrap pl-[10px] pr-[4px] text-[13px]" style={{ color: color.faint }}>
      {label}
      <Kbd className="!h-[22px] !min-w-[24px] !justify-center !rounded-full !px-[6px] !text-[12px]">{keycap}</Kbd>
    </span>
  )
}

/** A footer action: label + keycap. `strong` + enabled = the white primary button; otherwise text, faint when it can't act. */
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
  const solid = strong && enabled
  return (
    <motion.button
      type="button"
      tabIndex={-1}
      disabled={!enabled}
      className={`flex h-[30px] shrink-0 cursor-pointer items-center gap-[8px] whitespace-nowrap rounded-full pr-[4px] text-[13px] disabled:cursor-default ${solid ? 'pl-[12px]' : 'pl-[10px]'} ${strong ? 'font-medium' : ''}`}
      initial={false}
      animate={{
        backgroundColor: solid ? color.accent : fill.clear,
        color: solid ? color.onAccent : enabled ? color.label : color.faint
      }}
      whileHover={enabled ? (solid ? { scale: 1.03 } : { backgroundColor: fill.chip, color: color.text }) : undefined}
      whileTap={enabled ? { scale: 0.97 } : undefined}
      transition={{ duration: 0.14 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {label}
      {solid ? (
        <span className="grid h-[22px] min-w-[24px] place-items-center rounded-full px-[6px] text-[12px]" style={{ background: fill.onAccentKey, color: color.onAccent }}>
          {keycap}
        </span>
      ) : (
        <Kbd className="!h-[22px] !min-w-[24px] !justify-center !rounded-full !px-[6px] !text-[12px]">{keycap}</Kbd>
      )}
    </motion.button>
  )
}
