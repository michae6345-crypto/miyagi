/**
 * Feature: launcher. Fills the launcher needs that core/theme.ts has no token for yet.
 * Kept in this one place so Adrian's theme can replace them in one go (see "Core requests" in the brief).
 */
export const tint = {
  /** Search field fill and border, on the black island. */
  field: 'rgba(255,255,255,.07)',
  fieldBorder: 'rgba(255,255,255,.1)',
  /** The gliding row highlight. */
  highlight: 'rgba(255,255,255,.08)',
  highlightBorder: 'rgba(255,255,255,.08)',
  /** Icon tiles and skeleton bars. */
  icon: 'rgba(255,255,255,.08)',
  skeleton: 'rgba(255,255,255,.07)',
  /** A light backdrop dim (opacity animates 0 → 1). */
  dim: 'rgba(0,0,0,.18)',
  /** Button inner chip (↵). */
  onAccent: 'rgba(255,255,255,.22)',
  accentGlow: '0 6px 20px rgba(10,132,255,.35)',
  /** Must equal core/Island.tsx's shadows so the hand-over is invisible: pill-sized, and card-sized. */
  pillShadow: '0 2px 10px rgba(0,0,0,.25)',
  cardShadow: '0 24px 60px rgba(0,0,0,.5)'
} as const
