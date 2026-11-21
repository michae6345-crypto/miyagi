/**
 * Feature: auth. The signed-in learner's avatar: their initial in a neutral circle (chrome, never a hue; BRAND.md).
 * Signed out (no initial), the person glyph. Used by the login, the shell's Account page and its sidebar chip.
 */
import type { ReactNode } from 'react'
import { color, fill, radius2 } from '../../core/theme'
import { PersonGlyph } from '../account/ui'

export function Avatar({ initial, size = 32 }: { initial?: string; size?: number }): ReactNode {
  return (
    <span
      aria-hidden
      data-avatar={initial ? 'initial' : 'person'}
      className="relative flex shrink-0 items-center justify-center font-semibold"
      style={{ width: size, height: size, borderRadius: radius2.round, background: fill.navActive, color: color.text, fontSize: Math.round(size * 0.44), lineHeight: 1 }}
    >
      {initial ? initial : <PersonGlyph size={Math.round(size * 0.55)} />}
    </span>
  )
}
