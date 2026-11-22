/**
 * The notch island's pure geometry (no React, no DOM, no Electron): where the island sits, the notch shape, the
 * sizes of its resting views, and the hit zone main grabs. Tested offline (test/notchIsland.test.ts).
 * Design: miyagi-v2/NOTCH-ISLAND.md. `layout.notch.place === 'below'` (or no notch) means today's pill: every function
 * here then answers exactly what the old code did.
 */
import type { NotchLayout } from '../../../common/notch'
import { pill } from './theme'

type Box = { x: number; y: number; w: number; h: number }

/** The notch's radii: closed (at rest, ears) and open (peek, cards). The shape animates between them. */
export const NOTCH_RADII = { closed: { top: 6, bottom: 14 }, open: { top: 19, bottom: 24 } } as const
export type Radii = { top: number; bottom: number }

/** How far each ear grows sideways, at the notch's own height. */
export const EAR_W = 36
/** The peek: this wide (at least), and this much taller than the notch. */
export const PEEK = { w: 300, drop: 28 } as const
/** The pointer counts as over the notch within this margin; the peek opens after OPEN_MS and closes CLOSE_MS after leaving. */
export const HOVER = { margin: 6, openMs: 150, closeMs: 100 } as const
/** Main's grab zone in notch mode: this far either side of the island, this far below it, never above (the menu bar). */
export const GRAB = { side: 6, below: 12 } as const
/** One pixel of black above the display, so no seam shows between the island and the top edge. */
export const STRIP = 1

/** What a pill-sized mode shows in the notch: nothing (the notch itself), ears, or a drop with its content. */
export type NotchView = 'rest' | 'ears' | 'drop' | 'ears+drop'

/** The notch layout when the island lives there, else undefined (the pill below the menu bar, as before). */
export function notchOf(layout: { notch?: NotchLayout } | undefined): NotchLayout | undefined {
  const n = layout?.notch
  if (!n || n.place !== 'notch') return undefined
  return [n.x, n.width, n.height].every((v) => typeof v === 'number' && Number.isFinite(v)) && n.width > 0 && n.height > 0 ? n : undefined
}

/** The island's top edge in display coordinates: the display top in the notch, else the pill's top. */
export function islandTopAt(layout: { notch?: NotchLayout }, pillTop: number): number {
  return notchOf(layout) ? 0 : pillTop
}

/** The island's resting bottom edge in display coordinates: the notch's bottom, or the pill's. */
export function islandBottomAt(layout: { notch?: NotchLayout }, pillTop: number): number {
  const n = notchOf(layout)
  return n ? n.height : pillTop + pill.height
}

/** Radii for a state: open for the peek and cards, closed otherwise. */
export const radiiFor = (open: boolean): Radii => (open ? NOTCH_RADII.open : NOTCH_RADII.closed)

/**
 * The notch path in the element's own coordinates: concave top "ears" (`top` radius) and convex bottom
 * corners (`bottom` radius), quadratic curves. `strip` extra pixels sit above the shape (the black seam strip), so the
 * element is `h + strip` tall and the shape is shifted down by `strip`. Radii are clamped to what fits.
 */
export function notchPath(w: number, h: number, top: number, bottom: number, strip = 0): string {
  const W = Math.max(0, w)
  const H = Math.max(0, h)
  const t = Math.max(0, Math.min(top, W / 2, H))
  const b = Math.max(0, Math.min(bottom, (W - 2 * t) / 2, H - t))
  const s = strip
  const f = (n: number): string => String(Math.round(n * 100) / 100)
  const P = (cmd: string, ...v: number[]): string => `${cmd}${v.map(f).join(' ')}`
  return [
    P('M', 0, 0),
    P('L', W, 0),
    P('L', W, s),
    P('Q', W - t, s, W - t, s + t),
    P('L', W - t, s + H - b),
    P('Q', W - t, s + H, W - t - b, s + H),
    P('L', t + b, s + H),
    P('Q', t, s + H, t, s + H - b),
    P('L', t, s + t),
    P('Q', t, s, 0, s),
    'Z'
  ].join(' ')
}

/** The CSS clip-path for that shape. */
export const notchClip = (w: number, h: number, top: number, bottom: number, strip = STRIP): string => `path('${notchPath(w, h, top, bottom, strip)}')`

/** The notch rect itself: the island at rest. */
export const restSize = (n: NotchLayout): { w: number; h: number } => ({ w: n.width, h: n.height })
/** Ears: the notch widened by an ear each side, same height. */
export const earsSize = (n: NotchLayout): { w: number; h: number } => ({ w: n.width + 2 * EAR_W, h: n.height })

/**
 * The island's size in the notch. `kind`: a card (fixed width, `measured` its content's size) or a pill-sized mode.
 * A drop (peek or a pill line) is the notch row plus the content row, at least PEEK.w wide. Rest and ears ignore
 * `measured`.
 */
