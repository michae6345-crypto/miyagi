/**
 * The Miyagi bonsai and wordmark, from the brand kit (app/brand). Never redraw the tree or retype the
 * wordmark: use these. The cut follows the size: small ≤ 32px, icon ≤ 140px, full above.
 * tone 'dark' = for dark backgrounds (white trunk and pot): the default, since the overlay is dark HUD.
 */
import type { ReactNode } from 'react'
import treeFull from '../../assets/brand/tree-full.svg'
import treeFullDark from '../../assets/brand/tree-full-dark.svg'
import treeIcon from '../../assets/brand/tree-icon.svg'
import treeIconDark from '../../assets/brand/tree-icon-dark.svg'
import treeSmall from '../../assets/brand/tree-small.svg'
import treeSmallDark from '../../assets/brand/tree-small-dark.svg'
import wordmark from '../../assets/brand/wordmark.svg'
import wordmarkDark from '../../assets/brand/wordmark-dark.svg'
import { markLevel } from '../theme'

type Level = 'auto' | 'full' | 'icon' | 'small'
type Tone = 'light' | 'dark'

const SRC = {
  full: { light: treeFull, dark: treeFullDark },
  icon: { light: treeIcon, dark: treeIconDark },
  small: { light: treeSmall, dark: treeSmallDark }
} as const

/** The bonsai. Replaces every sparkle icon in the app (pill, launcher input, …). */
export function MiyagiMark({ size = 16, tone = 'dark', level = 'auto', className }: { size?: number; tone?: Tone; level?: Level; className?: string }): ReactNode {
  const lvl = level === 'auto' ? markLevel(size) : level
  return <img src={SRC[lvl][tone]} width={size} height={size} alt="" aria-hidden draggable={false} className={`shrink-0 select-none ${className ?? ''}`} />
}

/** The wordmark: lowercase miyagi with the green light on the first i. Height in px. */
export function MiyagiWordmark({ height = 20, tone = 'dark', className }: { height?: number; tone?: Tone; className?: string }): ReactNode {
  return <img src={tone === 'dark' ? wordmarkDark : wordmark} height={height} style={{ width: 'auto' }} alt="Miyagi" draggable={false} className={className} />
}
