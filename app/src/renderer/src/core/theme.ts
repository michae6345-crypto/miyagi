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
 *  - App text in Bricolage Grotesque (bundled, styles.css @font-face; Michael's call, Nov 24), system font as fallback. No Inter.
 */
/**
 * Motion tokens (the springs, fades, beat, press and stagger) live in core/ui/motionTokens.ts (helpers beside them in core/ui/motion.ts), the single source of truth
 * (docs/MOTION.md). Re-exported here so `import { spring } from '../core/theme'` keeps working.
 */
export { beat, duration, ease, fade, press, spring, springOut, stagger } from './ui/motionTokens'

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
  pastel: { pink: '#F9C5D5', sky: '#C5E4F9', lilac: '#D9D2FF', pinkDeep: '#F4A7BF', skyDeep: '#9CCFF2', apricot: '#FFC4A3', mint: '#BFE6DA', peach: '#FFC4A3', sand: '#E9DFC6',
    /** Option fills (Adrian, Nov 21): Diagram and Watch each get their own pastel. peachLight is lighter than the tone peach (that one is the apricot that read orange). */
    seafoam: '#BFEBE6',
    peachLight: '#FBD5BE'
  }
} as const

/** The overlay follows macOS: dark HUD glass by default, light when the system is light. */
export const hud = {
  /**
   * The notch black: the island, its cards and the pill-to-sheet morphs. Pure #000 because that is what the notch's
   * hardware is (the display is off there), so the pill fuses with it. Opaque, never translucent or vibrant (nothing
   * of the desktop may show through), and the same in the light and dark app themes: the island pins data-theme="dark".
   * Relation to the app's dark windows: they are one warm-neutral ramp a few steps above black (layout lane, Nov 22:
   * chrome #141413, content #1B1B1A, card #222221, popover #2C2B2A; R−B ≤ 1 so nothing reads blue or brown). So black =
   * the island and nothing else; every window, panel and sheet is gray, never #000, and no surface inside the island
   * may paint a gray fill (use white alphas on it).
   */
  notch: '#000000',
  /**
   * The open notch panel's glow: black at the notch, deep green at the bottom (Michael, Nov 22: Clicky does a blue that
   * fades into black; ours is green). A try-out: tune or drop it here only.
   */
  // Nov 22, round 2: the brand mint (pastel.mint #BFE6DA) as a soft glow rising from the bottom edge, so it fits the
  // app's pastels and melts into the black instead of banding.
  notchGlow: 'radial-gradient(130% 100% at 50% 130%, rgba(150,228,200,.62) 0%, rgba(150,228,200,.26) 42%, rgba(0,0,0,0) 80%)',
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
/** Text in the app windows' dark theme (the island's pinned scope keeps `hud.dark`; see themeCss). */
const APP_DARK = { text: '#ECEBE8', label: '#A3A29E' } as const
const SHADOW = '24,22,16'
const palette: Record<string, readonly [string, string]> = {
  // ---- text and status ----
  // The app windows' own text pair (layout lane, Nov 22): dark #ECEBE8 / #A3A29E, light the website's ink and muted.
  // The island keeps hud.dark.text / hud.dark.muted: themeCss() pins those two back inside [data-theme="dark"].
  'c-text': [APP_DARK.text, brand.ink],
  'c-label': [APP_DARK.label, brand.inkMuted],
  // Dark faint is a solid warm gray (layout lane, Nov 22): white .42 was about 4.1:1 on the #1B1B1A pane and 3.8:1 on
  // #222221 cards, under 4.5:1 for the 12 px meta (durations, step counts); #858480 is about 4.8:1 on the pane.
  // Light faint: the website's #8F8F88 is 3.0:1 on the cream pane, so the app uses #6F6F68 (4.7:1 on #F6F6F3, test/lightContrast.test.ts).
  'c-faint': ['#858480', '#6F6F68'],
  'c-hairline': [hud.dark.hairline, `rgba(${INK},.10)`],
  'c-accent': [hud.dark.button, hud.light.button],
  'c-on-accent': [hud.dark.buttonText, hud.light.buttonText],
  // Ink on a solid option pastel: fixed in both appearances (c-on-accent is paper in light, unreadable on a pastel).
  'c-on-pastel': [brand.ink, brand.ink],
  'c-offtrack': [brand.offTrack, brand.ink],
  'c-offtrack-tint': [brand.offTrackTint, `rgba(${INK},.06)`],
  'c-green': [brand.pass, '#22A24B'],
  'c-green-deep': [brand.passDeep, '#187A37'],
  /** Green as text: the pass green on dark, the deep green on light (the fill green is 3.3:1 on white). */
  'c-green-text': [brand.pass, '#187A37'],
  'c-green-tint': [brand.passTint, 'rgba(31,155,69,.12)'],
  'c-on-green': [brand.ink, brand.ink],
  // Glass (launcher, lesson panel, account menu): the same neutral ramp as the windows (it was the cool iOS 28,28,30,
  // which read blue next to the warm windows).
  'c-glass': ['rgb(30,30,29)', 'rgb(252,251,249)'],
  'c-window': ['#141413', '#F1EFE9'],
  'c-white': ['#FFFFFF', brand.ink], // Tailwind's text-white / bg-white/10 in features follow the theme through this
  'c-focus': ['rgba(255,255,255,.88)', 'rgba(20,20,20,.88)'],
  // ---- which bonsai / wordmark cut shows (core/ui/Mark.tsx): the dark cut on dark, the light cut on light ----
  'mk-dark': ['inline-block', 'none'],
  'mk-light': ['none', 'inline-block'],
  // ---- layers, back to front: base (window chrome, the sidebar), raised (the content pane), overlay (cards on it) ----
  // Layout lane (Nov 22, Linear / Notion dark): one warm-neutral ramp with very low chroma (R−B ≤ 1; more read muddy),
  // each step about 7 levels apart.
  // Light is the website's cream (Michael, Nov 22): the content canvas is the site's paper #F6F6F3, the sidebar and window
  // chrome a step deeper (#F1EFE9, also on the site), cards white with a hairline border.
  'l-base': ['#141413', '#F1EFE9'],
  'l-raised': ['#1B1B1A', brand.paper],
  'l-overlay': ['#222221', '#FFFFFF'],
  // Edges: the pane's own outline (no divider beside the sidebar: the tone step separates them) and a card's border.
  'l-edge': ['rgba(255,255,255,.06)', `rgba(${INK},.07)`],
  'l-border': ['rgba(255,255,255,.08)', `rgba(${INK},.08)`],
  // The fine dot grid on the content pane (PR #242). Neutral and quiet; PANEL fades it out away from the top.
  'd-dot': ['rgba(255,255,255,.05)', `rgba(${INK},.06)`],
  // ---- v4 frame (Adrian's ui-next mock, Nov 23: docs/ui-next/mock/app.css, its paper-cream variant) ----
  // The sidebar and the page share one tone (cream in light, the pane gray in dark) with a hairline between them; the
  // hairline, hover, selected-row, fill and track steps are the mock's warm-ink alphas. Read through `v4c` below.
  // Dark: the sidebar sits one step above the page like the mock's (rgb 32,31,29 over 25,24,22), held at #1D1D1B so the
  // faint ink (#858480: "3 of 8", the section labels) keeps 4.5:1 on it (test/v4Shell.test.ts). Light: one cream for both.
  'v4-side': ['#1D1D1B', brand.paper],
  'v4-page': ['#1B1B1A', brand.paper],
  'v4-card': ['#242422', '#FFFFFF'],
  'v4-hair': ['rgba(255,255,255,.085)', 'rgba(40,38,33,.09)'],
  'v4-hair2': ['rgba(255,255,255,.13)', 'rgba(40,38,33,.14)'],
  'v4-hover': ['rgba(255,255,255,.05)', 'rgba(40,38,33,.045)'],
  'v4-active': ['rgba(255,255,255,.085)', 'rgba(40,38,33,.075)'],
  'v4-fill': ['rgba(255,255,255,.05)', 'rgba(40,38,33,.04)'],
  'v4-fill2': ['rgba(255,255,255,.085)', 'rgba(40,38,33,.075)'],
  'v4-track': ['rgba(255,255,255,.16)', 'rgba(40,38,33,.13)'],
  'v4-ghost': ['rgba(255,255,255,.22)', 'rgba(40,38,33,.22)'],
  'v4-e1': ['0 0 0 1px rgba(255,255,255,.07), 0 1px 2px rgba(0,0,0,.3)', '0 0 0 1px rgba(15,15,15,.045), 0 1px 2px rgba(15,15,15,.05)'],
  'v4-e2': ['0 0 0 1px rgba(255,255,255,.07), 0 2px 6px rgba(0,0,0,.3), 0 10px 24px rgba(0,0,0,.28)', '0 0 0 1px rgba(15,15,15,.05), 0 2px 5px rgba(15,15,15,.06), 0 8px 20px rgba(15,15,15,.06)'],
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
  'f-on-pastel-key': ['rgba(0,0,0,.1)', 'rgba(0,0,0,.1)'],
  'f-track': ['rgba(255,255,255,.18)', `rgba(${INK},.14)`],
  'f-track-soft': ['rgba(255,255,255,.14)', `rgba(${INK},.10)`],
  'f-ring': ['rgba(255,255,255,.28)', `rgba(${INK},.28)`],
  'f-key': ['rgba(255,255,255,.1)', `rgba(${INK},.06)`],
  'f-key-text': ['rgba(255,255,255,.62)', `rgba(${INK},.6)`],
  'f-button': ['rgba(255,255,255,.09)', `rgba(${INK},.06)`],
  'f-thumb': ['#181715', '#E7E5DF'],
  'f-thumb-art': ['#3A3834', '#CFCCC3'],
  'f-group': ['rgba(255,255,255,.04)', '#FFFFFF'],
  'f-nav-active': ['rgba(255,255,255,.12)', `rgba(${INK},.07)`],
  /** The app sidebar's selected row: a quiet fill, no hue, no edge (Linear's dimmed sidebar). */
  'f-nav-on': ['rgba(255,255,255,.07)', `rgba(${INK},.055)`],
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
  's-panel': ['rgba(30,30,29,0.96)', 'rgba(253,252,250,0.97)'],
  's-sheet': ['#2C2B2A', '#FFFFFF'],
  's-row': ['rgba(255,255,255,.06)', `rgba(${INK},.04)`],
  's-row-hover': ['rgba(255,255,255,.1)', `rgba(${INK},.07)`],
  's-well': ['rgba(0,0,0,.26)', `rgba(${INK},.05)`],
  's-border': ['rgba(255,255,255,.12)', `rgba(${INK},.09)`],
  // ---- elevation: soft, wide, low-opacity stacks. Light shadows are warm ink, not black ----
  'e-raised': ['0 1px 1px rgba(0,0,0,.3), 0 2px 4px rgba(0,0,0,.22), 0 6px 14px rgba(0,0,0,.2)', `0 0 0 .5px rgba(${SHADOW},.05), 0 1px 2px rgba(${SHADOW},.05), 0 4px 12px rgba(${SHADOW},.06)`],
  'e-overlay': ['0 1px 2px rgba(0,0,0,.3), 0 4px 10px rgba(0,0,0,.22), 0 12px 28px rgba(0,0,0,.24)', `0 0 0 .5px rgba(${SHADOW},.06), 0 2px 5px rgba(${SHADOW},.05), 0 10px 26px rgba(${SHADOW},.09), 0 22px 48px rgba(${SHADOW},.06)`],
  'e-panel': ['0 1px 2px rgba(0,0,0,.3), 0 6px 14px rgba(0,0,0,.24), 0 18px 40px rgba(0,0,0,.3), 0 36px 80px rgba(0,0,0,.32)', `0 0 0 .5px rgba(${SHADOW},.07), 0 3px 8px rgba(${SHADOW},.06), 0 16px 36px rgba(${SHADOW},.1), 0 40px 88px rgba(${SHADOW},.13)`],
  // The content pane and the cards on it: no drop shadow in dark (depth comes from the tone steps, a border and a top
  // highlight), a soft two-layer lift in light.
  // "No shadow" is a zero shadow, not `none`: these sit inside a comma list (border + highlight + elevation), where `none`
  // makes the whole declaration invalid and the card lost its border and top edge in dark.
  'e-pane': ['0 0 0 0 transparent', `0 0 0 .5px rgba(${SHADOW},.03), 0 1px 2px rgba(${SHADOW},.04)`],
  'e-tile': ['0 0 0 0 transparent', `0 1px 2px rgba(${SHADOW},.04), 0 4px 12px rgba(${SHADOW},.03)`],
  'e-card': [`0 0 0 0.5px ${hud.notch}, 0 2px 4px rgba(0,0,0,.3), 0 12px 28px rgba(0,0,0,.34), 0 32px 72px rgba(0,0,0,.42)`, `0 0 0 .5px rgba(${SHADOW},.08), 0 3px 8px rgba(${SHADOW},.07), 0 18px 40px rgba(${SHADOW},.12), 0 44px 96px rgba(${SHADOW},.16)`],
  // ---- highlight edges ----
  'h-top': ['inset 0 1px 0 rgba(255,255,255,.1)', 'inset 0 1px 0 rgba(255,255,255,.95)'],
  'h-top-soft': ['inset 0 1px 0 rgba(255,255,255,.06)', 'inset 0 1px 0 rgba(255,255,255,.8)'],
  'h-card': ['inset 0 1px 0 rgba(255,255,255,.04)', 'inset 0 1px 0 rgba(255,255,255,.9)'],
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
  // a skill track's area (home window redraft, Adrian Nov 21): barely tinted in dark (a wash over gray read as a
  // dusty gray box), the tag's pale wash at 60% in light
  'tone-sky-wash': [alphaHex(brand.pastel.sky, 0.055), alphaHex('#DDEEF9', 0.6)],
  'tone-lilac-wash': [alphaHex(brand.pastel.lilac, 0.055), alphaHex('#E7E2FB', 0.6)],
  'tone-pink-wash': [alphaHex(brand.pastel.pink, 0.055), alphaHex('#FADCE6', 0.6)],
  'tone-mint-wash': [alphaHex(brand.pastel.mint, 0.055), alphaHex('#D8F0EA', 0.6)],
  'tone-peach-wash': [alphaHex(brand.pastel.peach, 0.055), alphaHex('#FCE3D2', 0.6)],
  'tone-sand-wash': [alphaHex(brand.pastel.sand, 0.055), alphaHex('#EFE8D8', 0.6)],
  // ---- glass panels (theme.glass): the same surfaces, as before ----
  'glass-bg': ['rgba(30, 30, 29, 0.96)', 'rgba(252, 251, 249, 0.97)'],
  'glass-text': [hud.dark.text, brand.ink],
  // QA Q08 (Nov 24): faint was 4.0:1 (dark) and 2.65:1 (light) on the glass; now at least 4.5:1 on the pane and its
  // hover field. Light label moves darker with it so label still reads above faint.
  'glass-label': ['rgba(255,255,255,.66)', 'rgba(0,0,0,.66)'],
  'glass-faint': ['rgba(255,255,255,.54)', 'rgba(0,0,0,.57)'],
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
  // The notch island pins this set: its text stays the HUD pair, not the app windows' softer one.
  const island = `--c-text:${hud.dark.text};--c-label:${hud.dark.muted};`
  const light = `${decls(1)}--color-white:var(--c-white);color-scheme:light;`
  return [
    `:root,[data-theme="dark"],:root[data-appearance="dark"] [data-theme="auto"]{${dark}}`,
    `[data-theme="dark"]{${island}}`,
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
  /** Ink text and icons on a solid option pastel (actionTone): the same in light and dark. */
  onPastel: 'var(--c-on-pastel)',
  /** Off track: white, shown as a ring (the name stays `amber` so call sites don't change). */
  amber: 'var(--c-offtrack)',
  amberTint: 'var(--c-offtrack-tint)',
  /** Passed. Nothing else is green. */
  green: 'var(--c-green)',
  greenDeep: 'var(--c-green-deep)',
  /** Passed, as text on any surface: readable green in light, the pass green in dark. */
  greenText: 'var(--c-green-text)',
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
  /** Everything inside the app: Bricolage Grotesque (Michael, Nov 24), the system font as fallback. */
  ui: '"Bricolage Grotesque", -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif',
  /** Brand moments (auth/onboarding headings). The same face since Nov 24; the wordmark is an outlined SVG. */
  brand: '"Bricolage Grotesque", -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
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

/** The open notch island's shadow (a CSS filter on the shape's wrapper, because the shape itself is clipped): none at rest, so it fuses with the hardware notch. */
export const notchDrop = 'drop-shadow(0 10px 18px rgba(0,0,0,.4))'

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
  /** A keycap on a solid option pastel (ink at 10% in both appearances). */
  onPastelKey: 'var(--f-on-pastel-key)',
  clear: 'rgba(255,255,255,0)',
  /** Next to nothing, but not fully clear: an interactive transparent overlay still hit-tests as ours (features/circle). */
  catch: 'rgba(0,0,0,0.012)',
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
  /** The app window sidebar's selected row (features/shell Sidebar): quieter than navActive. */
  navOn: 'var(--f-nav-on)',
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
 * never status. Each option its own pastel (Adrian, Nov 21): sky = Explain · seafoam = Diagram · peach = Watch ·
 * lilac = Show me · pink = Hint.
 * The ONE primary action per surface is white + ink (PrimaryButton). Chrome and navigation stay neutral.
 */
export const actionTone = {
  explain: brand.pastel.sky,
  diagram: brand.pastel.seafoam,
  watch: brand.pastel.peachLight,
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

/**
 * The app windows' layout system (layout lane, Nov 22; features/shell owns the frame, ui.tsx Page / PageHeader use it).
 * Michael: "the centering is off, especially in full screen". One spacing scale, one page column for every page,
 * centered in the content pane (not the window), top-anchored (never vertically centered), and one header pattern.
 *
 *   space      the only spacing steps (px): 4 8 12 16 20 24 32 40 56 80 (Linear's 4/8 grid)
 *   sidebar    232 wide, 196 below a 1100 px window, icons only (64) below 860; rows 30 tall, 10 px inset, 2 apart
 *   pane       the content pane, inset 8 from the window's top, right and bottom, radius 12, no divider beside the sidebar
 *   page       one column: 640 of content inside 40 px gutters (720 in all; 24 px gutters when the pane is under 760),
 *              centered in the pane; Skills takes the wide one (960 + gutters = 1040). Forms and long text cap at 560 and
 *              stay left inside it (the column centers, its text never does). The one column component is
 *              features/shell ui.tsx PageColumn (720 / 1040, gutters included), so a page's content and the shell's
 *              title share one left edge on every page.
 *              `top` / `topFull`: the window's top edge to the page title's top (80, 52 in macOS full screen, where no
 *              title bar needs dragging), the same line Home's first element sits on. Never vertically centered.
 *              Title to first section is 32: the header leaves `titleGap` (24) under the title's line, the page's column
 *              starts `bodyTop` (8) below that.
 *   radius     cards and ask boxes 12, the one hero card (Home's Continue) 16, the pane 12 (concentric at the 8 inset).
 */
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 14: 56, 20: 80 } as const
export const layout = {
  sidebar: { w: 232, narrowW: 196, compactW: 64, narrowBelow: 1100, compactBelow: 860, pad: 10, row: 30, rowGap: 2, groupGap: 20, foot: 12 },
  pane: { inset: 8, radius: 12 },
  page: {
    column: 640,
    wide: 960,
    form: 560,
    gutter: 40,
    gutterTight: 24,
    tightBelow: 760,
    top: 80,
    topFull: 52,
    /** The title row's height (a search field on the right fits it); the 32 px title line centers in it. */
    titleRow: 36,
    /** Under the title's 32 px line, inside the header; with the column's bodyTop the title to first section is 32. */
    titleGap: 24,
    /** A page column's own top padding, under the header (PageColumn's default `top`). */
    bodyTop: 8,
    section: 40,
    label: 12,
    bottom: 64
  },
  radius: { card: 12, hero: 16 }
} as const

/**
 * The v4 frame (Adrian's ui-next mock, Nov 23-24: docs/ui-next/README.md "the rules behind the pages"). The pages use
 * the whole window: a Notion-style 240 sidebar, a 44 px top bar with the breadcrumb, and wide row-and-table pages.
 * features/shell ui.tsx turns these into PageFrame / PageHeader / Section / TwoCol / Rows / Table.
 *
 *   sidebar  240 wide (216 under a 1100 window, icons only under 860), 8 px side padding, 30 px rows, quiet section
 *            labels (Plans, Recent) 18 above their rows, the account row 40 tall at the foot
 *   top      the top bar over every page: 44 tall, the breadcrumb at 13.5 px
 *   page     content 1040 wide, centered in the main area, 44 under the top bar, 40 px gutters (24 under a 760 main).
 *            Home and Progress: a 684 main column and a 316 rail, 40 apart, one hairline (the rail's left edge, 32 in);
 *            under a 900 main the rail drops below. Settings: two columns of groups 56 apart. Library, Plans: full width.
 *   row      a list row 44 tall (50 with a cover), a rail row 33 (48 with two lines); hairlines between rows
 *   table    head 32, rows 46, hairlines under each; the first column has no left padding
 *   sec      a section label 12.5 / 550 muted, 30 above and 10 under, with an optional quiet link on the right
 */
export const v4 = {
  sidebar: { w: 240, narrowW: 216, compactW: 64, padX: 8, padY: 10, row: 30, brand: 34, labelTop: 18, labelBottom: 4, account: 40, icon: 16 },
  top: 44,
  page: { w: 1040, main: 684, rail: 316, colGap: 40, railPad: 32, settingsGap: 56, top: 44, bottom: 72, gutter: 40, gutterTight: 24, twoColBelow: 900 },
  row: { h: 44, cover: 50, rail: 33, railTall: 48, padX: 8 },
  table: { head: 32, row: 46, padX: 8 },
  sec: { top: 30, bottom: 10, first: 26 },
  radius: { row: 6, control: 8, card: 12, tag: 4 }
} as const

/** The v4 frame's colors (palette `v4-*`): use these, never the mock's hex. Text stays `color.text` / `label` / `faint`. */
export const v4c = {
  side: 'var(--v4-side)',
  page: 'var(--v4-page)',
  card: 'var(--v4-card)',
  hair: 'var(--v4-hair)',
  hair2: 'var(--v4-hair2)',
  hover: 'var(--v4-hover)',
  active: 'var(--v4-active)',
  fill: 'var(--v4-fill)',
  fill2: 'var(--v4-fill2)',
  track: 'var(--v4-track)',
  ghost: 'var(--v4-ghost)',
  e1: 'var(--v4-e1)',
  e2: 'var(--v4-e2)'
} as const

/**
 * The v4 type ramp (the mock's sizes). Bricolage Grotesque since Nov 24, so the display sizes are 600, not 650-700.
 * Spread one into a style with its color.
 */
export const v4type = {
  title: { fontSize: 32, lineHeight: '38px', fontWeight: 600, letterSpacing: '-0.025em' },
  lede: { fontSize: 14.5, lineHeight: '20px', fontWeight: 400 },
  h2: { fontSize: 20, lineHeight: '26px', fontWeight: 600, letterSpacing: '-0.015em' },
  sec: { fontSize: 12.5, lineHeight: '18px', fontWeight: 550 },
  row: { fontSize: 14, lineHeight: '20px', fontWeight: 550 },
  body: { fontSize: 14, lineHeight: '20px', fontWeight: 400 },
  meta: { fontSize: 13, lineHeight: '18px', fontWeight: 400, fontVariantNumeric: 'tabular-nums' },
  th: { fontSize: 12.5, lineHeight: '16px', fontWeight: 450 },
  nav: { fontSize: 14, lineHeight: '20px', fontWeight: 500 },
  navLabel: { fontSize: 12, lineHeight: '16px', fontWeight: 550 },
  crumb: { fontSize: 13.5, lineHeight: '18px', fontWeight: 400 },
  stat: { fontSize: 22, lineHeight: '26px', fontWeight: 600, letterSpacing: '-0.015em', fontVariantNumeric: 'tabular-nums' },
  statSm: { fontSize: 17, lineHeight: '22px', fontWeight: 600, letterSpacing: '-0.015em', fontVariantNumeric: 'tabular-nums' },
  tag: { fontSize: 12.5, lineHeight: '20px', fontWeight: 400 }
} as const

/**
 * The app windows' type ramp (Linear's scale, layout lane Nov 22; Bricolage Grotesque since Nov 24: titles 600 with
 * slightly negative tracking, 12-14 px text at normal tracking, optical sizing picks the text cut). Spread one into a style:
 * `style={{ ...typeScale.pageTitle, color: color.text }}`. Sentence case everywhere, no uppercase labels.
 */
export const typeScale = {
  pageTitle: { fontSize: 26, lineHeight: '32px', fontWeight: 600, letterSpacing: '-0.6px' },
  cardTitle: { fontSize: 17, lineHeight: '24px', fontWeight: 600, letterSpacing: '-0.3px' },
  section: { fontSize: 13, lineHeight: '18px', fontWeight: 600 },
  body: { fontSize: 14, lineHeight: '20px', fontWeight: 450 },
  row: { fontSize: 14, lineHeight: '20px', fontWeight: 500 },
  nav: { fontSize: 13, lineHeight: '18px', fontWeight: 500 },
  meta: { fontSize: 12, lineHeight: '16px', fontWeight: 500, fontVariantNumeric: 'tabular-nums' }
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
  /** The app window's content pane: none in dark, a hairline lift in light. */
  pane: 'var(--e-pane)',
  /** A card on the pane: none in dark (border + top highlight do it), soft in light. */
  tile: 'var(--e-tile)',
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
  /** A card on the app's content pane: the faintest top edge (layout lane: dark cards carry no shadow). */
  card: 'var(--h-card)',
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
  sky: { bg: 'var(--tone-sky-bg)', fg: 'var(--tone-sky-fg)', wash: 'var(--tone-sky-wash)', solid: brand.pastel.sky },
  lilac: { bg: 'var(--tone-lilac-bg)', fg: 'var(--tone-lilac-fg)', wash: 'var(--tone-lilac-wash)', solid: brand.pastel.lilac },
  pink: { bg: 'var(--tone-pink-bg)', fg: 'var(--tone-pink-fg)', wash: 'var(--tone-pink-wash)', solid: brand.pastel.pink },
  mint: { bg: 'var(--tone-mint-bg)', fg: 'var(--tone-mint-fg)', wash: 'var(--tone-mint-wash)', solid: brand.pastel.mint },
  peach: { bg: 'var(--tone-peach-bg)', fg: 'var(--tone-peach-fg)', wash: 'var(--tone-peach-wash)', solid: brand.pastel.peach },
  sand: { bg: 'var(--tone-sand-bg)', fg: 'var(--tone-sand-fg)', wash: 'var(--tone-sand-wash)', solid: brand.pastel.sand }
} as const
export type Tone = keyof typeof tone
export const toneNames = Object.keys(tone) as Tone[]
/** A stable tone for any string (a track, a tool, a tag): the same name always gets the same color. */
export function toneFor(key: string): Tone {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
  return toneNames[h % toneNames.length]
}
