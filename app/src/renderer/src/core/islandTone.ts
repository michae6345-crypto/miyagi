/**
 * What kind of panel the open notch island holds, and so whether it may paint bon's pastel gradient (hud.notchGradient;
 * Michael, Nov 26). Pure: no React, no DOM. Tested in test/notchTint.test.ts.
 *
 * The gradient is opt-in. It shows only on CALM panels (the notch home: Continue lesson, ask miyagi, the drop zone, the
 * lessons ready to run and the Library row; it is also the idle hover panel). Every other panel stays plain notch
 * black, and the ones that warn are named here so a test holds them to it: a hue behind "Not yet", an error, a failed
 * build, offline, a permission ask or any other warning would read as "passed" (Adrian, MIC-83). A mode not listed is
 * 'other': plain black too.
 */
import { SHORT_OPEN_H } from './notchGeometry'

/** Calm panels: the gradient may show behind them. */
export const CALM_PANELS = ['home', 'continue', 'ask', 'library', 'idle-hover'] as const
/** Panels that warn or report a problem: never the gradient. */
export const BLOCKED_PANELS = ['notyet', 'error', 'offline', 'permission', 'failed', 'warning'] as const
export type CalmPanel = (typeof CALM_PANELS)[number]
export type BlockedPanel = (typeof BLOCKED_PANELS)[number]
export type PanelKind = CalmPanel | BlockedPanel | 'other'

/**
 * Island mode id -> its panel kind. A mode can refine this while it is open (IslandMode.useTone: the notch home turns
 * 'warning' while a dropped link it can't teach is showing). Modes not listed are 'other'.
 */
export const MODE_PANEL: Readonly<Record<string, PanelKind>> = {
  'notch-home': 'home',
  // Off track and its cards.
  offtrack: 'notyet',
  // features/errors: every stall.
  'err-crash': 'error',
  'err-engine-offline': 'offline',
  'err-editor-closed': 'error',
  'err-build-failed': 'failed',
  'err-limit': 'warning',
  'err-stopped': 'error',
  'err-reconnecting': 'offline',
  'err-blocker': 'warning',
  'err-net-offline': 'offline',
  'err-busy': 'warning',
  // Permission asks: the push-to-talk Allow card, setup's permission recovery.
  'ptt-card': 'permission',
  'onboarding-recovery': 'permission',
  // The cloud refused a build (sign in, a cap).
  'signin-card': 'warning',
  'cap-line': 'warning'
}

const calm = new Set<string>(CALM_PANELS)

/** The panel kind of a mode, with its own live refinement when it has one. */
export function panelOf(modeId: string | undefined, refined?: PanelKind): PanelKind {
  if (refined) return refined
  return (modeId && MODE_PANEL[modeId]) || 'other'
}

/** Whether a panel kind may show the gradient: calm ones only. */
export const isCalm = (kind: PanelKind): boolean => calm.has(kind)

/**
 * Whether the island paints bon's gradient now: open, tall (the short peek keeps plain black, as do closed and the
 * ears) and holding a calm panel.
 */
export const gradientOn = (open: boolean, h: number, kind: PanelKind): boolean => open && h >= SHORT_OPEN_H && isCalm(kind)
