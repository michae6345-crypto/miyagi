/**
 * Hover intent for the notch island, pure (no React, no DOM, no timers): a small state machine the island drives with
 * pointer events and one timer. Tested offline (test/hoverIntent.test.ts).
 *
 *  - Light response: the moment the pointer enters, `light` is true (the island leans in a hair); nothing waits.
 *  - Open: a timer started on enter. It is cancelled when the pointer leaves, and re-checked when it fires (the pointer
 *    must still be inside and the island not muted), so a pass-through never pops the peek.
 *  - Close: a short grace after the pointer leaves an open island; coming back inside cancels it.
 *  - Mute: when another notch app shares the notch (`coexist`), a pointer that dwells in the notch core is probably
 *    driving that app's own panel. After MUTE_ENTER_MS in the core the island mutes (peek hidden, nothing grabbed) and
 *    springs back MUTE_EXIT_MS after the pointer has left that app's open zone.
 *
 * Every function takes `now` (ms) and returns a new state; `hoverDeadline` says when to call `hoverTick` next.
 */
import { COEXIST_HOVER, HOVER, inNotchCore, inOtherOpenZone, OTHER_CORE_DWELL_MS, OTHER_OPEN_MUTE_MS, type NotchRect } from './notchGeometry'

export type Pt = { x: number; y: number }
export type { NotchRect }
export type Box = { x: number; y: number; w: number; h: number }

export type HoverTimings = { openMs: number; closeMs: number }
export type HoverCfg = HoverTimings & { coexist: boolean }
/** Timings and mode for the island: the island's own `HOVER` normally, the coexist timings when the notch is shared. */
export const cfgFor = (coexist: boolean): HoverCfg => (coexist ? { ...COEXIST_HOVER, coexist } : { openMs: HOVER.openMs, closeMs: HOVER.closeMs, coexist })

/** Mute timing is main's (notchGeometry OTHER_CORE_DWELL_MS / OTHER_OPEN_MUTE_MS): both sides use the same constants. */
export const MUTE_ENTER_MS = OTHER_CORE_DWELL_MS
export const MUTE_EXIT_MS = OTHER_OPEN_MUTE_MS
/** Hover zones next to the core when it is shared: the strip just under the notch is this tall. */
export const STRIP_BELOW = 12
/** Each ear's width as a hover zone (the ear the island draws). */
export const EAR_ZONE = 36

export type HoverState = {
  /** The pointer is on the island (or in one of its hover zones). */
  inside: boolean
  /** The instant, light response: true from the moment the pointer enters. */
  light: boolean
  /** The peek is open. */
  open: boolean
  /** Another notch app is open under the pointer: hide, grab nothing. */
  muted: boolean
  openAt?: number
  closeAt?: number
  coreSince?: number
  farSince?: number
}
export const HOVER_IDLE: HoverState = { inside: false, light: false, open: false, muted: false }

export function hoverEnter(s: HoverState, now: number, cfg: HoverCfg): HoverState {
  if (s.inside && !s.closeAt) return s.muted && s.light ? { ...s, light: false } : s
  const openAt = s.open || s.muted ? undefined : (s.openAt ?? now + cfg.openMs)
  return { ...s, inside: true, light: !s.muted, closeAt: undefined, openAt }
}

export function hoverLeave(s: HoverState, now: number, cfg: HoverCfg): HoverState {
  if (!s.inside && !s.light && s.openAt === undefined) return s
  return { ...s, inside: false, light: false, openAt: undefined, closeAt: s.open ? (s.closeAt ?? now + cfg.closeMs) : undefined }
}

/** Close the peek and drop timers now (Esc, a shortcut, the watchdog). The pointer stays where it is: no re-open until it re-enters. */
export function hoverCancel(s: HoverState): HoverState {
  return s.open || s.light || s.openAt !== undefined || s.closeAt !== undefined ? { ...s, open: false, light: false, openAt: undefined, closeAt: undefined } : s
}

/** Back to rest after a display change, sleep or wake. Keeps what we know about the other notch app. */
export const hoverReset = (s: HoverState): HoverState => ({ ...HOVER_IDLE, muted: s.muted, coreSince: s.coreSince, farSince: s.farSince })

/** Open now (the wheel gesture committed). */
export function hoverOpenNow(s: HoverState, now: number, cfg: HoverCfg): HoverState {
  if (s.muted) return s
  return { ...s, open: true, openAt: undefined, closeAt: s.inside ? undefined : (s.closeAt ?? now + cfg.closeMs) }
}

/** The pointer is inside the notch core (the part the hardware notch covers, where the other app's hit rect is). */
export const inCore = (p: Pt, n: NotchRect): boolean => inNotchCore(p, n)

