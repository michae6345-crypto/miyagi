/**
 * The island controller's pure decisions (core/Island.tsx wires them to React), so the "stays extended" guarantees are
 * tested offline (test/islandState.test.ts).
 *
 * Michael's symptom: the island sometimes stays extended and never collapses. Every way into an extended state needs a
 * way out. Owned exits live in the feature stores (✕, dismiss, lesson end). This file is the safety net underneath
 * them, for the states that have NO owner:
 *   - the size is card-sized but no card mode is winning (no mode, or a pill mode): "ownerless size"
 *   - the hover card is up but the pointer is gone (a mouseleave that click-through forwarding dropped): "orphan hover"
 *   - the hover card is up and the pointer has done nothing for a long time: "idle hover"
 * A condition must hold for its grace period before the watchdog acts (a spring in flight is not a fault), and acting is
 * idempotent: it only ever sets rest values, so running it twice, or against a state that already moved on, is harmless.
 */
import { pill } from './theme'

export type Modeish = { id: string; width?: number }

/** The first active mode wins (modes arrive sorted by descending priority: core/registry.ts). -1 = none claims the island. */
export function resolveMode(wanted: readonly boolean[]): number {
  return wanted.indexOf(true)
}

/** A pill-sized mode has no card width. */
export function isPillMode(mode: Modeish | undefined): boolean {
  return !mode || mode.width === undefined
}

/** Taller than the pill: extended (a card). */
export function isExtendedSize(size: { w: number; h: number }, restH: number = pill.height): boolean {
  return size.h > restH
}

export const WATCHDOG_TICK_MS = 500
/** An extended size nobody claims must collapse within this. Longer than the spring (~0.5 s) and a mode swap's remeasure. */
export const OWNERLESS_GRACE_MS = 1200
/** The hover card without the pointer on it (the 300 ms leave grace has long run out). */
export const ORPHAN_HOVER_GRACE_MS = 1500
/** The hover card with the pointer on it but nothing moved or pressed for this long: the pointer left unseen. */
export const IDLE_HOVER_MS = 20_000

export type WatchInput = {
  /** The winning mode, if any. */
  mode: Modeish | undefined
  size: { w: number; h: number }
  hover: boolean
  pointerIn: boolean
  /** ms timestamp of the last pointer move / press seen on the island or the window. */
  lastActivity: number
  now: number
  /** In the notch: the notch's height (the island's resting height). Default: the pill's. */
  restH?: number
  /** In the notch: a pill-sized mode is showing a drop (a peek or its content line): taller than rest, legitimately. */
  dropOk?: boolean
}

export type WatchState = { ownerlessSince: number; orphanSince: number }
export const WATCH_REST: WatchState = { ownerlessSince: 0, orphanSince: 0 }

export type WatchAction = { resetSize: boolean; clearHover: boolean }
export const NO_ACTION: WatchAction = { resetSize: false, clearHover: false }

/** One watchdog tick: returns the next timers and what (if anything) to collapse now. Pure. */
export function watchdogStep(state: WatchState, input: WatchInput): { state: WatchState; action: WatchAction } {
  const { mode, size, hover, pointerIn, lastActivity, now } = input

  // Extended, but no card mode is winning: the black box has no owner.
  const ownerless = isExtendedSize(size, input.restH) && isPillMode(mode) && !input.dropOk
  const ownerlessSince = ownerless ? state.ownerlessSince || now : 0
  const resetSize = ownerless && now - ownerlessSince >= OWNERLESS_GRACE_MS

  // The hover card outstayed the pointer, or the pointer stopped doing anything under it.
  const orphan = hover && !pointerIn
  const orphanSince = orphan ? state.orphanSince || now : 0
  const clearHover = (orphan && now - orphanSince >= ORPHAN_HOVER_GRACE_MS) || (hover && now - lastActivity >= IDLE_HOVER_MS)

  return {
    state: { ownerlessSince: resetSize ? 0 : ownerlessSince, orphanSince: clearHover ? 0 : orphanSince },
    action: resetSize || clearHover ? { resetSize, clearHover } : NO_ACTION
  }
}

/** What the island reports to main as its box. Hidden (no mode, or handed to the launcher) = not a click target. */
export function reportedBox(shown: boolean, size: { w: number; h: number }, dx: number, dy: number): { w: number; h: number; dx: number; dy: number; shown: boolean } {
  return { w: size.w, h: size.h, dx, dy, shown }
}
