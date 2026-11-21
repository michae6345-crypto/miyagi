/**
 * Core (v2, W0-3): the two plain buttons every v2 surface uses. Options (Explain, Hint, Show me, Diagram, Watch) are
 * OptionTile (HelpRow.tsx) or OptionButton (atoms.tsx); everything else is one of these.
 *
 *   PrimaryButton  the ONE primary action per surface: white + ink on dark, ink + paper on paper. Never green, never blue.
 *   QuietButton    chrome and navigation (Back, Cancel, Keep working): a neutral fill, no hue.
 *
 * Geometry is the v2 mockups' rounded rectangle, never a pill: 'lg' is 44 px, radius 12, 15 px (Les-* 'Check my work',
 * Onb-Setup-Ready, Err-EngineReconnect, Prog-Progress-Window); 'md' is 36 px, radius 10, 13 px (Home-Library 'New
 * lesson'). Primary text is 600; Quiet is 13 px / 500 on surface.row with an inset hairline (Err-EngineReconnect 'Copy
 * details'). Keycaps come from the platform (`keyName`), never a typed label. `busy` swaps the icon for the spinner.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Spinner } from './atoms'
import { Keycap, type KeyName } from './Keycap'
import { color, fill, paper, radius2, surface, type2 } from '../theme'

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

const H: Record<ButtonSize, number> = { md: 36, lg: 44 }
const R: Record<ButtonSize, number> = { md: radius2.row, lg: radius2.card }
const PAD: Record<ButtonSize, number> = { md: 16, lg: 24 }

type Look = { bg: string; fg: string; spin: string; hover: string; kind: 'primary' | 'quiet'; keyOn: 'accent' | 'dark' | 'paper'; border?: string }

function Base({ label, onClick, icon: I, keyName, disabled, busy, size = 'md', block, title, bg, fg, spin, hover, kind, keyOn, border }: Props & Look): ReactNode {
  const h = H[size]
  const quiet = kind === 'quiet'
  return (
    <motion.button
      type="button"
      data-button={kind}
      disabled={disabled}
      title={title}
      aria-busy={busy || undefined}
      className={`flex shrink-0 cursor-pointer items-center justify-center gap-[8px] whitespace-nowrap disabled:cursor-default ${block ? 'w-full' : ''}`}
      style={{
        height: h,
        paddingLeft: PAD[size],
        paddingRight: keyName ? Math.round(PAD[size] / 2) : PAD[size],
        borderRadius: R[size],
        fontSize: quiet || size === 'md' ? type2.sm : type2.body,
        fontWeight: quiet ? 500 : 600,
        backgroundColor: bg,
        boxShadow: border ? `inset 0 0 0 1px ${border}` : undefined,
        color: fg,
        opacity: disabled ? 0.4 : 1
      }}
      whileHover={disabled ? undefined : { filter: hover }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {busy ? <Spinner size={size === 'lg' ? 15 : 13} c={fg} track={spin} /> : I && <I size={size === 'lg' ? 16 : 14} strokeWidth={1.8} className="shrink-0" />}
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
      bg={onPaper ? paper.field : surface.row}
      fg={onPaper ? paper.ink : color.text}
      border={onPaper ? paper.border : surface.border}
      spin={onPaper ? paper.group : fill.trackSoft}
      hover="brightness(1.15)"
      keyOn={onPaper ? 'paper' : 'dark'}
    />
  )
}
