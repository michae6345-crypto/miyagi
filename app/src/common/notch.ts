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
 * `boringNotch` is deprecated, always false; it stays on the type for one merge so older renderer code compiles.
 */
export type NotchLayout = NotchGeom & { place: IslandPlace; coexist?: boolean; boringNotch: boolean }

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
  return { hasNotch: real, x: (width - w) / 2, width: w, height: 32, place: mode === 'below' ? 'below' : 'notch', coexist: false, boringNotch: false }
}
