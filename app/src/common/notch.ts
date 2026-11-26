/**
 * Notch geometry, pure (no electron, no node): shared by main/notch.ts (runner + cache) and the browser stage.
 * Design: miyagi-v2/NOTCH-ISLAND.md (Geometry, Placement modes).
 */

/** Where the island lives: in the notch (default on macOS) or the pill below the menu bar (Windows, a display without a notch, the pref). */
export type IslandPlace = 'notch' | 'below'

/** The notch rect in display-local points: x from the display's left edge, y is always the display top. */
export type NotchGeom = { hasNotch: boolean; x: number; width: number; height: number }

/**
 * What the renderers get as `layout.notch`. `coexist`: another notch app is running (private, log-only: it never changes
 * `place`, and nothing shows it in the UI; the island only reads it to keep the notch core free for that app's hover).
 */
export type NotchLayout = NotchGeom & { place: IslandPlace; coexist?: boolean }

type R = { x: number; y: number; w: number; h: number }
/** One entry of `miyagi-listen --screens` (native/listen/Screens.swift). */
export type ScreenInfo = {
  id: number
  frame: R
  visible: R
  safeTop: number
  auxLeft: number | null
  auxRight: number | null
  scale: number
  builtin: boolean
}

/** The fake notch on displays without one (external monitors, older Macs): same width the hardware notch roughly has. */
export const FAKE_NOTCH_WIDTH = 185
const MIN_BAND = 24
/** A notch overlay widens the notch by 4 pt to hide the seam. */
const SEAM = 4

type DisplayLike = { id: number; bounds: { x: number; y: number; width: number; height: number }; workArea: { x: number; y: number; width: number; height: number } }

/**
 * The notch for a display. `info` is the helper's entry for it (absent: helper missing, failed or not read yet).
 * Without a real notch the geometry is only a placeholder for the pill below the menu bar (`hasNotch` false, and
 * effectivePlace never answers 'notch' for it), so no black notch is ever drawn where there is none.
 */
export function notchFor(display: DisplayLike, info?: ScreenInfo): NotchGeom {
  const w = display.bounds.width
  if (info && info.safeTop > 0 && typeof info.auxLeft === 'number' && typeof info.auxRight === 'number') {
    const width = Math.round(info.frame.w - info.auxLeft - info.auxRight + SEAM)
    if (width > 0 && width < w) return { hasNotch: true, x: (w - width) / 2, width, height: info.safeTop }
  }
  // The helper's safeTop is the real top inset; the work area's offset is wrong while the menu bar auto-hides.
  const band = info && info.safeTop > 0 ? info.safeTop : Math.max(MIN_BAND, display.workArea.y - display.bounds.y)
  return { hasNotch: false, x: (w - FAKE_NOTCH_WIDTH) / 2, width: FAKE_NOTCH_WIDTH, height: band }
}

/** The notch placement: only on a Mac, only on a display that has a notch, and not when the pref says below. Other notch apps never matter. */
export function effectivePlace(pref: IslandPlace | undefined, mac: boolean, hasNotch: boolean): IslandPlace {
  return mac && pref !== 'below' && hasNotch ? 'notch' : 'below'
}

/**
 * A menu bar is never taller than this (a notch band is 32 to 38 pt; a plain menu bar 24). A work area that starts lower
 * than this is not a menu bar (a display mid-swap, a bad read), and the island must not hang from it in mid-screen.
 */
export const MAX_MENU_BAR = 64
/** Air the island keeps under a band when MIYAGI_PILL_TOP is set, and on Windows (a taskbar docked at the top). */
export const MENU_BAR_GAP = 4
/**
 * A menu bar that hides itself reports no band, but it still slides in over the top 24 pt: the island hangs under where
 * it will be, not at 0 where the menu bar would cover it (review of #282).
 */
export const HIDDEN_MENU_BAR = 24

/**
 * The menu bar's bottom edge on a display, in display-local points: what the island hangs from when it isn't in the
 * notch. The work area answers on its own (no helper needed); the helper's safeTop only raises it (a notched display
 * whose menu bar hides itself still has the notch band). 0 when there is none: a hidden menu bar on a display without a
 * notch, or a second display without a menu bar. Clamped to MAX_MENU_BAR.
 */
