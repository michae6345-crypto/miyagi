/**
 * Feature: launcher. White-overlay fills the launcher needs that core/theme.ts has no token for yet.
 * Kept in this one place so Adrian's theme can replace them in one go (see "Core requests" in the brief).
 */
export const tint = {
  /** Search field fill and border. */
  field: 'rgba(255,255,255,.06)',
  fieldBorder: 'rgba(255,255,255,.14)',
  /** The gliding row highlight. */
  highlight: 'rgba(255,255,255,.08)',
  highlightBorder: 'rgba(255,255,255,.1)',
  /** Icon tiles and skeleton bars. */
  icon: 'rgba(255,255,255,.08)',
  skeleton: 'rgba(255,255,255,.07)',
  /** Backdrop dim (opacity animates 0 → 1, so the screen dims 0 → .35). */
  dim: 'rgba(0,0,0,.35)',
  /** Button inner chip (↵). */
  onAccent: 'rgba(255,255,255,.22)',
  accentGlow: '0 6px 20px rgba(10,132,255,.35)',
  /** The landed pill's shadow: must equal core/Island.tsx's pill shadow so the swap is invisible. */
  pillShadow: '0 2px 10px rgba(0,0,0,.25)',
  clear: 'rgba(255,255,255,0)'
} as const
