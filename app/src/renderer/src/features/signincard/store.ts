/**
 * Feature: signincard. Brief: app/agents/signincard.md
 *
 * The engine forwards the shared-lesson-cache notice (server/lesson/cloud_cache.py on_notice) as:
 *
 *   cloud.notice {reason, status, resets_at?}             the target event (needs the contract + wire.ts KNOWN: Core requests)
 *   error {message, notice: {reason, status, resets_at?}}  works with today's app core: Error allows extra fields and
 *                                                          wire.ts keeps the payload as sent. Its pill line is dropped
 *                                                          here, since the card or the line says it better.
 *
 * State:
 *   signin   the sign-in card is up (401 signin_required), until Sign in succeeds, Not now or Esc
 *   cap      the cap line (429), until Esc or CAP_MS
 *   tried    Sign in was pressed from this card (its failure line shows under the buttons)
 *   visible  which of the two is the one on the island right now (Esc closes only what the learner sees)
 */
import { create } from 'zustand'
import { onMessage, onUi, type MessageType } from '../../core/bus'
import { dismissNotice, notify } from '../../core/lesson'
import { signInWith, useAuth } from '../auth/store'
import { capLine, classify, parseNotice, SIGNIN, type CapKind } from './notice'

export const CAP_MS = 10_000

type Shown = 'signin' | 'cap'
type State = {
  signin?: { at: number }
  cap?: { kind: CapKind; line: string; at: number }
  tried: boolean
  visible?: Shown
}

export const useSignInCard = create<State>(() => ({ tried: false }))
const set = useSignInCard.setState
const get = useSignInCard.getState

let capTimer: ReturnType<typeof setTimeout> | undefined

/** One notice from the engine. Returns what it showed (for the test), or null for a notice with no UI. */
export function receive(raw: unknown, now: Date = new Date()): Shown | null {
  const n = parseNotice(raw)
  const c = n && classify(n)
  if (!n || !c) return null
  if (c.kind === 'signin') {
    if (useAuth.getState().user) return null // signed in since: the next build claim will go through
    set({ signin: { at: now.getTime() }, tried: false })
    return 'signin'
  }
  clearTimeout(capTimer)
  const at = now.getTime()
  set({ cap: { kind: c.cap, line: capLine(n, now), at } })
  capTimer = setTimeout(() => {
    if (get().cap?.at === at) closeCap()
  }, CAP_MS)
  return 'cap'
}

export function notNow(): void {
  set({ signin: undefined, tried: false })
}

export function closeCap(): void {
  clearTimeout(capTimer)
  set({ cap: undefined })
}

/** Sign in: the existing Google flow (features/auth: system browser, PKCE, loopback). The card closes on success. */
export function signIn(): void {
  set({ tried: true })
  void signInWith('google')
}

export function setVisible(which: Shown, on: boolean): void {
  if (on) set({ visible: which })
  else if (get().visible === which) set({ visible: undefined })
}

// Engine → app. The target event (dropped by wire.ts until it is in KNOWN; the stage's inline mock delivers it).
onMessage('cloud.notice' as string as MessageType, (p) => {
  receive(p)
})
// Today's transport: an engine error frame carrying the notice. Its generic pill line goes once the dispatch is done.
onMessage('error', (p) => {
  const notice = (p as { notice?: unknown }).notice
  if (notice === undefined || receive(notice) === null) return
  queueMicrotask(() => dismissNotice('engine-error'))
})

// Signed in (here or in the login window): the card has done its job.
useAuth.subscribe((s, prev) => {
  if (!s.user || prev.user) return
  if (get().signin) {
    const pressed = get().tried
    notNow()
    if (pressed) notify(SIGNIN.signedIn, 'info', { id: 'signincard-done' })
  }
})

onUi('dismiss', () => {
  const v = get().visible
  if (v === 'signin') notNow()
  else if (v === 'cap') closeCap()
})
onUi('reset', () => {
  clearTimeout(capTimer)
  set({ signin: undefined, cap: undefined, tried: false, visible: undefined })
})
