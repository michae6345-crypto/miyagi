/**
 * The Miyagi bonsai and wordmark, from the brand kit (app/brand). Never redraw the tree or retype the
 * wordmark: use these. The cut follows the size: small ≤ 32px, icon ≤ 140px, full above.
 * tone 'dark' = for dark backgrounds (lighter bark and clay), 'light' for light ones. Left out, the cut follows the theme
 * (Settings > Appearance), and the always-dark island and overlay keep the dark cut.
 *
 * The tree is in COLOR everywhere in the app (Adrian, Sun: back from the Sat monochrome cut): green pads, brown
 * trunk and clay pot (Nov 19), as drawn in the brand files. Don't recolor or filter it. `mono` (white silhouette on dark,
 * ink on light) is kept only for a surface that truly needs a one-color glyph; nothing in the app passes it.
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

/** The bonsai. Replaces every sparkle icon in the app (pill, launcher input, …). In color by default. */
export function MiyagiMark({ size = 16, tone, level = 'auto', mono = false, className }: { size?: number; tone?: Tone; level?: Level; mono?: boolean; className?: string }): ReactNode {
  const lvl = level === 'auto' ? markLevel(size) : level
  const one = (t: Tone, show?: string): ReactNode => {
    const filter = mono ? (t === 'dark' ? 'brightness(0) invert(1)' : 'brightness(0)') : undefined
    return <img key={t} src={SRC[lvl][t]} width={size} height={size} alt="" aria-hidden draggable={false} style={{ ...(filter ? { filter } : {}), ...(show ? { display: show } : {}) }} className={`shrink-0 select-none ${className ?? ''}`} />
  }
  // No tone: both cuts, and the theme (--mk-dark / --mk-light, core/theme.ts) shows the one that fits the background.
  return tone ? one(tone) : <>{one('dark', 'var(--mk-dark)')}{one('light', 'var(--mk-light)')}</>
}

/** The wordmark: lowercase miyagi with the green light on the first i. Height in px. */
export function MiyagiWordmark({ height = 20, tone, className }: { height?: number; tone?: Tone; className?: string }): ReactNode {
  const one = (t: Tone, show?: string): ReactNode => <img key={t} src={t === 'dark' ? wordmarkDark : wordmark} height={height} style={{ width: 'auto', ...(show ? { display: show } : {}) }} alt="miyagi" draggable={false} className={className} />
  return tone ? one(tone) : <>{one('dark', 'var(--mk-dark)')}{one('light', 'var(--mk-light)')}</>
}
