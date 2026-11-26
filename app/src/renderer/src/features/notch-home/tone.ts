/**
 * Feature: notch-home. The panel's tone for the island (core/islandTone.ts), pure so test/notchTint.test.ts can run it.
 * Calm ('home': bon's gradient may show) unless the panel is saying something went wrong: a dropped page miyagi can't
 * read or teach, or a drop that wasn't a link. Then 'warning', plain black, so a hue never sits behind a refusal.
 */
import type { PanelKind } from '../../core/islandTone'

export function homeTone(s: { dropped?: string; preview?: { error?: unknown; teachable?: boolean }; miss: boolean }): PanelKind {
  const cannot = !!s.dropped && !!s.preview && (!!s.preview.error || s.preview.teachable === false)
  return s.miss || cannot ? 'warning' : 'home'
}
