/**
 * Core (v2, W0-3): a keycap. The label ALWAYS comes from bridge.platform.keys (⌃⌥E on a Mac, Alt+E on Windows): pass
 * the key's name, never a label. A name the platform doesn't have renders nothing (never a guess).
 *
 *   <Keycap k="explain" />                 on a dark surface (panel, island, window)
 *   <Keycap k="hint" on="accent" />        inside a white button (follows the theme)
 *   <Keycap k="hint" on="pastel" />        inside a solid option pastel (ink at 10%, both appearances)
 *   <Keycap k="dismiss" on="paper" />      on a light surface
 */
import type { ReactNode } from 'react'
import type { KeyName } from '../../../../main/platform'
import { bridge } from '../../bridge'
import { fill, highlight, paper, radius2, type2 } from '../theme'

export type { KeyName }
export type KeycapOn = 'dark' | 'accent' | 'pastel' | 'paper'

/** The label for a key name, or undefined when this platform has none. */
export function keyLabel(k: KeyName): string | undefined {
  const keys = bridge.platform.keys as Partial<Record<KeyName, string>>
  return keys[k] || undefined
}

/** Polish: a keycap stands on its surface (a darker bottom lip, a faint top edge) so it reads as a key, not a tag. */
const TONE: Record<KeycapOn, { bg: string; fg: string; border?: string; lip?: string }> = {
  dark: { bg: fill.keycap, fg: fill.keycapText, border: fill.keycapBorder, lip: `${highlight.keyLip}, ${highlight.topSoft}` },
  accent: { bg: fill.onAccentKey, fg: 'inherit' },
  pastel: { bg: fill.onPastelKey, fg: 'inherit' },
  paper: { bg: paper.group, fg: paper.muted, border: paper.hairline, lip: highlight.base }
}

export function Keycap({ k, on = 'dark', size = 'md' }: { k: KeyName; on?: KeycapOn; size?: 'sm' | 'md' }): ReactNode {
  const label = keyLabel(k)
  if (!label) return null
  const t = TONE[on]
  const h = size === 'sm' ? 18 : 22
  return (
    <span
      data-keycap={k}
      className="inline-flex shrink-0 items-center justify-center whitespace-nowrap font-medium tabular-nums"
      style={{
        height: h,
        minWidth: h,
        padding: '0 6px',
        borderRadius: on === 'accent' || on === 'pastel' ? radius2.round : radius2.keycap,
        background: t.bg,
        color: t.fg,
        boxShadow: [t.lip, t.border && `inset 0 0 0 1px ${t.border}`].filter(Boolean).join(', ') || undefined,
        fontSize: type2.micro,
        lineHeight: 1
      }}
    >
      {label}
    </span>
  )
}
