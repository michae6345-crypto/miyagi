/**
 * One command tile on the glass bar: a 30px glyph tile and its label. That's all at rest (pass 3: simpler).
 * The keycap appears above the tile on hover, and above every tile while ⌥ is held (keys.ts).
 * Colors are glass tokens (theme.glass): they flip with <html data-appearance="light">. Pastel option tiles keep
 * their ink glyph in both. Hover / lit backgrounds are plain CSS, not motion, so a live appearance switch repaints.
 */
import { AnimatePresence, motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { ActionKind } from '../../core/shortcuts'
import { actionTone, color, glass, type OptionAction } from '../../core/theme'
import { Glyph } from './Busy'
import { useAltHeld } from './keys'
import { PRESS_MS, PRESS_SCALE } from './press'

export type Look = { background: string; color: string }

/** Tile looks. Options: their pastel + ink. Chrome: a neutral glass tile. The one primary / a toggle that's on: glass.button. */
export const look = {
  option: (kind: OptionAction): Look => ({ background: actionTone[kind], color: color.onAccent }),
  neutral: { background: glass.fieldHover, color: glass.text } as Look,
  quiet: { background: glass.field, color: glass.label } as Look,
  primary: { background: glass.button, color: glass.buttonText } as Look
}

/** Hover fill for anything clickable on the bar (CSS, so it follows the appearance). */
export const hoverCls = 'transition-colors duration-150 hover:bg-[var(--glass-field)]'

type TileProps = {
  label: string
  icon: LucideIcon
  look: Look
  onClick: () => void
  /** bridge.platform.keys[kind]: shown above the tile on hover / ⌥ held. */
  keycap?: string
  /** The glyph becomes the Spinner while the engine thinks about this action (Busy.tsx). */
  busyKind?: ActionKind
  /** The 90 ms press dip (press.ts), for presses that didn't come from this tile's own click. */
  dip?: boolean
  /** Diagram open / More menu open: the tile's button stays filled. */
  lit?: boolean
  /** Toggles (Diagram, Voice): aria-pressed. */
  pressed?: boolean
  expanded?: boolean
  quiet?: boolean
  title?: string
  /** Replaces the icon (the Voice equalizer). */
  glyph?: ReactNode
}

export function Tile({ label, icon: Icon, look: l, onClick, keycap, busyKind, dip, lit, pressed, expanded, quiet, title, glyph }: TileProps): ReactNode {
  const [hover, setHover] = useState(false)
  const alt = useAltHeld((a) => a.held)
  const inner = glyph ?? <Icon size={16} strokeWidth={1.8} />
  return (
    <motion.button
      className={`relative flex h-[58px] w-[72px] cursor-pointer flex-col items-center justify-center rounded-[14px] ${hoverCls}`}
      style={lit ? { background: glass.field } : undefined}
      aria-pressed={pressed}
      aria-expanded={expanded}
      title={title}
      animate={{ scale: dip ? PRESS_SCALE : 1 }}
      whileTap={{ scale: PRESS_SCALE }}
      transition={{ duration: PRESS_MS / 1000 }}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onClick={onClick}
    >
      <span className="grid h-[30px] w-[30px] place-items-center rounded-[9px]" style={l}>
        {busyKind ? (
          <Glyph kind={busyKind} tone={l.color} size={16}>
            {inner}
          </Glyph>
        ) : (
          inner
        )}
      </span>
      <span className="mt-[6px] whitespace-nowrap text-[12px] leading-none" style={{ color: quiet ? glass.label : glass.text }}>
        {label}
      </span>
      <AnimatePresence>{keycap && (hover || alt) && <FloatingKey text={keycap} />}</AnimatePresence>
    </motion.button>
  )
}

/** A keycap floating above the bar: a small glass chip, readable over any desktop. Passive (data-ui). */
function FloatingKey({ text }: { text: string }): ReactNode {
  return (
    <motion.span
      data-ui
      data-keycap=""
      className="pointer-events-none absolute left-1/2 top-[-34px] flex h-[22px] items-center whitespace-nowrap rounded-[7px] border px-[7px] text-[11.5px] font-medium leading-none"
      style={{ x: '-50%', background: glass.bg, borderColor: glass.hairline, color: glass.label, backdropFilter: 'blur(20px)' }}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 4 }}
      transition={{ duration: 0.12 }}
    >
      {text}
    </motion.span>
  )
}

/** A keycap inside a glass surface (the Ask field, the More menu): the core Kbd, in glass colors. */
export function GlassKey({ text }: { text: string }): ReactNode {
  return (
    <span className="inline-flex h-[22px] items-center whitespace-nowrap rounded-[6px] px-[7px] text-[12px] font-medium" style={{ background: glass.key, color: glass.keyText }}>
      {text}
    </span>
  )
}
