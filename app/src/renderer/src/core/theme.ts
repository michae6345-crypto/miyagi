/**
 * Miyagi design tokens: the brand kit (app/brand/BRAND.md, app/brand/code/theme.ts) mapped onto the
 * names the app already uses. Change colors HERE, never in feature code.
 *
 * Brand rules (BRAND.md):
 *  - Green only ever means passed. Off track has no hue: a white ring (`color.amber` keeps the old slot's name). Gray means watching. No red.
 *  - Buttons are white on dark (ink on light). Never system blue, never green.
 *  - No gradients, glows, purple, neon, sparkles or emoji. The sparkle is replaced by the small tree.
 *  - App text in the system font (SF Pro / Segoe). Brand font (Google Sans Flex) only for brand moments. No Inter.
 */
import type { Transition } from 'motion/react'

/** The one spring used everywhere. */
export const spring: Transition = { type: 'spring', stiffness: 420, damping: 34, mass: 0.9 }
/** Collapse is the reverse, slightly faster. */
export const springOut: Transition = { type: 'spring', stiffness: 420, damping: 38, mass: 0.9 }

/** Brand palette, verbatim from the kit. */
export const brand = {
  paper: '#F6F6F3',
  surface: '#FFFFFF',
  surface2: '#EFEFEA',
  ink: '#141414',
  inkMuted: '#66665F',
  inkFaint: '#8F8F88',
  pass: '#30D158',
  passDeep: '#1F9B45',
  passText: '#1C8A3C',
  passTint: 'rgba(48,209,88,0.14)',
  /**
   * Off track has NO hue (Adrian, Sat 5 PM: amber read as "AI slop", then apricot still felt orange). It's white on
   * the island, drawn as a hollow ring ("Not yet"); offline stays the gray ring. offTrackDeep = ink on a light surface.
   */
  offTrack: '#F4F4F5',
  offTrackDeep: '#141414',
  offTrackTint: 'rgba(255,255,255,0.08)',
  watching: '#8E8E93',
  pill: '#000000',
  /**
   * Pastels for OPTIONS only (Adrian, Sat: "4 · Pastel"): suggestion / quick-action chips, source-kind tiles,
   * the "Best" label. Ink text on them. They never mean status (green = passed, amber = off track stay as is),
   * and the chrome stays black and white. No gradients or glow.
   */
  pastel: { pink: '#F9C5D5', sky: '#C5E4F9', lilac: '#D9D2FF', pinkDeep: '#F4A7BF', skyDeep: '#9CCFF2', apricot: '#FFC4A3' }
} as const

/** The overlay follows macOS: dark HUD glass by default, light when the system is light. */
export const hud = {
  dark: { glass: 'rgba(28,28,30,0.72)', text: '#F4F4F5', muted: 'rgba(255,255,255,0.6)', hairline: 'rgba(255,255,255,0.12)', button: '#F4F4F5', buttonText: '#141414' },
  light: { glass: 'rgba(255,255,255,0.78)', text: '#141414', muted: 'rgba(0,0,0,0.55)', hairline: 'rgba(0,0,0,0.10)', button: '#141414', buttonText: '#F6F6F3' }
} as const

/**
 * What components use (dark HUD). `accent` is the "active / interactive" color and is WHITE
 * (it used to be system blue): progress, focus, selected, primary buttons. Pair a white fill with `onAccent` text.
 */
export const color = {
  accent: hud.dark.button,
  onAccent: hud.dark.buttonText,
  /** Off track: white, shown as a ring (the name stays `amber` so call sites don't change). */
  amber: brand.offTrack,
  amberTint: brand.offTrackTint,
  /** Passed. Nothing else is green. */
  green: brand.pass,
  greenDeep: brand.passDeep,
  greenTint: brand.passTint,
  /** Watching (status dot). */
  gray: brand.watching,
  text: hud.dark.text,
  label: hud.dark.muted,
  faint: 'rgba(255,255,255,.42)',
  hairline: hud.dark.hairline,
  /** The notch pill and the island: always black. */
  island: brand.pill,
  /** Panels on the dark HUD. CSS can't blur other apps in Electron, so this is more opaque than the kit's .72. */
  glass: 'rgba(28,28,30,.90)'
} as const

export const font = {
  /** Everything inside the app. */
  ui: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif',
  /** Brand moments only (wordmark is an outlined SVG, so rarely needed in the app). */
  brand: '"Google Sans Flex", system-ui, sans-serif',
  mono: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'
} as const

export const text = { xs: 13, sm: 15, md: 20, lg: 28 } as const
export const radius = { chip: 14, card: 20, island: 24, pill: 17, launcher: 28 } as const
export const shadow = '0 20px 60px rgba(0,0,0,.45)'

/** The island's two shadows. Anything that hands over to the island (the launcher) must match them exactly. */
export const shadows = { pill: '0 2px 10px rgba(0,0,0,.25)', card: '0 24px 60px rgba(0,0,0,.5)' } as const

