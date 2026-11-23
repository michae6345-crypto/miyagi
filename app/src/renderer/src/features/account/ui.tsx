/**
 * Feature: account. Small pieces the four views share. Neutral only: the meter is white on dark and ink on paper
 * (never green: green means passed), rows and chips have no hue.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Keycap, type KeyName } from '../../core/ui/Keycap'
import { color, elevation, fill, highlight, paper, radius2, surface, type2 } from '../../core/theme'

/**
 * The account window's cards (menu, sign in, upgrade): one border and a top highlight in dark, no drop shadow (layout lane,
 * Nov 22); light keeps the soft tile lift. The same recipe as features/shell ui.tsx CARD.
 */
export const WINDOW_CARD_SHADOW = `${highlight.card}, inset 0 0 0 1px var(--l-border), ${elevation.tile}`
import { resetDay, type HelpMeter } from './model'
import { fade, press, spring } from '../../core/ui/motion'

export type Tone = 'dark' | 'paper'

/** The monthly help meter (Plan-AccountMenu, Plan-Upgrade, Plan-Pricing footer). */
export function Meter({ help, label, tone = 'dark', width }: { help: HelpMeter; label: string; tone?: Tone; width?: number | string }): ReactNode {
  const pct = Math.round((Math.min(help.used, help.limit) / help.limit) * 100)
  const onPaper = tone === 'paper'
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={help.limit}
      aria-valuenow={help.used}
      aria-valuetext={`${help.used} of ${help.limit}`}
      className="overflow-hidden"
      style={{ height: 6, width: width ?? '100%', borderRadius: radius2.round, background: onPaper ? paper.hairline : fill.hairline }}
    >
      <div style={{ height: 6, width: `${pct}%`, borderRadius: radius2.round, background: onPaper ? paper.ink : color.text }} />
    </div>
  )
}

/** The grouped meter block on a dark card: title, "N of M", the bar, "Resets on …". */
export function MeterGroup({ help, title, count, label, padding = 12, resetsDot = false }: { help: HelpMeter; title: string; count: string; label: string; padding?: number; resetsDot?: boolean }): ReactNode {
  const day = resetDay(help.resetsAt)
  return (
    <div className="flex flex-col gap-[8px]" style={{ padding, background: surface.row, borderRadius: radius2.chip }}>
      <div className="flex justify-between" style={{ fontSize: type2.sm, lineHeight: '18px' }}>
        <span className="font-medium" style={{ color: color.text }}>
          {title}
        </span>
        <span className="tabular-nums" style={{ color: color.label }}>
          {count}
        </span>
      </div>
      <Meter help={help} label={label} />
      {day && <span style={{ fontSize: type2.xs, lineHeight: '16px', color: color.label }}>{`Resets on ${day}${resetsDot ? '.' : ''}`}</span>}
    </div>
  )
}

/** One row of the account menu: icon, label, an optional right side (a keycap or a word). */
export function MenuRow({ icon: I, label, onClick, keyName, right }: { icon: LucideIcon; label: string; onClick: () => void; keyName?: KeyName; right?: string }): ReactNode {
  return (
    <motion.button
      type="button"
      role="menuitem"
      className="flex w-full cursor-pointer items-center gap-[12px] text-left"
      style={{ height: 44, padding: '0 12px', borderRadius: radius2.row, color: color.text, fontSize: type2.md, backgroundColor: fill.clear }}
      whileHover={{ backgroundColor: surface.row }}
      whileFocus={{ backgroundColor: surface.row }}
      transition={fade.tint}
      onClick={onClick}
    >
      <I size={16} strokeWidth={1.6} className="shrink-0" style={{ color: fill.chipText }} aria-hidden />
      <span className="flex-1">{label}</span>
      {keyName && <Keycap k={keyName} size="sm" />}
      {right && <span style={{ fontSize: type2.xs, color: color.label }}>{right}</span>}
    </motion.button>
  )
}

export function Rule({ tone = 'dark', inset = 0 }: { tone?: Tone; inset?: number }): ReactNode {
  return <div aria-hidden style={{ height: 1, margin: `0 ${inset}px`, background: tone === 'paper' ? paper.group : fill.hairline }} />
}