export function menuBarBottom(display: DisplayLike, info?: ScreenInfo): number {
  const work = display.workArea.y - display.bounds.y
  const band = Math.max(0, work > 0 && work <= MAX_MENU_BAR ? work : 0, info && info.safeTop > 0 ? info.safeTop : 0)
  return Math.round(Math.min(band, MAX_MENU_BAR))
}

/** What islandAnchor needs besides the display. */
export type AnchorOpts = {
  mac: boolean
  pref?: IslandPlace
  /** The helper's entry for this display (absent: helper missing, failed, timed out, or not read yet). */
  info?: ScreenInfo
  /** Notch geometry is known (a helper read or the persisted cache). Until then the island is never put in a notch. */
  known: boolean
  /** MIYAGI_PILL_TOP, when set (px from the display top). */
  override?: number
  /**
   * The display has a menu bar, shown or hidden (default true). False only for a display with none at all (a second
   * display while "Displays have separate Spaces" is off): then the island may sit at the very top.
   */
  menuBar?: boolean
}

/**
 * The island's top edge when it is NOT in the notch, in display-local points.
 *   Mac: flush with the menu bar's bottom edge, a tab hanging from it, centred (MacBook Neo, Nov 25: on a display
 *        without a notch the old default top of 40 left the island floating 16 pt under a 24 pt menu bar). A menu bar
 *        that hides itself: under where it slides in (HIDDEN_MENU_BAR). A display with no menu bar at all: its top
 *        edge. MIYAGI_PILL_TOP moves it down as before.
 *   Windows: 8 px, or MENU_BAR_GAP under a taskbar docked at the top (unchanged).
 * Pure and helper-free: a missing or slow helper only means `info` is absent; the work area still gives the band.
 */
export function belowTop(display: DisplayLike, o: Pick<AnchorOpts, 'mac' | 'info' | 'override' | 'menuBar'>): number {
  const band = menuBarBottom(display, o.info)
  if (!o.mac || o.override !== undefined) {
    const base = o.override ?? 8
    return band > 0 ? Math.max(base, band + MENU_BAR_GAP) : base
  }
  return band > 0 ? band : o.menuBar === false ? 0 : HIDDEN_MENU_BAR
}

export type IslandAnchor = { place: IslandPlace; top: number; notch: NotchGeom }

/**
 * Where the island goes on a display: in the notch (top 0) when the display has one and the pref allows it, else
 * hanging from the menu bar (belowTop). Never mid-screen, and never a notch drawn where there is none.
 */
export function islandAnchor(display: DisplayLike, o: AnchorOpts): IslandAnchor {
  const notch = notchFor(display, o.info)
  const place = o.known ? effectivePlace(o.pref, o.mac, notch.hasNotch) : 'below'
  return { place, top: place === 'notch' ? 0 : belowTop(display, o), notch }
}

/** Parse the helper's stdout. Never throws: anything malformed gives an empty list (callers keep what they had). */
export function parseScreens(text: string): ScreenInfo[] {
  const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  const rect = (v: unknown): R | null => {
    if (!v || typeof v !== 'object') return null
    const r = v as Record<string, unknown>
    const x = num(r.x), y = num(r.y), w = num(r.w), h = num(r.h)
    return x === null || y === null || w === null || h === null ? null : { x, y, w, h }
  }
  try {
    const line = text.split('\n').find((l) => l.trim().startsWith('{')) ?? ''
    const list = (JSON.parse(line) as { screens?: unknown }).screens
    if (!Array.isArray(list)) return []
    const out: ScreenInfo[] = []
    for (const e of list) {
      if (!e || typeof e !== 'object') continue
      const r = e as Record<string, unknown>
      const id = num(r.id), frame = rect(r.frame), visible = rect(r.visible)
      if (id === null || !frame || !visible) continue
      out.push({
        id,
        frame,
        visible,
        safeTop: Math.max(0, num(r.safeTop) ?? 0),
        auxLeft: num(r.auxLeft),
        auxRight: num(r.auxRight),
        scale: num(r.scale) ?? 1,
        builtin: r.builtin === true
      })
    }
    return out
  } catch {
    return []
  }
}

/** The browser stage's notch: `?notch=fake|real|below` (default real-ish 200x32, notch place). */
export function stageNotch(mode: string | null, width: number): NotchLayout {
  const real = mode !== 'fake'
  const w = mode === 'fake' ? FAKE_NOTCH_WIDTH : 200
  return { hasNotch: real, x: (width - w) / 2, width: w, height: 32, place: mode === 'below' ? 'below' : 'notch', coexist: false }
}