/** Track the pointer for the mute (only when the notch is shared). Call on every pointer move. */
export function hoverPoint(s: HoverState, now: number, cfg: HoverCfg, p: Pt, n: NotchRect): HoverState {
  if (!cfg.coexist) return s
  const coreSince = inCore(p, n) ? (s.coreSince ?? now) : undefined
  const farSince = inOtherOpenZone(p, n) ? undefined : (s.farSince ?? now)
  return coreSince === s.coreSince && farSince === s.farSince ? s : { ...s, coreSince, farSince }
}

/** Where a pointer starts a hover when the notch is shared: the two ears and the strip under the notch, never the core. */
export function inHoverZone(p: Pt, n: NotchRect, openBox?: Box, margin = 6): boolean {
  if (openBox && p.x >= openBox.x - margin && p.x <= openBox.x + openBox.w + margin && p.y >= 0 && p.y <= openBox.y + openBox.h + margin) return true
  if (inCore(p, n)) return false
  const inEar = p.y >= 0 && p.y < n.height + 1 && ((p.x >= n.x - EAR_ZONE && p.x < n.x) || (p.x > n.x + n.width && p.x <= n.x + n.width + EAR_ZONE))
  const inStrip = p.x >= n.x && p.x <= n.x + n.width && p.y >= n.height && p.y <= n.height + STRIP_BELOW
  return inEar || inStrip
}

/** Fire the deadlines that are due. Open re-checks that the pointer is still inside; close that it is still out. */
export function hoverTick(s: HoverState, now: number, cfg: HoverCfg): HoverState {
  let t = s
  if (cfg.coexist && !t.muted && t.coreSince !== undefined && now - t.coreSince >= MUTE_ENTER_MS) {
    t = { ...t, muted: true, light: false, open: false, openAt: undefined, closeAt: undefined, coreSince: undefined }
  }
  if (t.muted && t.farSince !== undefined && now - t.farSince >= MUTE_EXIT_MS) {
    t = { ...t, muted: false, farSince: undefined, light: t.inside, openAt: t.inside ? now + cfg.openMs : undefined }
  }
  if (t.openAt !== undefined && now >= t.openAt) t = { ...t, open: t.inside && !t.muted ? true : t.open, openAt: undefined }
  if (t.closeAt !== undefined && now >= t.closeAt) t = { ...t, open: t.inside ? t.open : false, closeAt: undefined }
  return t
}

/** When to call `hoverTick` next, or undefined when nothing is pending. */
export function hoverDeadline(s: HoverState, cfg: HoverCfg): number | undefined {
  const at: number[] = []
  if (s.openAt !== undefined) at.push(s.openAt)
  if (s.closeAt !== undefined) at.push(s.closeAt)
  if (cfg.coexist && !s.muted && s.coreSince !== undefined) at.push(s.coreSince + MUTE_ENTER_MS)
  if (s.muted && s.farSince !== undefined) at.push(s.farSince + MUTE_EXIT_MS)
  return at.length ? Math.min(...at) : undefined
}

/** What the island shows of the hover: the peek, never while muted. */
export const peekOpen = (s: HoverState): boolean => s.open && !s.muted

// ---------------------------------------------------------------------------------------------------------------
// The down-wheel stretch (optional): a scroll down over the island leans it open; past COMMIT it opens.
// ---------------------------------------------------------------------------------------------------------------

export const STRETCH = { commit: 200, lean: 0.08, endMs: 300 } as const
export type Stretch = { progress: number; committed: boolean }
export const STRETCH_IDLE: Stretch = { progress: 0, committed: false }

/** One wheel event (`deltaY` > 0 is down). Returns the new state and whether this event committed the open. */
export function stretchWheel(s: Stretch, deltaY: number): { state: Stretch; commit: boolean } {
  const progress = Math.max(0, s.progress + deltaY)
  const commit = !s.committed && progress >= STRETCH.commit
  return { state: { progress, committed: s.committed || commit }, commit }
}
/**
 * Does the island keep a wheel event for its own stretch? Only a down-wheel whose pointer is over the island's drawn
 * shape: its transparent hover margin (either side and below) and an up-wheel are the app underneath's to scroll.
 * `rect` is the stretch element's box, which includes that margin.
 */
export function stretchKeepsWheel(rect: { left: number; right: number; bottom: number }, x: number, y: number, deltaY: number, margin: number = HOVER.margin): boolean {
  return deltaY > 0 && x >= rect.left + margin && x <= rect.right - margin && y <= rect.bottom - margin
}
/**
 * The island's scale while stretching: it leans open with the wheel, up to 1 + STRETCH.lean at the commit point and no
 * further. (It was 1 + progress * 0.01 with progress in wheel pixels: 3x at the commit, so a scroll on the notch
 * ballooned it to two or three times its size before the panel opened. MIC-83.)
 */
export const stretchScale = (s: Stretch): number => 1 + (Math.max(0, Math.min(s.progress, STRETCH.commit)) / STRETCH.commit) * STRETCH.lean
