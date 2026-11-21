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
 *
 * Polish (UI-POLISH-SPEC 3): each button is a lit slab. Primary: a white top edge and an ink base line inside, a two-layer
 * raised shadow under it. Quiet: the hairline plus the dark surfaces' top highlight. Hover and press are a tint layer
 * whose opacity fades (.mg-press, styles.css), never an animated filter or color; the dip is scale .97 on the spring.
 * Disabled: 40%, flat (no lift), no hover tint, no dip. Busy: held press tint, no lift, no dip, no second click.
 * Keyboard focus: the global focus-visible ring.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Spinner } from './atoms'
import { pressMotion } from './motion'
import { Keycap, type KeyName } from './Keycap'
import { color, elevation, fill, highlight, paper, radius2, surface, type2 } from '../theme'

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

/** `depth`: the button's own box-shadow stack (edges and lift). `light`: a white or pastel fill, so hover darkens. */
type Look = { bg: string; fg: string; spin: string; depth: string; light: boolean; kind: 'primary' | 'quiet'; keyOn: 'accent' | 'dark' | 'paper' }

function Base({ label, onClick, icon: I, keyName, disabled, busy, size = 'md', block, title, bg, fg, spin, depth, light, kind, keyOn }: Props & Look): ReactNode {
  const h = H[size]
  const quiet = kind === 'quiet'
  return (
    <motion.button
      type="button"
      data-button={kind}
      disabled={disabled}
      title={title}
      aria-busy={busy || undefined}
      className={`mg-press ${light ? 'mg-press-light' : ''} flex shrink-0 cursor-pointer items-center justify-center gap-[8px] whitespace-nowrap disabled:cursor-default ${block ? 'w-full' : ''}`}
      style={{
        height: h,
        paddingLeft: PAD[size],
        paddingRight: keyName ? Math.round(PAD[size] / 2) : PAD[size],
        borderRadius: R[size],
        fontSize: quiet || size === 'md' ? type2.sm : type2.body,
        fontWeight: quiet ? 500 : 600,
        backgroundColor: bg,
        // Disabled sits flat: a primary loses its edges and lift, a quiet button keeps its hairline.
        boxShadow: disabled && kind === 'primary' ? undefined : depth,
        color: fg,
        opacity: disabled ? 0.4 : 1
      }}
      // Polish: a busy button is already pressed in (held tint), so it does not dip again and a second click does not re-run.
      {...pressMotion(disabled || busy)}
      onMouseDown={(e) => e.preventDefault()}
      onClick={busy ? undefined : onClick}
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
      // Polish: busy keeps the edges and drops the lift, so the held press tint reads as pressed in.
      depth={
        onPaper
          ? p.busy
            ? highlight.top
            : `${highlight.top}, ${paper.shadowSmall}`
          : p.busy
            ? `${highlight.onLight}, ${highlight.base}`
            : `${highlight.onLight}, ${highlight.base}, ${elevation.raised}`
      }
      light={!onPaper}
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
      spin={onPaper ? paper.group : fill.trackSoft}
      depth={onPaper ? `inset 0 0 0 1px ${paper.border}` : `inset 0 0 0 1px ${surface.border}, ${highlight.top}`}
      light={onPaper}
      keyOn={onPaper ? 'paper' : 'dark'}
    />
  )
}
