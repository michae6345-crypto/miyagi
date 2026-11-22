/**
 * Core (v2, W0-5): shared rect math, pure (no React, no DOM, no Electron), so the main process can import it too.
 * Moved here from features/spotlight/place.ts and features/player/dock.ts, which re-export it unchanged, so every old
 * import keeps working. New code imports from here (core never imports a feature for geometry).
 *
 * Contract (shared/contracts/events.ts): rects are screen POINTS, top-left origin, relative to the PRIMARY display's
 * full frame (menu bar included); a window at `origin` in that space maps them with toLocal.
 */

export type Rect = { x: number; y: number; w: number; h: number }
export type Point = { x: number; y: number }
/** Electron's rect shape (width / height), as main and the player dock use it. */
export type Box = { x: number; y: number; width: number; height: number }

// ---- the spotlight's hole (was features/spotlight/place.ts) ------------------------------------------------------

/** Breathing room left and right of the OCR'd text block (the engine's own padding is small; mockup 04). */
export const HOLE_PAD = 8
/**
 * Above and below it: about 3 pt, so an editor line's hole stays inside that line's leading (Michael's audit A7: at 8,
 * plus a 30 pt minimum, the box was ~1.7 lines tall and cut into the next line).
 */
export const HOLE_PAD_Y = 3
/** A one-word target still gets a hole you can see. */
export const HOLE_MIN = { w: 44, h: 20 } as const
/** Below this share of the hole on screen it isn't worth a dim: say it on the pill instead. */
export const MIN_VISIBLE_SHARE = 0.25

/** Screen points → this window's coordinates (local = screen − origin). */
export function toLocal(r: Rect, origin: Point): Rect {
  return { x: r.x - origin.x, y: r.y - origin.y, w: r.w, h: r.h }
}

/** A rect we can point at: finite numbers and a real size (the engine can send an empty or zero box). */
export function isUsableRect(r: Partial<Rect> | undefined | null): r is Rect {
  return !!r && [r.x, r.y, r.w, r.h].every((v) => typeof v === 'number' && Number.isFinite(v)) && r.w! > 0 && r.h! > 0
}

export function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

export function contains(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h
}

/** The cut-out: the target plus padding (wide left/right, tight above/below), grown around its center to a minimum size. */
export function hole(r: Rect, pad = HOLE_PAD, padY = HOLE_PAD_Y): Rect {
  const w = Math.max(r.w + pad * 2, HOLE_MIN.w)
  const h = Math.max(r.h + padY * 2, HOLE_MIN.h)
  return { x: r.x + r.w / 2 - w / 2, y: r.y + r.h / 2 - h / 2, w, h }
}

/** Overlap of two rects in px² (0 when apart). */
export function overlapArea(a: Rect, b: Rect): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return w > 0 && h > 0 ? w * h : 0
}

/** Share of `a`'s area that lies inside `b` (0–1). */
export function overlapShare(a: Rect, b: Rect): number {
  return a.w * a.h > 0 ? overlapArea(a, b) / (a.w * a.h) : 0
}

/** OCR jitter: the engine re-reads the screen every ~2s and boxes wobble by a point or two. */
export function sameRect(a: Rect, b: Rect, tol = 2): boolean {
  return Math.abs(a.x - b.x) <= tol && Math.abs(a.y - b.y) <= tol && Math.abs(a.w - b.w) <= tol && Math.abs(a.h - b.h) <= tol
}

/** `r` grown by `by` on every side. */
export function grow(r: Rect, by: number): Rect {
  return { x: r.x - by, y: r.y - by, w: r.w + by * 2, h: r.h + by * 2 }
}

// ---- the video player's dock (was features/player/dock.ts) -------------------------------------------------------

/** The player docks in the right 40% of the work area. */
export const DOCK_FRACTION = 0.4
const DOCK_INSET = 8
/** No bottom bar any more (Nov 21): the player ends at the work area's inset, like the drawer. */
const DOCK_BAR_CLEARANCE = 0

/**
 * Where the player docks: the right 40% of the work area, inset 8px, ending above the shortcut bar. Shared by main
 * (src/main/features/player.ts) and the browser stage, so both put it in the same place.
 */
export function dockRect(workArea: Box): Box {
  const width = Math.round(workArea.width * DOCK_FRACTION) - DOCK_INSET * 2
  return {
    x: workArea.x + workArea.width - width - DOCK_INSET,
    y: workArea.y + DOCK_INSET,
    width,
    height: Math.max(320, workArea.height - DOCK_INSET * 2 - DOCK_BAR_CLEARANCE)
  }
}

/** Box (width/height) ↔ Rect (w/h). */
export const boxToRect = (b: Box): Rect => ({ x: b.x, y: b.y, w: b.width, h: b.height })
export const rectToBox = (r: Rect): Box => ({ x: r.x, y: r.y, width: r.w, height: r.h })
