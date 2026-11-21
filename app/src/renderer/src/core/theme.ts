/**
 * Miyagi design tokens: the brand kit (app/brand/BRAND.md, app/brand/code/theme.ts) mapped onto the
 * names the app already uses. Change colors HERE, never in feature code.
 *
 * LIGHT AND DARK (Nov 21): every surface, text, border, fill, elevation and tint token below is a CSS variable
 * (`var(--c-text)` ...), so the same token resolves per theme. The values live once, in `palette` (below); `themeCss()`
 * writes them into a <style> that core/prefs.ts injects before first paint. <html data-appearance="light|dark"> picks the
 * set. Two scopes override it:
 *   data-theme="dark"  always the dark set: the notch island, its cards, and the overlay's passive layers (Overlay.tsx),
 *                      because the real notch is black on a light desktop too.
 *   data-theme="auto"  back to the resolved appearance inside a dark scope (GlassCard: the lesson panel, account sheets).
 * Raw values (for main, which has no CSS) are `rawBg` and `glassBg`. Hex lives only in this file and styles.css.
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
  /** = hud.notch (the notch black), kept here for the brand-kit table. */
  pill: '#000000',
  /**
   * Pastels for OPTIONS only (Adrian, Sat: "4 · Pastel"): suggestion / quick-action chips, source-kind tiles,
   * the "Best" label. Ink text on them. They never mean status (green = passed, amber = off track stay as is),
   * and the chrome stays black and white. No gradients or glow.
   */
  pastel: { pink: '#F9C5D5', sky: '#C5E4F9', lilac: '#D9D2FF', pinkDeep: '#F4A7BF', skyDeep: '#9CCFF2', apricot: '#FFC4A3', mint: '#BFE6DA', peach: '#FFC4A3', sand: '#E9DFC6' }
} as const

/** The overlay follows macOS: dark HUD glass by default, light when the system is light. */
export const hud = {
  /**
   * The notch black: the island, its cards and the pill-to-sheet morphs. Pure #000 because that is what the notch's
   * hardware is (the display is off there), so the pill fuses with it. Opaque, never translucent or vibrant (nothing
   * of the desktop may show through), and the same in the light and dark app themes: the island pins data-theme="dark".
   * Relation to the app's dark windows: the windows are system gray rgb(28,28,30), a deliberate step lighter, one
   * notch up (raised rgb(37,37,39), sheet rgb(44,44,46)). So black = the island and nothing else; every window, panel
   * and sheet is gray, never #000, and no surface inside the island may paint a gray fill (use white alphas on it).
   */
  notch: '#000000',
  dark: { glass: 'rgba(28,28,30,0.72)', text: '#F4F4F5', muted: 'rgba(255,255,255,0.6)', hairline: 'rgba(255,255,255,0.12)', button: '#F4F4F5', buttonText: '#141414' },
  light: { glass: 'rgba(255,255,255,0.78)', text: '#141414', muted: 'rgba(0,0,0,0.55)', hairline: 'rgba(0,0,0,0.10)', button: '#141414', buttonText: '#F6F6F3' }
} as const


