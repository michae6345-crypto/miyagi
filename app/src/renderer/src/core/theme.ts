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
  /**
   * Panels on the dark HUD (the launcher / ask panel). CSS can't blur other apps in Electron, so this is far more
   * opaque than the kit's .72: at .90 the code under the ask panel still showed through (Michael's tests 2-3, A13).
   * At .96 text behind the launcher still showed next to its rows (Michael's Devpost shots), so it is now solid.
   */
  glass: 'rgb(28,28,30)',
  /** v2: the ink tick / text on a green (passed) circle. */
  onGreen: brand.ink,
  /** v2: an app window's opaque body (Onboarding, Library, Progress). Same as surface.window. */
  window: 'rgb(28,28,30)'
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
 * shadow layers (brand: transform and opacity only) is a follow-up for those lanes. The first layer is a 0.5 px hairline
 * that keeps the black island apart from a dark editor behind it.
 */
export const shadows = {
  pill: '0 0 0 0.5px rgba(255,255,255,.09), 0 1px 2px rgba(0,0,0,.32), 0 4px 10px rgba(0,0,0,.22), 0 10px 24px rgba(0,0,0,.14)',
  card: '0 0 0 0.5px rgba(255,255,255,.09), 0 2px 4px rgba(0,0,0,.3), 0 12px 28px rgba(0,0,0,.34), 0 32px 72px rgba(0,0,0,.42)'
} as const

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
  thumbArt: '#3A3A3C',
  // ---- v2 (W0-2) ----
  /** A grouped block of rows (Set-General). */
  group: 'rgba(255,255,255,.04)',
  hairline: 'rgba(255,255,255,.12)',
  /** The selected sidebar row (Settings, Library). */
  navActive: 'rgba(255,255,255,.12)',
  /** The selected segment of a Segmented control, and its track. */
  segmentOn: 'rgba(255,255,255,.18)',
  segmentTrack: 'rgba(255,255,255,.06)',
  /** A keycap on a dark surface (core/ui/Keycap.tsx). On a pastel or white button it's onAccentKey. */
  keycap: 'rgba(255,255,255,.12)',
  keycapBorder: 'rgba(255,255,255,.18)',
  keycapText: 'rgba(255,255,255,.78)',
  /** Step dots / meters: a step not reached yet. */
  trackNext: 'rgba(255,255,255,.18)',
  /** Les-Mini's step bars: a step not reached yet, a touch brighter on the small 4 px bar. */
  trackNextMini: 'rgba(255,255,255,.24)',
  /** A skill being practiced (Prog-Progress-Window): white at 55%, never a hue. */
  practicing: 'rgba(255,255,255,.55)',
  /** A Toggle that is off. */
  toggleOff: 'rgba(255,255,255,.16)'
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
  /** v2: Settings → General caption (decision 9: the settings panel stays black). */
  appearanceCaption: 'Applies to panels and this window.',
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
  notYet: brand.offTrack,
  /** The ring's stroke on paper. */
  notYetOnPaper: brand.ink,
  watching: brand.watching,
  unknown: brand.watching,
  offline: brand.watching,
  /** An empty / pending ring (a step not started, a row not checked yet). */
  ring: 'rgba(255,255,255,.28)'
} as const

/** Dark surfaces, back to front: the lesson panel, an app window's body, a sheet inside it, a row on any of them. */
export const surface = {
  /** The lesson panel docked beside the editor, the island's cards' glass twin (Les-Working). */
  panel: 'rgba(28,28,30,0.96)',
  /** App windows (Onboarding, Library, Progress): opaque, so nothing shows through. Same as color.window. */
  window: 'rgb(28,28,30)',
  /** A sheet or popover inside a window (Onb-Checklist-Mixed). */
  sheet: '#2C2C2E',
  /** A grouped row on any of the above (Set-General, Home-Library). */
  row: 'rgba(255,255,255,.06)',
  rowHover: 'rgba(255,255,255,.1)',
  /** Polish: a recessed box (the code to type, a text field): darker than the surface it sits in, never lighter. */
  well: 'rgba(0,0,0,.26)',
  border: 'rgba(255,255,255,.12)',
  /** Polish: layered (contact + mid + ambient), see `elevation`. Same names, so every caller gets the depth. */
  shadow: '0 1px 2px rgba(0,0,0,.3), 0 6px 14px rgba(0,0,0,.24), 0 18px 40px rgba(0,0,0,.3), 0 36px 80px rgba(0,0,0,.32)',
  shadowSmall: '0 1px 2px rgba(0,0,0,.3), 0 4px 10px rgba(0,0,0,.22), 0 12px 28px rgba(0,0,0,.24)'
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
  raised: '0 1px 1px rgba(0,0,0,.3), 0 2px 4px rgba(0,0,0,.22), 0 6px 14px rgba(0,0,0,.2)',
  overlay: surface.shadowSmall,
  panel: surface.shadow
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
  top: 'inset 0 1px 0 rgba(255,255,255,.1)',
  topSoft: 'inset 0 1px 0 rgba(255,255,255,.06)',
  onLight: 'inset 0 1px 0 rgba(255,255,255,.55)',
  base: 'inset 0 -1px 0 rgba(0,0,0,.1)',
  well: 'inset 0 1px 3px rgba(0,0,0,.4)',
  /** A keycap's bottom lip: the key stands on the surface. */
  keyLip: 'inset 0 -1px 0 rgba(0,0,0,.35)'
} as const

/**
 * Hover and press tints, painted by a layer over the control whose OPACITY animates (styles.css .mg-press), so no
 * color or filter ever animates. `onDark` lightens a neutral control; `onLight` darkens a white or pastel one.
 * `onInk` lightens the ink GlassPrimary under light glass (styles.css .mg-glass); an ink fill needs a stronger white.
 */
export const tint = {
  hoverOnDark: 'rgba(255,255,255,.06)',
  pressOnDark: 'rgba(255,255,255,.1)',
  hoverOnLight: 'rgba(0,0,0,.045)',
  pressOnLight: 'rgba(0,0,0,.09)',
  hoverOnInk: 'rgba(255,255,255,.08)',
  pressOnInk: 'rgba(255,255,255,.14)'
} as const

/** The keyboard focus ring (focus-visible only, never on a mouse click): white on dark, ink on paper, 2 px, 2 px out. */
export const focus = { dark: 'rgba(255,255,255,.88)', paper: 'rgba(20,20,20,.88)', width: 2, offset: 2 } as const

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
