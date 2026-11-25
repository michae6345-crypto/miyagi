/**
 * Core (v2, W0-3): a keycap. The label ALWAYS comes from bridge.platform.keys (⌃⌥E on a Mac, Alt+E on Windows), or the
 * learner's own key for a rebound shortcut (core/keys.ts, live): pass the key's name, never a label. A name the platform
 * doesn't have renders nothing (never a guess).
 *
 *   <Keycap k="explain" />                 on a dark surface (panel, island, window)
 *   <Keycap k="hint" on="accent" />        inside a white button (follows the theme)
 *   <Keycap k="hint" on="pastel" />        inside a solid option pastel (ink at 10%, both appearances)
 *   <Keycap k="dismiss" on="paper" />      on a light surface
 */
import type { ReactNode } from 'react'
import type { KeyName } from '../../../../main/platform'
import { liveKeyLabel, useKey } from '../keys'
import { fill, highlight, paper, radius2, type2 } from '../theme'

export type { KeyName }
export type KeycapOn = 'dark' | 'accent' | 'pastel' | 'paper'

/** The label for a key name right now (the learner's own key for a rebound shortcut), or undefined when there is none. In a component, prefer useKey (core/keys.ts): it re-renders when the key changes. */
export function keyLabel(k: KeyName): string | undefined {
  return liveKeyLabel(k)
}

/** Polish: a keycap stands on its surface (a darker bottom lip, a faint top edge) so it reads as a key, not a tag. */
const TONE: Record<KeycapOn, { bg: string; fg: string; border?: string; lip?: string }> = {
  dark: { bg: fill.keycap, fg: fill.keycapText, border: fill.keycapBorder, lip: `${highlight.keyLip}, ${highlight.topSoft}` },
  accent: { bg: fill.onAccentKey, fg: 'inherit' },
  pastel: { bg: fill.onPastelKey, fg: 'inherit' },
  paper: { bg: paper.group, fg: paper.muted, border: paper.hairline, lip: highlight.base }
}

export function Keycap({ k, on = 'dark', size = 'md' }: { k: KeyName; on?: KeycapOn; size?: 'sm' | 'md' }): ReactNode {
  const label = useKey(k)
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
