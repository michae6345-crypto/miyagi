/**
 * Feature: drawer (v2, A1). The panel's small shared pieces: its text tones (all core/theme tokens), the hairline
 * divider, and inline text where `backticks` mark code (React text only, never HTML).
 */
import type { ReactNode } from 'react'
import { color, fill, font, type2 } from '../../../core/theme'

/**
 * Les-*: titles in white, body copy at white .78, labels at .6. There is no .78 text token in core yet (Core request
 * 1 in agents/drawer.md); fill.keycapText has that exact value.
 */
export const tone = { text: color.text, body: fill.keycapText, label: color.label, hairline: fill.hairline } as const

/** A full-width 1 px rule between the panel's sections. */
export function Divider(): ReactNode {
  return <div aria-hidden className="h-px shrink-0" style={{ background: tone.hairline }} />
}

/** Text where `code` spans render in the mono font (Les-Checking caption, Les-NotYet lines, Les-Hint). */
export function Inline({ text, codeColor }: { text: string; codeColor?: string }): ReactNode {
  const parts = text.split('`')
  // An odd count of backticks: the last one is literal, not an opening.
  if (parts.length % 2 === 0) return text
  return parts.map((p, i) =>
    i % 2 ? (
      <span key={i} style={{ fontFamily: font.mono, fontSize: '0.95em', color: codeColor }}>
        {p}
      </span>
    ) : (
      p
    )
  )
}

/** The 12 px label above a block ("Type this in the new cell", "Need help"). */
export function Caption({ children }: { children: ReactNode }): ReactNode {
  return (
    <span className="block" style={{ fontSize: type2.xs, lineHeight: '16px', color: tone.label }}>
      {children}
    </span>
  )
}