export function notchSize(n: NotchLayout, kind: 'card' | 'pill', view: NotchView, fixed: number | undefined, measured: { w: number; h: number } | undefined): { w: number; h: number } {
  // The shape's straight sides sit one top radius in from its edges, so the card's own width fits between them.
  if (kind === 'card') return fixed && fixed > 0 && measured && measured.h > 0 ? { w: fixed + 2 * NOTCH_RADII.open.top, h: n.height + Math.ceil(measured.h) } : restSize(n)
  if (view === 'rest') return restSize(n)
  if (view === 'ears') return earsSize(n)
  if (!measured || !(measured.w > 0) || !(measured.h > 0)) return { w: PEEK.w, h: n.height + PEEK.drop }
  return { w: Math.max(PEEK.w, Math.ceil(measured.w) + 2 * NOTCH_RADII.open.top), h: n.height + Math.ceil(measured.h) }
}

/** A pill-sized mode's view with hover applied: the pointer over a rest or ears view opens the peek. */
export function viewWith(view: NotchView, hover: boolean): NotchView {
  return hover && (view === 'rest' || view === 'ears') ? 'drop' : view
}

/** Open radii for a peek, a drop or a card; closed for rest and ears. */
export const isOpenView = (kind: 'card' | 'pill', view: NotchView): boolean => kind === 'card' || view === 'drop' || view === 'ears+drop'

/** Hover timing while another notch app shares the notch: its 300 ms open delay, and a short cancellable close grace. */
export const COEXIST_HOVER = { openMs: 300, closeMs: 100 } as const
/** The other app's open panel: this far either side of the notch centre, this deep from the display top. */
export const OTHER_OPEN_ZONE = { half: 320, depth: 190 } as const
/** The pointer must stay outside the open zone this long before the grab is unmuted. */
export const OTHER_OPEN_MUTE_MS = 150

type Pt = { x: number; y: number }
export type NotchRect = { x: number; width: number; height: number }

/** Is the point in the notch core (the hardware notch itself)? `notch` and `p` share one coordinate space; the notch's top is `displayTop`. */
export function inNotchCore(p: Pt, notch: NotchRect, displayTop = 0): boolean {
  return p.x >= notch.x && p.x <= notch.x + notch.width && p.y >= displayTop && p.y < displayTop + notch.height
}

/** Is the point where another notch app's open panel would be (notch centre +-320, y 0..190 from the display top)? */
export function inOtherOpenZone(p: Pt, notch: NotchRect, displayTop = 0): boolean {
  const cx = notch.x + notch.width / 2
  return Math.abs(p.x - cx) <= OTHER_OPEN_ZONE.half && p.y >= displayTop && p.y <= displayTop + OTHER_OPEN_ZONE.depth
}

/**
 * Main's grab test (features/overlay-raise.ts). Below the menu bar: `margin` all round, as before. In the notch,
 * a rect that touches the display top (the island) is grabbed +-GRAB.side horizontally and GRAB.below under it only,
 * never above or into the menu bar beside it; other rects keep the margin.
 * `opts.coexist` (with `opts.notch`, in the coordinate space of `p` and `r`): another notch app owns the notch core, so
 * the core is never grabbed; the ears (the island beside the notch) and the strip under it are.
 */
export function withinGrab(p: Pt, r: Box, o: { notch: boolean; displayTop: number; margin: number }, opts?: { coexist?: boolean; notch?: NotchRect }): boolean {
  if (o.notch && r.y <= o.displayTop + STRIP) {
    if (opts?.coexist && opts.notch && inNotchCore(p, opts.notch, o.displayTop)) return false
    return p.x >= r.x - GRAB.side && p.x <= r.x + r.w + GRAB.side && p.y >= o.displayTop && p.y <= r.y + r.h + GRAB.below
  }
  return p.x >= r.x - o.margin && p.x <= r.x + r.w + o.margin && p.y >= r.y - o.margin && p.y <= r.y + r.h + o.margin
}

/** In the core this long means the other app has probably opened its panel. */
export const OTHER_CORE_DWELL_MS = 250

/**
 * The mute that keeps miyagi's grab and peek away while another notch app's panel is open: it starts when the pointer
 * has stayed in the notch core for OTHER_CORE_DWELL_MS, and ends when the pointer has been outside the open zone for
 * OTHER_OPEN_MUTE_MS. Pure: call `step` on every poll with the clock and the pointer.
 */
export function createOtherOpenMute(): { step(now: number, p: Pt, notch: NotchRect, displayTop?: number): boolean; reset(): void } {
  let muted = false
  let coreSince = 0
  let outsideSince = 0
  return {
    step(now, p, notch, displayTop = 0) {
      if (!muted) {
        if (!inNotchCore(p, notch, displayTop)) coreSince = 0
        else if (!coreSince) coreSince = now
        else if (now - coreSince >= OTHER_CORE_DWELL_MS) {
          muted = true
          outsideSince = 0
        }
      } else if (inOtherOpenZone(p, notch, displayTop)) outsideSince = 0
      else if (!outsideSince) outsideSince = now
      else if (now - outsideSince >= OTHER_OPEN_MUTE_MS) {
        muted = false
        coreSince = 0
      }
      return muted
    },
    reset() {
      muted = false
      coreSince = 0
      outsideSince = 0
    }
  }
}