/** Neutral fills on the black island / dark HUD: white at low alphas, nothing else (brand: no extra hues). */
export const fill = {
  field: 'rgba(255,255,255,.06)',
  fieldBorder: 'rgba(255,255,255,.09)',
  chip: 'rgba(255,255,255,.05)',
  chipHover: 'rgba(255,255,255,.1)',
  chipBorder: 'rgba(255,255,255,.08)',
  chipText: 'rgba(255,255,255,.72)',
  highlight: 'rgba(255,255,255,.07)',
  tile: 'rgba(255,255,255,.06)',
  tileGlyph: 'rgba(255,255,255,.55)',
  skeleton: 'rgba(255,255,255,.06)',
  rule: 'rgba(255,255,255,.08)',
  /** A keycap sitting on a white (accent) or pastel button: ink at 10%. */
  onAccentKey: 'rgba(0,0,0,.1)',
  clear: 'rgba(255,255,255,0)',
  /** Ring / spinner tracks and the empty check circle. */
  track: 'rgba(255,255,255,.18)',
  trackSoft: 'rgba(255,255,255,.14)',
  ring: 'rgba(255,255,255,.28)',
  /** Keycaps (Kbd) and the round close button. */
  key: 'rgba(255,255,255,.1)',
  keyText: 'rgba(255,255,255,.62)',
  /** A neutral (chrome / navigation) button. */
  button: 'rgba(255,255,255,.09)',
  /** Generated video thumbnail. */
  thumb: '#1C1C1E',
  thumbArt: '#3A3A3C'
} as const

/**
 * The pastel options mapping (Adrian, Sat: "the same action is the same color everywhere"). Options only,
 * never status. sky = understand (Explain, Diagram, Watch) · lilac = Show me · pink = Hint.
 * The ONE primary action per surface is white + ink (PrimaryButton). Chrome and navigation stay neutral.
 */
export const actionTone = {
  explain: brand.pastel.sky,
  diagram: brand.pastel.sky,
  watch: brand.pastel.sky,
  show_me: brand.pastel.lilac,
  hint: brand.pastel.pink
} as const
export type OptionAction = keyof typeof actionTone

/** Source-kind tiles: a 16% wash of the pastel with a pastel glyph (videos keep their thumbnail). */
export const kindTone = {
  notebook: brand.pastel.skyDeep,
  repo: brand.pastel.skyDeep,
  paper: brand.pastel.pinkDeep,
  blog: brand.pastel.lilac
} as const

/**
 * Glass panels (shortcut bar, player, drawer) follow Settings → Appearance (System / Light / Dark); the notch
 * island and every card stay black like the Dynamic Island. On a glass panel use these instead of color.* /
 * fill.*: they are CSS variables (styles.css) that switch on <html data-appearance>. Not for canvas (no var()).
 */
/** The glass panel background as plain colors, for main (a window paints it before CSS loads). Keep in sync with styles.css. */
export const glassBg = { dark: 'rgba(28,28,30,0.9)', light: 'rgba(250,250,248,0.92)' } as const

export const glass = {
  bg: 'var(--glass-bg)',
  text: 'var(--glass-text)',
  label: 'var(--glass-label)',
  faint: 'var(--glass-faint)',
  hairline: 'var(--glass-hairline)',
  field: 'var(--glass-field)',
  fieldHover: 'var(--glass-field-hover)',
  rule: 'var(--glass-rule)',
  key: 'var(--glass-key)',
  keyText: 'var(--glass-key-text)',
  track: 'var(--glass-track)',
  /** The one primary action on a glass panel: white on dark, ink on light. */
  button: 'var(--glass-button)',
  buttonText: 'var(--glass-button-text)',
  /** Status on glass: the same meanings, deeper on light for contrast. */
  pass: 'var(--glass-pass)',
  offTrack: 'var(--glass-offtrack)',
  shadow: 'var(--glass-shadow)'
} as const

/** Screen dims behind surfaces. spotlight .66: Adrian asked for more contrast than the spec's .55. */
export const scrim = { spotlight: 'rgba(0,0,0,.66)', launcher: 'rgba(0,0,0,.22)' } as const

/** Copy from the brand kit. */
export const copy = {
  /** Brand moments are lowercase like the wordmark (Adrian, Sat 5 PM). Teaching copy keeps normal case. */
  name: 'miyagi',
  oneLiner: 'Turn any tutorial into an auto-graded lab.',
  launcherPlaceholder: 'ask miyagi anything',
  /** The pill / bar entry point. */
  ask: 'ask miyagi',
  passed: 'Good. Now the next one.'
} as const

/** Which bonsai cut to use at which size (see core/ui/Mark.tsx). */
export const markLevel = (px: number): 'small' | 'icon' | 'full' => (px <= 32 ? 'small' : px <= 140 ? 'icon' : 'full')

/** Pill geometry. Collapsed pill is ~300×34; cards grow downward from its center. */
export const pill = { height: 34, landingWidth: 300, maxCardWidth: 520 } as const

/** Launcher: grows out of the notch island, 640 wide (topRatio is a leftover from the mid-screen version). */
export const launcher = { width: 640, topRatio: 0.22 } as const

/** "0:00" style timestamps; "1:02:00" past an hour (long videos build part by part). */
export function clock(t: number): string {
  const s = Math.max(0, Math.round(t))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

/** A #RRGGBB token at an alpha, e.g. the kind tiles' 16% pastel wash: alpha(kindTone.paper, 0.16). */
export function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1, 7), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}