/** #RRGGBB at an alpha, as rgba() (used by the palette before `alpha` below is defined). */
function alphaHex(hex: string, a: number): string {
  const n = parseInt(hex.slice(1, 7), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

/**
 * THE palette: [dark, light] for every themed variable. One place. Names are the CSS variables without `--`.
 * Dark is the HUD (system gray 28,28,30, white alphas). Light is warm white, Apple and Notion style: the window sits
 * lowest (warm gray), content surfaces lift to white with soft ink-tinted shadows, text is the brand ink, and fills are
 * ink at low alpha. Not an inversion: shadows are warm and wide, highlights are white edges, and the greens are deeper.
 */
const INK = '20,20,20'
const SHADOW = '24,22,16'
const palette: Record<string, readonly [string, string]> = {
  // ---- text and status ----
  'c-text': [hud.dark.text, brand.ink],
  'c-label': [hud.dark.muted, `rgba(${INK},.62)`],
  'c-faint': ['rgba(255,255,255,.42)', `rgba(${INK},.42)`],
  'c-hairline': [hud.dark.hairline, `rgba(${INK},.10)`],
  'c-accent': [hud.dark.button, hud.light.button],
  'c-on-accent': [hud.dark.buttonText, hud.light.buttonText],
  'c-offtrack': [brand.offTrack, brand.ink],
  'c-offtrack-tint': [brand.offTrackTint, `rgba(${INK},.06)`],
  'c-green': [brand.pass, '#22A24B'],
  'c-green-deep': [brand.passDeep, '#187A37'],
  'c-green-tint': [brand.passTint, 'rgba(31,155,69,.12)'],
  'c-on-green': [brand.ink, brand.ink],
  'c-glass': ['rgb(28,28,30)', 'rgb(252,251,249)'],
  'c-window': ['rgb(28,28,30)', 'rgb(243,242,238)'],
  'c-white': ['#FFFFFF', brand.ink], // Tailwind's text-white / bg-white/10 in features follow the theme through this
  'c-focus': ['rgba(255,255,255,.88)', 'rgba(20,20,20,.88)'],
  // ---- which bonsai / wordmark cut shows (core/ui/Mark.tsx): the dark cut on dark, the light cut on light ----
  'mk-dark': ['inline-block', 'none'],
  'mk-light': ['none', 'inline-block'],
  // ---- layers, back to front: base (window), raised (content), overlay (sheets, popovers, menus) ----
  'l-base': ['rgb(28,28,30)', 'rgb(243,242,238)'],
  'l-raised': ['rgb(37,37,39)', '#FFFFFF'],
  'l-overlay': ['rgb(44,44,46)', '#FFFFFF'],
  // ---- fill.* ----
  'f-field': ['rgba(255,255,255,.06)', `rgba(${INK},.045)`],
  'f-field-border': ['rgba(255,255,255,.09)', `rgba(${INK},.10)`],
  'f-chip': ['rgba(255,255,255,.05)', `rgba(${INK},.04)`],
  'f-chip-hover': ['rgba(255,255,255,.1)', `rgba(${INK},.08)`],
  'f-chip-border': ['rgba(255,255,255,.08)', `rgba(${INK},.09)`],
  'f-chip-text': ['rgba(255,255,255,.72)', `rgba(${INK},.70)`],
  'f-highlight': ['rgba(255,255,255,.07)', `rgba(${INK},.05)`],
  'f-tile': ['rgba(255,255,255,.06)', `rgba(${INK},.05)`],
  'f-tile-glyph': ['rgba(255,255,255,.55)', `rgba(${INK},.5)`],
  'f-skeleton': ['rgba(255,255,255,.06)', `rgba(${INK},.06)`],
  'f-rule': ['rgba(255,255,255,.08)', `rgba(${INK},.08)`],
  'f-on-accent-key': ['rgba(0,0,0,.1)', 'rgba(255,255,255,.2)'],
  'f-track': ['rgba(255,255,255,.18)', `rgba(${INK},.14)`],
  'f-track-soft': ['rgba(255,255,255,.14)', `rgba(${INK},.10)`],
  'f-ring': ['rgba(255,255,255,.28)', `rgba(${INK},.28)`],
  'f-key': ['rgba(255,255,255,.1)', `rgba(${INK},.06)`],
  'f-key-text': ['rgba(255,255,255,.62)', `rgba(${INK},.6)`],
  'f-button': ['rgba(255,255,255,.09)', `rgba(${INK},.06)`],
  'f-thumb': ['#1C1C1E', '#E7E5DF'],
  'f-thumb-art': ['#3A3A3C', '#CFCCC3'],
  'f-group': ['rgba(255,255,255,.05)', '#FFFFFF'],
  'f-nav-active': ['rgba(255,255,255,.12)', `rgba(${INK},.07)`],
  'f-segment-on': ['rgba(255,255,255,.18)', '#FFFFFF'],
  'f-segment-track': ['rgba(255,255,255,.06)', `rgba(${INK},.06)`],
  'f-keycap': ['rgba(255,255,255,.12)', `rgba(${INK},.05)`],
  'f-keycap-border': ['rgba(255,255,255,.18)', `rgba(${INK},.13)`],
  'f-keycap-text': ['rgba(255,255,255,.78)', `rgba(${INK},.65)`],
  'f-track-next': ['rgba(255,255,255,.18)', `rgba(${INK},.14)`],
  'f-track-next-mini': ['rgba(255,255,255,.24)', `rgba(${INK},.2)`],
  'f-practicing': ['rgba(255,255,255,.55)', `rgba(${INK},.5)`],
  'f-toggle-off': ['rgba(255,255,255,.16)', `rgba(${INK},.16)`],
  // ---- surface.* ----
  's-panel': ['rgba(28,28,30,0.96)', 'rgba(253,252,250,0.97)'],
  's-sheet': ['#2C2C2E', '#FFFFFF'],
  's-row': ['rgba(255,255,255,.06)', `rgba(${INK},.04)`],
  's-row-hover': ['rgba(255,255,255,.1)', `rgba(${INK},.07)`],
  's-well': ['rgba(0,0,0,.26)', `rgba(${INK},.05)`],
  's-border': ['rgba(255,255,255,.12)', `rgba(${INK},.09)`],
  // ---- elevation: soft, wide, low-opacity stacks. Light shadows are warm ink, not black ----
  'e-raised': ['0 1px 1px rgba(0,0,0,.3), 0 2px 4px rgba(0,0,0,.22), 0 6px 14px rgba(0,0,0,.2)', `0 0 0 .5px rgba(${SHADOW},.05), 0 1px 2px rgba(${SHADOW},.05), 0 4px 12px rgba(${SHADOW},.06)`],
  'e-overlay': ['0 1px 2px rgba(0,0,0,.3), 0 4px 10px rgba(0,0,0,.22), 0 12px 28px rgba(0,0,0,.24)', `0 0 0 .5px rgba(${SHADOW},.06), 0 2px 5px rgba(${SHADOW},.05), 0 10px 26px rgba(${SHADOW},.09), 0 22px 48px rgba(${SHADOW},.06)`],
  'e-panel': ['0 1px 2px rgba(0,0,0,.3), 0 6px 14px rgba(0,0,0,.24), 0 18px 40px rgba(0,0,0,.3), 0 36px 80px rgba(0,0,0,.32)', `0 0 0 .5px rgba(${SHADOW},.07), 0 3px 8px rgba(${SHADOW},.06), 0 16px 36px rgba(${SHADOW},.1), 0 40px 88px rgba(${SHADOW},.13)`],
  'e-card': [`0 0 0 0.5px ${hud.notch}, 0 2px 4px rgba(0,0,0,.3), 0 12px 28px rgba(0,0,0,.34), 0 32px 72px rgba(0,0,0,.42)`, `0 0 0 .5px rgba(${SHADOW},.08), 0 3px 8px rgba(${SHADOW},.07), 0 18px 40px rgba(${SHADOW},.12), 0 44px 96px rgba(${SHADOW},.16)`],
  // ---- highlight edges ----
  'h-top': ['inset 0 1px 0 rgba(255,255,255,.1)', 'inset 0 1px 0 rgba(255,255,255,.95)'],
  'h-top-soft': ['inset 0 1px 0 rgba(255,255,255,.06)', 'inset 0 1px 0 rgba(255,255,255,.8)'],
  'h-on-light': ['inset 0 1px 0 rgba(255,255,255,.55)', 'inset 0 1px 0 rgba(255,255,255,.3)'],
  'h-well': ['inset 0 1px 3px rgba(0,0,0,.4)', `inset 0 1px 3px rgba(${SHADOW},.12)`],
  'h-key-lip': ['inset 0 -1px 0 rgba(0,0,0,.35)', `inset 0 -1px 0 rgba(${SHADOW},.16)`],
  // ---- hover and press tints (.mg-press): neutral controls lighten on dark, darken on light ----
  'mg-tint-hover': ['rgba(255,255,255,.06)', `rgba(${INK},.045)`],
  'mg-tint-press': ['rgba(255,255,255,.1)', `rgba(${INK},.09)`],
  // a white or pastel fill (.mg-press-light) darkens in both themes; an ink fill (.mg-press-accent) lightens in light
  'mg-tint-hover-fill': ['rgba(0,0,0,.045)', `rgba(${INK},.05)`],
  'mg-tint-press-fill': ['rgba(0,0,0,.09)', `rgba(${INK},.10)`],
  'mg-tint-hover-accent': ['rgba(0,0,0,.045)', 'rgba(255,255,255,.1)'],
  'mg-tint-press-accent': ['rgba(0,0,0,.09)', 'rgba(255,255,255,.18)'],
  // ---- soft pastel tints (see `tone`): dark = a 16% wash with the pastel as text; light = a pale wash with a deep text ----
  'tone-sky-bg': [alphaHex(brand.pastel.sky, 0.16), '#DDEEF9'],
  'tone-sky-fg': [brand.pastel.sky, '#2B6C9B'],
  'tone-lilac-bg': [alphaHex(brand.pastel.lilac, 0.16), '#E7E2FB'],
  'tone-lilac-fg': [brand.pastel.lilac, '#5848B0'],
  'tone-pink-bg': [alphaHex(brand.pastel.pink, 0.16), '#FADCE6'],
  'tone-pink-fg': [brand.pastel.pink, '#A23C66'],
  'tone-mint-bg': [alphaHex(brand.pastel.mint, 0.16), '#D8F0EA'],
  'tone-mint-fg': [brand.pastel.mint, '#2A7468'],
  'tone-peach-bg': [alphaHex(brand.pastel.peach, 0.16), '#FCE3D2'],
  'tone-peach-fg': [brand.pastel.peach, '#9A4E1C'],
  'tone-sand-bg': [alphaHex(brand.pastel.sand, 0.14), '#EFE8D8'],
  'tone-sand-fg': [brand.pastel.sand, '#77683F'],
  // ---- glass panels (theme.glass): the same surfaces, as before ----
  'glass-bg': ['rgba(28, 28, 30, 0.96)', 'rgba(252, 251, 249, 0.97)'],
  'glass-text': [hud.dark.text, brand.ink],
  'glass-label': ['rgba(255,255,255,.6)', 'rgba(0,0,0,.56)'],
  'glass-faint': ['rgba(255,255,255,.42)', 'rgba(0,0,0,.38)'],
  'glass-hairline': ['rgba(255,255,255,.12)', 'rgba(0,0,0,.1)'],
  'glass-field': ['rgba(255,255,255,.06)', 'rgba(0,0,0,.045)'],
  'glass-field-hover': ['rgba(255,255,255,.1)', 'rgba(0,0,0,.08)'],
  'glass-rule': ['rgba(255,255,255,.08)', 'rgba(0,0,0,.08)'],
  'glass-key': ['rgba(255,255,255,.1)', 'rgba(0,0,0,.07)'],
  'glass-key-text': ['rgba(255,255,255,.62)', 'rgba(0,0,0,.55)'],
  'glass-track': ['rgba(255,255,255,.18)', 'rgba(0,0,0,.14)'],
  'glass-button': [hud.dark.button, hud.light.button],
  'glass-button-text': [hud.dark.buttonText, hud.light.buttonText],
  'glass-pass': [brand.pass, brand.passText],
  'glass-offtrack': [brand.offTrack, brand.ink],
  'glass-shadow': ['0 1px 2px rgba(0, 0, 0, 0.3), 0 6px 14px rgba(0, 0, 0, 0.24), 0 18px 40px rgba(0, 0, 0, 0.3), 0 36px 80px rgba(0, 0, 0, 0.32)', `0 0 0 .5px rgba(${SHADOW},.07), 0 3px 8px rgba(${SHADOW},.06), 0 16px 36px rgba(${SHADOW},.1)`]
}

/** One variable set as CSS declarations (0 = dark, 1 = light). */
function decls(i: 0 | 1): string {
  return Object.entries(palette)
    .map(([k, v]) => `--${k}:${v[i]};`)
    .join('')
}

/**
 * The theme's stylesheet (injected by core/prefs.ts before first paint; styles.css has no copy). Dark is the default,
 * light follows <html data-appearance="light">. `data-theme="dark"` pins the dark set below it (the island, the
 * overlay); `data-theme="auto"` hands a subtree back to the resolved appearance. Tailwind's --color-white follows c-white.
 */
export function themeCss(): string {
  const dark = `${decls(0)}--color-white:var(--c-white);color-scheme:dark;`
  const light = `${decls(1)}--color-white:var(--c-white);color-scheme:light;`
  return [
    `:root,[data-theme="dark"],:root[data-appearance="dark"] [data-theme="auto"]{${dark}}`,
    `:root[data-appearance="light"],:root[data-appearance="light"] [data-theme="auto"]{${light}}`
  ].join('\n')
}

/** Raw window colors for main (a window paints before any CSS loads): opaque. Same values as `l-base` in `palette`. */
export const rawBg = { dark: palette['l-base'][0], light: palette['l-base'][1] } as const
/** fill.thumb as raw hex per theme, for colour maths and canvas (fill.thumb itself is a var()). */
export const rawThumb = { dark: palette['f-thumb'][0], light: palette['f-thumb'][1] } as const

/**
 * What components use (dark HUD). `accent` is the "active / interactive" color and is WHITE
 * (it used to be system blue): progress, focus, selected, primary buttons. Pair a white fill with `onAccent` text.
 */
export const color = {
  accent: 'var(--c-accent)',
  onAccent: 'var(--c-on-accent)',
  /** Off track: white, shown as a ring (the name stays `amber` so call sites don't change). */
  amber: 'var(--c-offtrack)',
  amberTint: 'var(--c-offtrack-tint)',
  /** Passed. Nothing else is green. */
  green: 'var(--c-green)',
  greenDeep: 'var(--c-green-deep)',
  greenTint: 'var(--c-green-tint)',
  /** Watching (status dot). */
  gray: brand.watching,
  text: 'var(--c-text)',
  label: 'var(--c-label)',
  faint: 'var(--c-faint)',
  hairline: 'var(--c-hairline)',
  /** The notch pill and the island: always black. */
  island: hud.notch,
  /**
   * Panels on the dark HUD (the launcher / ask panel). CSS can't blur other apps in Electron, so this is far more
   * opaque than the kit's .72: at .90 the code under the ask panel still showed through (Michael's tests 2-3, A13).
   * At .96 text behind the launcher still showed next to its rows (Michael's Devpost shots), so it is now solid.
   */
  glass: 'var(--c-glass)',
  /** v2: the ink tick / text on a green (passed) circle. */
  onGreen: 'var(--c-on-green)',
  /** v2: an app window's opaque body (Onboarding, Library, Progress). Same as surface.window. */
  window: 'var(--c-window)'
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

/**
 * The island's two shadows. Anything that hands over to the island (the launcher, settings) must match them exactly.
 * Polish (UI-POLISH-SPEC 2): layered, not one blur. A tight contact shadow, a mid shadow and a wide ambient one, so the
 * black pill sits ON the screen instead of floating in a haze. Both have the SAME four layers, because Settings and the
 * launcher still animate boxShadow between them in their pill-to-sheet morphs (pre-existing), and motion interpolates a
 * shadow string layer by layer: equal counts keep that morph smooth. Moving those morphs to an opacity crossfade of two
 * shadow layers (brand: transform and opacity only) is a follow-up for those lanes. The first layer is a 0.5 px ring in the
 * notch black itself (it was a 9% white hairline, which drew a grey edge the real notch doesn't have).
 */
export const shadows = {
  pill: `0 0 0 0.5px ${hud.notch}, 0 1px 2px rgba(0,0,0,.32), 0 4px 10px rgba(0,0,0,.22), 0 10px 24px rgba(0,0,0,.14)`,
  /** The card / sheet shadow: follows the theme (same four layers in both, so the pill-to-sheet morph still interpolates). */
  card: 'var(--e-card)'
} as const

/** Neutral fills on the black island / dark HUD: white at low alphas, nothing else (brand: no extra hues). */
export const fill = {
  field: 'var(--f-field)',
  fieldBorder: 'var(--f-field-border)',
  chip: 'var(--f-chip)',
  chipHover: 'var(--f-chip-hover)',
  chipBorder: 'var(--f-chip-border)',
  chipText: 'var(--f-chip-text)',
  highlight: 'var(--f-highlight)',
  tile: 'var(--f-tile)',
  tileGlyph: 'var(--f-tile-glyph)',
  skeleton: 'var(--f-skeleton)',
  rule: 'var(--f-rule)',
  /** A keycap sitting on a white (accent) or pastel button: ink at 10%. */
  onAccentKey: 'var(--f-on-accent-key)',
  clear: 'rgba(255,255,255,0)',
  /** Ring / spinner tracks and the empty check circle. */
  track: 'var(--f-track)',
  trackSoft: 'var(--f-track-soft)',
  ring: 'var(--f-ring)',
  /** Keycaps (Kbd) and the round close button. */
  key: 'var(--f-key)',
  keyText: 'var(--f-key-text)',
  /** A neutral (chrome / navigation) button. */
  button: 'var(--f-button)',
  /** Generated video thumbnail. */
  thumb: 'var(--f-thumb)',
  thumbArt: 'var(--f-thumb-art)',
  // ---- v2 (W0-2) ----
  /** A grouped block of rows (Set-General). */
  group: 'var(--f-group)',
  hairline: 'var(--c-hairline)',
  /** The selected sidebar row (Settings, Library). */
  navActive: 'var(--f-nav-active)',
  /** The selected segment of a Segmented control, and its track. */
  segmentOn: 'var(--f-segment-on)',
  segmentTrack: 'var(--f-segment-track)',
  /** A keycap on a dark surface (core/ui/Keycap.tsx). On a pastel or white button it's onAccentKey. */
  keycap: 'var(--f-keycap)',
  keycapBorder: 'var(--f-keycap-border)',
  keycapText: 'var(--f-keycap-text)',
  /** Step dots / meters: a step not reached yet. */
  trackNext: 'var(--f-track-next)',
  /** Les-Mini's step bars: a step not reached yet, a touch brighter on the small 4 px bar. */
  trackNextMini: 'var(--f-track-next-mini)',
  /** A skill being practiced (Prog-Progress-Window): white at 55%, never a hue. */
  practicing: 'var(--f-practicing)',
  /** A Toggle that is off. */
  toggleOff: 'var(--f-toggle-off)'
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
export const glassBg = { dark: palette['glass-bg'][0], light: palette['glass-bg'][1] } as const

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

/**
 * Screen dims behind surfaces. spotlight .66: Adrian asked for more contrast than the spec's .55; it's for Show me
 * (and video lessons). spotlightSoft .16: a text lesson's "type here" target, where the learner's own code and
 * terminal must stay readable around the hole (Michael's audit A6: at .66 they weren't; at most .2).
 */
export const scrim = { spotlight: 'rgba(0,0,0,.66)', spotlightSoft: 'rgba(0,0,0,.16)', launcher: 'rgba(0,0,0,.22)' } as const

/** Never name an editor we don't support: a label naming the unsupported fork becomes "your editor"; none at all is VS Code. */
const UNSUPPORTED_EDITOR = /cursor/i
export function editorName(label?: string | null): string {
  const t = (label ?? '').trim()
  if (!t) return 'VS Code'
  return UNSUPPORTED_EDITOR.test(t) ? 'your editor' : t
}

/** Copy from the brand kit. */
export const copy = {
  /** v2 (W0-2): the guard every editor label goes through (card.setup.editorLabel, health rows...). */
  editorName,
  /** v2: Settings → General caption. The notch island stays black in both themes, like the real notch. */
  appearanceCaption: 'Applies to every miyagi window. The notch pill stays black.',
  /** Brand moments are lowercase like the wordmark (Adrian, Sat 5 PM). Teaching copy keeps normal case. */
  name: 'miyagi',
  oneLiner: 'Turn any tutorial into an auto-graded lab.',
  launcherPlaceholder: 'ask miyagi anything',
  /** The pill / bar entry point. */
  ask: 'ask miyagi',
  /** Michael, test 7: "Good. Now the next one." read as filler; the step's own result says more. */
  passed: 'Step done.'
} as const

// ---------------------------------------------------------------------------------------------------------------
// v2 tokens (miyagi-v2 BUILD-PLAN W0-2). Additive: everything above keeps its name and value. Mockup literals that
// differ from BRAND.md (the mockups' sky #BFE3F5, ⌥ keycaps) lose to BRAND.md and bridge.platform.keys.
// ---------------------------------------------------------------------------------------------------------------

/**
 * Status, in one place (Les-* / Prog-* / Onb-*). passed is the ONLY green. notYet has no hue: a hollow ring in `notYet`
 * with the word "Not yet". watching / unknown / offline are the gray. Never a pastel, never a glow.
 */
export const status = {
  passed: brand.pass,
  /** Green text on a paper (light) surface. */
  passedOnPaper: brand.passText,
  notYet: 'var(--c-offtrack)',
  /** The ring's stroke on paper. */
  notYetOnPaper: brand.ink,
  watching: brand.watching,
  unknown: brand.watching,
  offline: brand.watching,
  /** An empty / pending ring (a step not started, a row not checked yet). */
  ring: 'var(--f-ring)'
} as const

/** Dark surfaces, back to front: the lesson panel, an app window's body, a sheet inside it, a row on any of them. */
export const surface = {
  /** The lesson panel docked beside the editor, the island's cards' glass twin (Les-Working). */
  panel: 'var(--s-panel)',
  /** App windows (Onboarding, Library, Progress): opaque, so nothing shows through. Same as color.window. */
  window: 'var(--c-window)',
  /** A sheet or popover inside a window (Onb-Checklist-Mixed). */
  sheet: 'var(--s-sheet)',
  /** A grouped row on any of the above (Set-General, Home-Library). */
  row: 'var(--s-row)',
  rowHover: 'var(--s-row-hover)',
  /** Polish: a recessed box (the code to type, a text field): darker than the surface it sits in, never lighter. */
  well: 'var(--s-well)',
  border: 'var(--s-border)',
  /** Polish: layered (contact + mid + ambient), see `elevation`. Same names, so every caller gets the depth. */
  shadow: 'var(--e-panel)',
  shadowSmall: 'var(--e-overlay)'
} as const

/**
 * Light surfaces (Plan-Pricing, the dmg art, web pages): the brand's paper and ink. Buttons are ink with paper text,
 * status green is passText, nothing else gets a hue.
 */
export const paper = {
  bg: brand.paper,
  surface: brand.surface,
  ink: brand.ink,
  muted: 'rgba(20,20,20,.64)',
  label: 'rgba(20,20,20,.6)',
  faint: 'rgba(20,20,20,.42)',
  hairline: 'rgba(20,20,20,.1)',
  border: 'rgba(20,20,20,.16)',
  group: 'rgba(20,20,20,.08)',
  field: 'rgba(20,20,20,.04)',
  button: brand.ink,
  buttonText: brand.paper,
  pass: brand.passText,
  shadow: '0 12px 32px rgba(20,20,20,.08)',
  shadowSmall: '0 1px 2px rgba(20,20,20,.12)'
} as const

/**
 * The lesson panel's dock (Les-Working: right 16, top 52 at 1440x900, 360 wide; Les-Mini: the collapsed pill 380).
 * top: px from the display's top (the menu bar plus a gap); core/dock.ts keeps it under the work area's top.
 */
export const dock = { w: 360, inset: 16, gap: 10, miniW: 380, top: 52 } as const

/** App windows (decision 4: an explicit exception to "born from the island"; a Dock icon while open). Points. */
export const windowSize = {
  onboarding: { w: 720, h: 560 },
  library: { w: 1280, h: 820 },
  lessonDetail: { w: 960, h: 700 },
  progress: { w: 1100, h: 760 },
  account: { w: 720, h: 560 },
  /** The login (features/auth): the first-run size, so intro → login → setup stays in one spot (main/features/onboarding.ts). */
  auth: { w: 944, h: 640 },
  pricing: { w: 1200, h: 760 },
  /** Settings stays the grow-from-pill sheet; this is its clamp (A4). */
  settings: { w: 912, h: 576 }
} as const
export type AppWindowName = keyof typeof windowSize

/** v2 type scale (the mockups use 11 for keycaps and captions). The brand sizes 13 / 15 / 20 / 28 are all in here. */
export const type2 = { micro: 11, xs: 12, sm: 13, md: 14, body: 15, lg: 17, xl: 20, xxl: 28 } as const
/** v2 radii (the brand's 14 / 20 / 28 plus the small ones the mockups use). */
export const radius2 = { keycap: 6, control: 8, row: 10, card: 12, chip: 14, group: 16, panel: 20, sheet: 24, launcher: 28, round: 999 } as const

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

// ---------------------------------------------------------------------------------------------------------------
// Polish (UI-POLISH-SPEC.md): depth, press and motion tokens. Neutral only: black shadows, white highlights at low
// alpha. No hue, no glow (a glow is a colored or white OUTER blur; nothing here blurs light outward).
// ---------------------------------------------------------------------------------------------------------------

/**
 * Elevation, back to front. Each level is a layered stack (Comeau / Ahlin: several shadows whose offset and blur double
 * while the alpha falls), tuned for a dark HUD where a single soft shadow disappears.
 *   flat     a row or well on a surface: nothing
 *   raised   a button, a selected segment, a keycap-sized thing lifted 1 to 2 px
 *   overlay  a sheet, a popover, a menu
 *   panel    the docked lesson panel, the island's cards (surface.shadow)
 */
export const elevation = {
  flat: 'none',
  raised: 'var(--e-raised)',
  overlay: 'var(--e-overlay)',
  panel: 'var(--e-panel)'
} as const

/**
 * Edges that make a dark surface read as a lit object (macOS draws the same: a brighter top edge, a hairline all round).
 *   top       the top inner highlight on a raised dark surface (panel, sheet, quiet button)
 *   topSoft   the same on a grouped block or row, quieter
 *   onLight   the top highlight on a white or pastel fill (primary, option tiles): a faint white line on the top edge
 *   base      a faint ink line on the bottom inner edge of a white or pastel fill, so it reads as a pressable slab
 *   well      a recessed box (code, fields): a short inner shadow from the top edge, the surface pressed IN
 */
export const highlight = {
  top: 'var(--h-top)',
  topSoft: 'var(--h-top-soft)',
  onLight: 'var(--h-on-light)',
  base: 'inset 0 -1px 0 rgba(0,0,0,.1)',
  well: 'var(--h-well)',
  /** A keycap's bottom lip: the key stands on the surface. */
  keyLip: 'var(--h-key-lip)'
} as const

/**
 * Hover and press tints, painted by a layer over the control whose OPACITY animates (styles.css .mg-press), so no
 * color or filter ever animates. `onDark` lightens a neutral control; `onLight` darkens a white or pastel one.
 * `onInk` lightens the ink GlassPrimary under light glass (styles.css .mg-glass); an ink fill needs a stronger white.
 */
export const tint = {
  hoverOnDark: 'rgba(255,255,255,.06)',
  pressOnDark: 'rgba(255,255,255,.1)',
  hoverOnLight: 'var(--mg-tint-hover-fill)',
  pressOnLight: 'var(--mg-tint-press-fill)',
  hoverOnInk: 'rgba(255,255,255,.08)',
  pressOnInk: 'rgba(255,255,255,.14)'
} as const

/** The keyboard focus ring (focus-visible only, never on a mouse click): white on dark, ink on paper, 2 px, 2 px out. */
export const focus = { dark: 'var(--c-focus)', paper: 'rgba(20,20,20,.88)', width: 2, offset: 2 } as const

/**
 * Durations (seconds) and curves for the few tweens left (opacity fades, the tint layer). Everything that MOVES uses
 * `spring`. ease.out is a strong ease-out (Kowalski: enter fast, settle slow); never ease-in on an enter.
 */
export const duration = { instant: 0.08, fast: 0.12, base: 0.18, slow: 0.24 } as const
export const ease = { out: [0.23, 1, 0.32, 1], inOut: [0.77, 0, 0.175, 1] } as const

/**
 * Press: scale to .97 on the house spring (fast enough at this stiffness: ~90% in 0.13 s) and back with the same
 * spring, so a quick click still finishes the dip. Big targets (the option tiles) go to .96; never below .95.
 */
export const press = { scale: 0.97, scaleLarge: 0.96, transition: spring } as const

/**
 * Lists that appear together (onboarding rows, a settings section): each child rises 6 px and fades in, 35 ms apart,
 * the stagger capped at 8 children so a long list never makes the learner wait. Reduced motion: fade only (MotionConfig).
 */
export const stagger = { each: 0.035, cap: 8, rise: 6 } as const

// ---------------------------------------------------------------------------------------------------------------
// Nov 21: layers and soft pastel tints (both themes).
// ---------------------------------------------------------------------------------------------------------------

/**
 * Surface layering, back to front. `base` is the window, `raised` is content lifted off it (a card, a group), `overlay`
 * is a sheet, popover or menu above that. Each pairs a fill with its shadow and top edge (use `layerStyle`). Hover or
 * press moves an interactive surface ONE level up (raised to overlay; .mg-lift in styles.css), never more.
 */
export const layer = {
  base: { background: 'var(--l-base)', boxShadow: 'none' },
  raised: { background: 'var(--l-raised)', boxShadow: `${highlight.topSoft}, inset 0 0 0 1px ${surface.border}, ${elevation.raised}` },
  overlay: { background: 'var(--l-overlay)', boxShadow: `${highlight.top}, inset 0 0 0 1px ${surface.border}, ${elevation.overlay}` }
} as const
export type Layer = keyof typeof layer

/**
 * Soft pastel tints (Michael, Nov 21: pastels are no longer only for options). `bg` is a pale wash, `fg` the text or icon
 * on it, readable in both themes. Use for lesson and tool tags, skill tracks, section icons and selected states.
 * Never for status: green still means ONLY passed, "not yet" stays hueless, no red, no yellow. `solid` is the brand
 * pastel itself (a fixed hex, for an option fill with ink text, as actionTone).
 *   sky     tools, notebooks, understand      lilac  show me, practice       pink   hints, people
 *   mint    (teal, not the pass green) skills  peach  warm tracks, new        sand   neutral warm, everything else
 */
export const tone = {
  sky: { bg: 'var(--tone-sky-bg)', fg: 'var(--tone-sky-fg)', solid: brand.pastel.sky },
  lilac: { bg: 'var(--tone-lilac-bg)', fg: 'var(--tone-lilac-fg)', solid: brand.pastel.lilac },
  pink: { bg: 'var(--tone-pink-bg)', fg: 'var(--tone-pink-fg)', solid: brand.pastel.pink },
  mint: { bg: 'var(--tone-mint-bg)', fg: 'var(--tone-mint-fg)', solid: brand.pastel.mint },
  peach: { bg: 'var(--tone-peach-bg)', fg: 'var(--tone-peach-fg)', solid: brand.pastel.peach },
  sand: { bg: 'var(--tone-sand-bg)', fg: 'var(--tone-sand-fg)', solid: brand.pastel.sand }
} as const
export type Tone = keyof typeof tone
export const toneNames = Object.keys(tone) as Tone[]
/** A stable tone for any string (a track, a tool, a tag): the same name always gets the same color. */
export function toneFor(key: string): Tone {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
  return toneNames[h % toneNames.length]
}
