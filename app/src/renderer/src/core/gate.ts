/**
 * Core: the sign-in gate, as this window sees it (lane overlay-gate, agents/overlay-gate.md). A renderer backstop:
 * nothing in the overlay draws, asks or schedules before the gate opens, even if main shows the window early.
 *
 * Main owns the gate (main/gate.ts, lane login-first). This store only mirrors it:
 *   onboarding:get           answers { ..., gate: { login, setup, open } }
 *   feat:onboarding:gate     broadcasts { login, setup, open } whenever it changes
 * Parsed defensively: only open === true opens it.
 *
 *   open    the gate is open (until main first answers: closed)
 *   known   main answered at least once (or a broadcast arrived)
 *
 * Compatibility: a main that answers onboarding:get without a `gate` field predates the gate, so the gate reads OPEN
 * (this lane merges alone). A main with no onboarding:get handler at all (Electron's "No handler registered for
 * 'feat:onboarding:get'", RETRIES times, RETRY_MS apart) reads open too.
 * Any other failure (main's handler threw: a bad onboarding.json, an error in its sign-in check) is not an older main:
 * the gate stays closed and the ask repeats with a capped backoff (RETRY_MS doubling up to MAX_RETRY_MS) until main
 * answers or a feat:onboarding:gate broadcast arrives. Only main ever opens the gate.
 */
import { useSyncExternalStore } from 'react'
import { create } from 'zustand'
import { bridge } from '../bridge'

export type GateState = { open: boolean; known: boolean }

export const useGate = create<GateState>(() => ({ open: false, known: false }))

/** A missing onboarding:get handler (an older main, or main still starting): ask again this often, this many times. */
export const RETRY_MS = 1000
export const RETRIES = 3
/** Any other failure: ask again after RETRY_MS, doubling, never longer than this. The gate stays closed meanwhile. */
export const MAX_RETRY_MS = 15000

/** Electron's rejection when main registered no handler for the channel: the one failure that reads as an older main. */
const NO_HANDLER = /No handler registered for 'feat:onboarding:get'/

/** True when an onboarding:get rejection means main has no handler for it (and nothing else). */
export function isNoHandler(err: unknown): boolean {
  const text = err instanceof Error ? err.message : typeof err === 'string' ? err : ''
  return NO_HANDLER.test(text)
}

/** True for the gate part of an onboarding:get answer: no `gate` field = an older main (open); else gate.open === true. */
export function gateFromAnswer(answer: unknown): boolean {
  if (!answer || typeof answer !== 'object') return false
  if (!('gate' in answer)) return true
  return gateFromBroadcast((answer as { gate?: unknown }).gate)
}

/** True for a feat:onboarding:gate payload ({ login, setup, open }) only when open === true. */
export function gateFromBroadcast(payload: unknown): boolean {
  return !!payload && typeof payload === 'object' && (payload as { open?: unknown }).open === true
}

function apply(open: boolean): void {
  const s = useGate.getState()
  if (s.open !== open || !s.known) useGate.setState({ open, known: true })
}

/** A broadcast is newer than any answer still in flight: once one arrives, a late answer never overrides it. */
let heard = false
let started = false
/** Rejections so far: "No handler registered" ones (they open the gate at RETRIES), and every other kind. */
let noHandler = 0
let failed = 0

function ask(): void {
  if (heard) return // a broadcast already said where the gate is: stop asking
  let p: Promise<unknown>
  try {
    p = bridge.invoke<unknown>('onboarding:get')
  } catch (err) {
    p = Promise.reject(err)
  }
  p.then(
    (answer) => {
      if (!heard) apply(gateFromAnswer(answer))
    },
    (err: unknown) => {
      if (heard) return
      if (isNoHandler(err)) {
        noHandler += 1
        if (noHandler >= RETRIES) return apply(true) // a main from before onboarding:get never blocks the overlay
        setTimeout(ask, RETRY_MS)
        return
      }
      // main has the handler and it failed: never a reason to open. Stay closed and ask again, a little later each time.
      setTimeout(ask, Math.min(RETRY_MS * 2 ** failed, MAX_RETRY_MS))
      failed += 1
    }
  )
}

/** Subscribe and ask main once. Idempotent; runs at load (after this tick, so every stage stand-in is registered). */
export function startGate(): void {
  if (started) return
  started = true
  bridge.onFeature('onboarding:gate', (payload) => {
    heard = true
    apply(gateFromBroadcast(payload))
  })
  setTimeout(ask, 0)
}

export const gateIsOpen = (): boolean => useGate.getState().open

/**
 * Whether the gate is open, for components and island modes. Reads the live store on the server snapshot too, so a
 * Node render (test/overlayGate.test.ts) sees the same thing a window does.
 */
export function useGateOpen(): boolean {
  return useSyncExternalStore(useGate.subscribe, gateIsOpen, gateIsOpen)
}

/**
 * Run `fn` each time the gate opens (now, if it already is). Returns an unsubscribe. For work that must wait for the
 * gate: a launch-time ask (errors:crash-pending), a scheduled check (progress review).
 */
export function onGateOpen(fn: () => void): () => void {
  if (gateIsOpen()) fn()
  return useGate.subscribe((s, prev) => {
    if (s.open && !prev.open) fn()
  })
}

/** Run `fn` each time the gate closes again (a sign-out): drop timers that were scheduled while it was open. */
export function onGateClose(fn: () => void): () => void {
  return useGate.subscribe((s, prev) => {
    if (!s.open && prev.open) fn()
  })
}

startGate()
