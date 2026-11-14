// Miyagi design tokens. Drop into app/src/theme.ts.
// Green only ever means "passed". Amber means off track. There is no red anywhere.

export const color = {
  // brand surfaces (site, Devpost, slides, light-mode overlay)
  paper: '#F6F6F3',
  surface: '#FFFFFF',
  surface2: '#EFEFEA',
  ink: '#141414',
  inkMuted: '#66665F',
  inkFaint: '#8F8F88',
  hairline: 'rgba(0,0,0,0.08)',

  // states
  pass: '#30D158',        // passed, the light on the i, the bonsai's pads
  passDeep: '#1F9B45',    // pad undersides, back pads, pressed state
  passText: '#1C8A3C',    // green text on light backgrounds (AA contrast)
  passTint: 'rgba(48,209,88,0.14)',
  offTrack: '#FFB020',
  offTrackTint: 'rgba(255,176,32,0.12)',
  watching: '#8E8E93',

  // bonsai details (illustration only)
  soil: '#6B5643',
  jin: '#E7E2D6',

  // the notch pill is always black
  pill: '#000000',
} as const;

// The overlay follows macOS: dark HUD glass by default (Michael's mockups), light when the system is light.
export const hud = {
  dark: { glass: 'rgba(28,28,30,0.72)', text: '#F4F4F5', muted: 'rgba(255,255,255,0.6)', hairline: 'rgba(255,255,255,0.12)', button: '#F4F4F5', buttonText: '#141414' },
  light: { glass: 'rgba(255,255,255,0.78)', text: '#141414', muted: 'rgba(0,0,0,0.55)', hairline: 'rgba(0,0,0,0.10)', button: '#141414', buttonText: '#F6F6F3' },
} as const;

export const font = {
  brand: '"Google Sans Flex", system-ui, sans-serif',               // wordmark, headings, covers
  ui: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif', // everything inside the app
  mono: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
} as const;

export const text = { xs: 13, sm: 15, md: 20, lg: 28 } as const;     // Michael's scale
export const weight = { regular: 400, medium: 500, semibold: 600 } as const;
export const radius = { chip: 14, card: 20, launcher: 28, pill: 17 } as const;
export const shadow = { card: '0 20px 60px rgba(0,0,0,.45)', icon: '0 10px 24px rgba(0,0,0,.22)' } as const;
export const spring = { type: 'spring', stiffness: 420, damping: 34, mass: 0.9 } as const;

// Which bonsai cut to use at which size.
export const markLevel = (px: number) => (px <= 32 ? 'small' : px <= 140 ? 'icon' : 'full');

export const copy = {
  name: 'Miyagi',
  oneLiner: 'Turn any tutorial into an auto-graded lab.',
  launcherPlaceholder: 'Ask Miyagi anything',
  offTrackExample: 'Loss is flat at 0.25. Add a β curriculum, then rerun.',
  passExample: 'Good. Now the next one.',
} as const;

export const theme = { color, hud, font, text, weight, radius, shadow, spring, copy } as const;
export default theme;
