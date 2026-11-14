/**
 * Feature: launcher. The neutral fills the launcher needs that core/theme.ts has no token for yet:
 * white at low alphas on the black island, nothing else. Every hue comes from the theme (color.*),
 * and the accent is used only for the caret and the "best" result, so Adrian's theme flows straight through.
 * Kept in one place so they can move into the theme in one go (see "Core requests" in the brief).
 */
export const tint = {
  /** Search field. */
  field: 'rgba(255,255,255,.06)',
  fieldBorder: 'rgba(255,255,255,.09)',
  /** Suggestion / quick-action chips. */
  chip: 'rgba(255,255,255,.05)',
  chipHover: 'rgba(255,255,255,.1)',
  chipBorder: 'rgba(255,255,255,.08)',
  chipText: 'rgba(255,255,255,.72)',
  /** The gliding row highlight. */
  highlight: 'rgba(255,255,255,.07)',
  /** Icon tiles and skeleton bars. */
  icon: 'rgba(255,255,255,.06)',
  iconGlyph: 'rgba(255,255,255,.55)',
  skeleton: 'rgba(255,255,255,.06)',
  /** Footer rule (same as the step card's). */
  rule: 'rgba(255,255,255,.08)',
  /** Keycap on the white primary button (ink at a low alpha). */
  onAccentKey: 'rgba(0,0,0,.1)',
  clear: 'rgba(255,255,255,0)',
  /** A light backdrop dim (opacity animates 0 → 1). */
  dim: 'rgba(0,0,0,.22)',
  /** Must equal core/Island.tsx's shadows so the hand-over is invisible: pill-sized, and card-sized. */
  pillShadow: '0 2px 10px rgba(0,0,0,.25)',
  cardShadow: '0 24px 60px rgba(0,0,0,.5)'
} as const
