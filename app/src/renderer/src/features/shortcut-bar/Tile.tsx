/**
 * One command tile on the glass bar: a 28px glyph tile, its label and, under it, its keycap.
 * Keycaps show at rest (audit A22: in Electron the overlay never has focus, so hover was the only way to learn a
 * key); hover or ⌥ held (keys.ts) brightens them. Labels are glass.text on every tile, quiet ones included, so no
 * live control reads as disabled; only `disabled` dims a tile.
 * Colors are glass tokens (theme.glass): they flip with <html data-appearance="light">. Pastel option tiles keep
 * their ink glyph in both. Hover / lit backgrounds are plain CSS, not motion, so a live appearance switch repaints.
 */
import { motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { ActionKind } from '../../core/shortcuts'
import { actionTone, color, fill, glass, type OptionAction } from '../../core/theme'
import { Glyph } from './Busy'
import { useAltHeld } from './keys'
import { PRESS_MS, PRESS_SCALE } from './press'

/** A tile's fill and glyph color, plus its busy spinner: `glass` = GlassSpinner (CSS vars), `track` = ring behind the arc. */
export type Look = { background: string; color: string; track: string; glass: boolean }

/**
 * Tile looks. Options: their pastel + ink, the core ink Spinner on an ink-10% track. Chrome: a neutral glass tile.
 * The one primary / a toggle that's on: glass.button; its track is the button's text at 18% (no glass token reads
 * on glass.button in both appearances).
 */
export const look = {
  option: (kind: OptionAction): Look => ({ background: actionTone[kind], color: color.onAccent, track: fill.onAccentKey, glass: false }),
  neutral: { background: glass.fieldHover, color: glass.text, track: glass.track, glass: true } as Look,
  quiet: { background: glass.field, color: glass.label, track: glass.track, glass: true } as Look,
  primary: { background: glass.button, color: glass.buttonText, track: `color-mix(in srgb, ${glass.buttonText} 18%, transparent)`, glass: true } as Look
}

/** Hover fill for anything clickable on the bar (CSS, so it follows the appearance). */
export const hoverCls = 'transition-colors duration-150 hover:bg-[var(--glass-field)]'

/** A disabled tile (Back on a text lesson's first step): dimmed as a whole, no hover, no press. */
const DISABLED_OPACITY = 0.38

type TileProps = {
  label: string
  icon: LucideIcon
  look: Look
  onClick: () => void
  /** bridge.platform.keys[kind]: shown under the label. Tiles without one keep the line empty, so glyphs align. */
  keycap?: string
  /** The glyph becomes the Spinner while the engine thinks about this action (Busy.tsx). */
  busyKind?: ActionKind
  /** The 90 ms press dip (press.ts), for presses that didn't come from this tile's own click. */
  dip?: boolean
  /** Diagram open: the tile's button stays filled. */
  lit?: boolean
  /** Toggles (Diagram, Voice): aria-pressed. */
  pressed?: boolean
  expanded?: boolean
  disabled?: boolean
  title?: string
  /** Replaces the icon (the Voice equalizer). */
  glyph?: ReactNode
}

export function Tile({ label, icon: Icon, look: l, onClick, keycap, busyKind, dip, lit, pressed, expanded, disabled, title, glyph }: TileProps): ReactNode {
  const [hover, setHover] = useState(false)
  const alt = useAltHeld((a) => a.held)
  const inner = glyph ?? <Icon size={16} strokeWidth={1.8} />
  return (
    <motion.button
      className={`relative flex h-[62px] min-w-[72px] flex-col items-center justify-center rounded-[14px] px-[6px] ${disabled ? 'cursor-default' : `cursor-pointer ${hoverCls}`}`}
      style={{ ...(lit ? { background: glass.field } : {}), ...(disabled ? { opacity: DISABLED_OPACITY } : {}) }}
      aria-pressed={pressed}
      aria-expanded={expanded}
      disabled={disabled}
      title={title}
      animate={{ scale: dip && !disabled ? PRESS_SCALE : 1 }}
      whileTap={disabled ? undefined : { scale: PRESS_SCALE }}
      transition={{ duration: PRESS_MS / 1000 }}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onClick={onClick}
    >
      <span className="grid h-[28px] w-[28px] place-items-center rounded-[8px]" style={{ background: l.background, color: l.color }}>
        {busyKind ? (
          <Glyph kind={busyKind} tone={l.color} track={l.track} glass={l.glass} size={16}>
            {inner}
          </Glyph>
        ) : (
          inner
        )}
      </span>
      <span className="mt-[6px] whitespace-nowrap text-[12px] leading-none" style={{ color: glass.text }}>
        {label}
      </span>
      <span
        data-keycap={keycap ? '' : undefined}
        className="mt-[4px] h-[11px] whitespace-nowrap text-[10.5px] font-medium leading-none transition-colors duration-150"
        style={{ color: (hover && !disabled) || alt ? glass.text : glass.keyText }}
      >
        {keycap}
      </span>
    </motion.button>
  )
}

/** A keycap inside a glass surface (the Ask field): the core Kbd, in glass colors. */
export function GlassKey({ text }: { text: string }): ReactNode {
  return (
    <span className="inline-flex h-[22px] items-center whitespace-nowrap rounded-[6px] px-[7px] text-[12px] font-medium" style={{ background: glass.key, color: glass.keyText }}>
      {text}
    </span>
  )
}
