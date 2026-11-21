/**
 * Core (v2, W0-3): the two plain buttons every v2 surface uses. Options (Explain, Hint, Show me, Diagram, Watch) are
 * OptionTile (HelpRow.tsx) or OptionButton (atoms.tsx); everything else is one of these.
 *
 *   PrimaryButton  the ONE primary action per surface: white + ink on dark, ink + paper on paper. Never green, never blue.
 *   QuietButton    chrome and navigation (Back, Cancel, Keep working): a neutral fill, no hue.
 *
 * size 'md' is 30 px (the island's buttons), 'lg' is 36 px (panels and app windows). Keycaps come from the platform
 * (`keyName`), never a typed label. `busy` swaps the icon for the spinner (never look dead).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Spinner } from './atoms'
import { Keycap, type KeyName } from './Keycap'
import { color, fill, paper, radius2, type2 } from '../theme'

export type ButtonSize = 'md' | 'lg'
export type ButtonSurface = 'dark' | 'paper'

type Props = {
  label: string
  onClick: () => void
  icon?: LucideIcon
  keyName?: KeyName
  disabled?: boolean
  busy?: boolean
  size?: ButtonSize
  surface?: ButtonSurface
  /** Stretch to the container's width. */
  block?: boolean
  title?: string
}

const H: Record<ButtonSize, number> = { md: 30, lg: 36 }

function Base({ label, onClick, icon: I, keyName, disabled, busy, size = 'md', block, title, bg, fg, spin, hover, kind, keyOn }: Props & { bg: string; fg: string; spin: string; hover: string; kind: 'primary' | 'quiet'; keyOn: 'accent' | 'dark' | 'paper' }): ReactNode {
  const h = H[size]
  return (
    <motion.button
      type="button"
      data-button={kind}
      disabled={disabled}
      title={title}
      aria-busy={busy || undefined}
      className={`flex shrink-0 cursor-pointer items-center justify-center gap-[7px] whitespace-nowrap font-medium disabled:cursor-default ${block ? 'w-full' : ''}`}
      style={{
        height: h,
        paddingLeft: size === 'lg' ? 16 : 13,
        paddingRight: keyName ? 4 : size === 'lg' ? 16 : 13,
        borderRadius: radius2.round,
        fontSize: size === 'lg' ? type2.md : type2.sm,
        backgroundColor: bg,
        color: fg,
        opacity: disabled ? 0.4 : 1
      }}
      whileHover={disabled ? undefined : { filter: hover }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {busy ? <Spinner size={13} c={fg} track={spin} /> : I && <I size={size === 'lg' ? 14 : 13} strokeWidth={1.8} className="shrink-0" />}
      {label}
      {keyName && <Keycap k={keyName} on={keyOn} />}
    </motion.button>
  )
}

export function PrimaryButton(p: Props): ReactNode {
  const onPaper = p.surface === 'paper'
  return (
    <Base
      {...p}
      kind="primary"
      bg={onPaper ? paper.button : color.accent}
      fg={onPaper ? paper.buttonText : color.onAccent}
      spin={onPaper ? fill.trackSoft : fill.onAccentKey}
      hover={onPaper ? 'brightness(1.25)' : 'brightness(0.96)'}
      keyOn="accent"
    />
  )
}

export function QuietButton(p: Props): ReactNode {
  const onPaper = p.surface === 'paper'
  return (
    <Base
      {...p}
      kind="quiet"
      bg={onPaper ? paper.group : fill.button}
      fg={onPaper ? paper.ink : color.text}
      spin={onPaper ? paper.group : fill.trackSoft}
      hover="brightness(1.15)"
      keyOn={onPaper ? 'paper' : 'dark'}
    />
  )
}