/** A neutral outline chip ("Free", "Recommended"). */
export function Chip({ children, tone = 'dark' }: { children: ReactNode; tone?: Tone }): ReactNode {
  const onPaper = tone === 'paper'
  return (
    <span
      className="shrink-0 font-semibold"
      style={{
        fontSize: type2.micro,
        lineHeight: '20px',
        padding: '0 8px',
        borderRadius: radius2.round,
        boxShadow: `inset 0 0 0 1px ${onPaper ? paper.border : fill.keycapBorder}`,
        color: onPaper ? paper.ink : fill.chipText
      }}
    >
      {children}
    </span>
  )
}

/** The calm line under a surface for actions that are not live yet. */
export function Note({ text, tone = 'dark' }: { text?: string; tone?: Tone }): ReactNode {
  return (
    <p aria-live="polite" className="m-0 text-center" style={{ minHeight: 16, fontSize: type2.xs, lineHeight: '16px', color: tone === 'paper' ? paper.label : color.label }}>
      {text ?? ''}
    </p>
  )
}

/** An inline text link that calls back into the app (never an href: every way out goes through main's allowlist). */
export function TextLink({ children, onClick, tone = 'dark', weight = 400 }: { children: ReactNode; onClick: () => void; tone?: Tone; weight?: number }): ReactNode {
  return (
    <button type="button" className="cursor-pointer underline underline-offset-2" style={{ color: tone === 'paper' ? paper.ink : color.text, fontWeight: weight, font: 'inherit' }} onClick={onClick}>
      {children}
    </button>
  )
}

/** The person glyph (Plan-AccountMenu avatar). */
export function PersonGlyph({ size = 20 }: { size?: number }): ReactNode {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden>
      <circle cx="8" cy="5.5" r="2.75" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path d="M2.75 14c.6-2.6 2.7-4 5.25-4s4.65 1.4 5.25 4" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  )
}

/** Sign-in provider marks (Plan-SignIn), drawn in the text color: one color, no brand fills. */
export function AppleGlyph(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M11.2 8.5c0-1.6 1.3-2.3 1.4-2.4-.8-1.1-1.9-1.3-2.3-1.3-1-.1-1.9.6-2.4.6-.5 0-1.3-.6-2.1-.6-1.1 0-2.1.6-2.6 1.6-1.1 1.9-.3 4.8.8 6.3.5.8 1.1 1.6 1.9 1.6.8 0 1-.5 2-.5s1.2.5 2 .5c.8 0 1.4-.8 1.9-1.5.6-.9.8-1.7.8-1.8 0 0-1.4-.6-1.4-2.5zM9.6 3.6c.4-.5.7-1.2.6-1.9-.6 0-1.4.4-1.8.9-.4.4-.7 1.1-.6 1.8.7.1 1.4-.3 1.8-.8z"
      />
    </svg>
  )
}

export function GoogleGlyph(): ReactNode {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
      <path
        fill="currentColor"
        d="M14.2 8.1c0-.5 0-.9-.1-1.3H8v2.5h3.5c-.2.8-.6 1.5-1.3 1.9v1.6h2.1c1.2-1.1 1.9-2.8 1.9-4.7zM8 14.5c1.8 0 3.2-.6 4.3-1.6l-2.1-1.6c-.6.4-1.3.6-2.2.6-1.7 0-3.1-1.1-3.6-2.7H2.2v1.7C3.3 13 5.5 14.5 8 14.5zM4.4 9.2c-.1-.4-.2-.8-.2-1.2s.1-.8.2-1.2V5.1H2.2C1.8 6 1.5 7 1.5 8s.3 2 .7 2.9l2.2-1.7zM8 4.1c1 0 1.8.3 2.5 1l1.9-1.9C11.2 2.1 9.8 1.5 8 1.5 5.5 1.5 3.3 3 2.2 5.1l2.2 1.7C4.9 5.2 6.3 4.1 8 4.1z"
      />
    </svg>
  )
}

/** A full-width neutral button with a custom glyph (the provider rows on Sign in), the same look as QuietButton lg. */
export function GlyphButton({ glyph, label, onClick }: { glyph: ReactNode; label: string; onClick: () => void }): ReactNode {
  return (
    <motion.button
      type="button"
      className="flex w-full cursor-pointer items-center justify-center gap-[8px] font-medium"
      style={{ height: 44, borderRadius: radius2.card, backgroundColor: surface.row, boxShadow: `inset 0 0 0 1px ${surface.border}`, color: color.text, fontSize: type2.md }}
      whileHover={{ backgroundColor: surface.rowHover }}
      whileTap={{ scale: press.scale }}
      transition={{ ...fade.tint, scale: spring }}
      onClick={onClick}
    >
      {glyph}
      {label}
    </motion.button>
  )
}
