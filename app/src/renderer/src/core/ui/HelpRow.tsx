/**
 * Core (v2, W0-3): the "Need help" row of the lesson panel (Les-Working): Explain, Hint, Show me, Diagram, Watch.
 * Five equal OptionTiles, gap 8, each a solid pastel (BRAND.md mapping, theme.actionTone: sky = Explain / Diagram /
 * Watch, pink = Hint, lilac = Show me) with an ink label and its keycap from the platform inside the tile. Watch has
 * no shortcut (decision 3).
 * Options only: never a status, never the primary.
 *
 * Polish (UI-POLISH-SPEC 3): a tile is a pastel slab (white top edge, ink base line, a small lift); hover darkens it 4.5%
 * through the tint layer, press dips it to .96 on the spring. A tile whose answer is on its way (`busy`) sits pressed
 * in: no lift, the press tint held, its spinner inside.
 *
 *   <HelpRow options={[{ action: 'explain', onClick }, { action: 'hint', onClick, busy }]} />
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Lightbulb, MessageSquareText, SquarePlay, Waypoints, type LucideIcon } from 'lucide-react'
import { Spinner } from './atoms'
import { Keycap, type KeyName } from './Keycap'
import { actionTone, color, elevation, fill, highlight, radius2, type2, type OptionAction } from '../theme'
import { pressMotion } from './motion'

/** Watch (a video jump): a play mark inside a rounded screen, so it reads apart from Show me's square-play. */
export function WatchIcon({ size = 14, strokeWidth = 1.8, className }: { size?: number; strokeWidth?: number; className?: string }): ReactNode {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="2.5" y="4.5" width="19" height="13" rx="3" />
      <path d="M10.5 8.5 L14.5 11 L10.5 13.5 Z" fill="currentColor" />
      <path d="M8 21 H16" />
    </svg>
  )
}

const LABEL: Record<OptionAction, string> = { explain: 'Explain', hint: 'Hint', show_me: 'Show me', diagram: 'Diagram', watch: 'Watch' }
const ICON: Partial<Record<OptionAction, LucideIcon>> = { explain: MessageSquareText, hint: Lightbulb, show_me: SquarePlay, diagram: Waypoints }
/** The platform key for each option; Watch has none this push. */
const KEY: Partial<Record<OptionAction, KeyName>> = { explain: 'explain', hint: 'hint', show_me: 'show_me', diagram: 'diagram' }

export type HelpOption = {
  action: OptionAction
  onClick: () => void
  label?: string
  busy?: boolean
  disabled?: boolean
  hideKey?: boolean
  /** A small ink glyph above the label. Off by default (the Les-Working row is label + keycap only). */
  glyph?: boolean
}

/**
 * One tile of the row (Les-Working `.hb`): flex-1, 56 high, radius 12, a solid pastel fill, an ink label 12 px / 600
 * and the keycap inside the tile in the ink-on-pastel tone. Watch has no keycap.
 */
export function OptionTile({ action, onClick, label, busy, disabled, hideKey, glyph }: HelpOption): ReactNode {
  const I = ICON[action]
  const k = hideKey ? undefined : KEY[action]
  return (
    <motion.button
      type="button"
      data-option={action}
      disabled={disabled}
      aria-busy={busy || undefined}
      className="mg-press mg-press-light flex min-w-0 flex-1 cursor-pointer flex-col items-center justify-center gap-[4px] disabled:cursor-default"
      style={{
        height: 56,
        padding: '0 4px',
        borderRadius: radius2.card,
        background: actionTone[action],
        color: color.onAccent,
        opacity: disabled ? 0.4 : 1,
        // Polish: busy drops the lift and keeps the base edge; the held press tint is .mg-press[aria-busy="true"]::after (styles.css).
        // Disabled is flat (no edges, no lift), the same as a disabled Base in buttons.tsx.
        boxShadow: disabled ? undefined : busy ? highlight.base : `${highlight.onLight}, ${highlight.base}, ${elevation.raised}`
      }}
      // Polish: a busy tile is already pressed in, so it does not dip again and a second click does not re-ask.
      {...pressMotion(disabled || busy, true)}
      onMouseDown={(e) => e.preventDefault()}
      onClick={busy ? undefined : onClick}
    >
      {busy ? <Spinner size={12} c={color.onAccent} track={fill.onAccentKey} /> : glyph ? I ? <I size={12} strokeWidth={1.8} aria-hidden /> : <WatchIcon size={12} /> : null}
      <span className="max-w-full truncate" style={{ fontSize: type2.xs, fontWeight: 600, lineHeight: 1.2 }}>
        {label ?? LABEL[action]}
      </span>
      {k && <Keycap k={k} on="accent" size="sm" />}
    </motion.button>
  )
}

export function HelpRow({ options, title = 'Need help' }: { options: ReadonlyArray<HelpOption>; title?: string | null }): ReactNode {
  return (
    <div data-help-row className="flex flex-col gap-[12px]">
      {title && (
        <div className="font-medium" style={{ fontSize: type2.xs, color: color.label }}>
          {title}
        </div>
      )}
      <div className="flex items-stretch gap-[8px]">
        {options.map((o) => (
          <OptionTile key={o.action} {...o} />
        ))}
      </div>
    </div>
  )
}
