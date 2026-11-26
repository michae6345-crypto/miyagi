/**
 * Feature: signincard. Brief: app/agents/signincard.md
 *
 * The engine forwards the shared-lesson-cache notice (server/lesson/cloud_cache.py on_notice) as:
 *
 *   cloud.notice {reason, status, resets_at?}             the main path (contract + wire.ts KNOWN, Nov 24): the engine
 *                                                          registers on_notice in Engine.watch_cloud
 *   error {message, notice: {reason, status, resets_at?}}  fallback, kept for an engine that sends the notice that way:
 *                                                          Error allows extra fields and wire.ts keeps the payload as
 *                                                          sent. Its pill line is dropped here, since the card or the
 *                                                          line says it better.
 *
 * MIC-30: when miyagi-cloud's signin_mode (features/session, POST /v1/session) is "build" or "all" and the learner is a
 * guest (not signed in, install not linked), the same card shows as a new lesson build starts (the first
 * lesson.building of a build), without waiting for the cloud to refuse the claim. "off": the notice alone, as before.
 *
 * State:
 *   signin   the sign-in card is up (401 signin_required, or a guest's build start), until Sign in succeeds, Not now or Esc
 *   cap      the cap line (429), until Esc or CAP_MS
 *   region   the region line (451 region_unavailable, from the engine's cloud.notice or main's install mint): no Sign
 *            in (it would not help), until Not now or Esc. Once per launch: a learner who closed it is not told again
 *   tried    Sign in was pressed from this card (its failure line shows under the buttons)
 *   visible  which of the two is the one on the island right now (Esc closes only what the learner sees)
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { dismissNotice, notify } from '../../core/lesson'
import { signInWith, useAuth } from '../auth/store'
import { promptsOnBuild } from '../session/model'
import { useSession } from '../session/store'
import { capLine, classify, parseNotice, REGION_NOTICE, SIGNIN, type CapKind } from './notice'

export const CAP_MS = 10_000

type Shown = 'signin' | 'cap' | 'region'
type State = {
  signin?: { at: number }
  cap?: { kind: CapKind; line: string; at: number }
  region?: { at: number }
  /** The region line was shown this launch (it is not shown again, and no sign-in card follows it). */
  regionSeen?: boolean
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
  if (c.kind === 'region') {
    if (get().regionSeen) return null
    set({ region: { at: now.getTime() }, regionSeen: true, signin: undefined, tried: false }) // signing in would not help
    return 'region'
  }
  if (c.kind === 'signin') {
    if (get().regionSeen) return null // the region block answers first: signing in would not help
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

export function closeRegion(): void {
  set({ region: undefined })
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

// Engine → app: the main path.
onMessage('cloud.notice', (p) => {
  receive(p)
})
// Fallback: an engine error frame carrying the notice. Its generic pill line goes once the dispatch is done.
onMessage('error', (p) => {
  const notice = (p as { notice?: unknown }).notice
  if (notice === undefined || receive(notice) === null) return
  queueMicrotask(() => dismissNotice('engine-error'))
})

// A guest starts a new lesson build while the cloud wants an account for it (signin_mode "build" / "all"): once per build.
let building = false
/** One lesson.building frame. Returns true when it put the card up (for the test). */
export function buildStarted(p: { failed?: boolean }, now: Date = new Date()): boolean {
  if (p.failed) {
    building = false
    return false
  }
  if (building) return false
  building = true
  if (get().regionSeen) return false // the region block: a sign-in card would not help
  if (!promptsOnBuild(useSession.getState().view, !!useAuth.getState().user)) return false
  set({ signin: { at: now.getTime() }, tried: false })
  return true
}
const buildDone = (): void => {
  building = false
}
onMessage('lesson.building', (p) => {
  buildStarted(p)
})
onMessage('lesson.ready', buildDone)
onMessage('lesson.ended', buildDone)

/** main/features/cloud.ts's CloudView (index.tsx subscribes): POST /v1/install answered 451 region_unavailable, so no
 *  engine notice can come (no token). Returns what it showed. */
export function cloudView(c: { region?: boolean } | undefined): Shown | null {
  return c?.region ? receive(REGION_NOTICE) : null
}

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
  else if (v === 'region') closeRegion()
  else if (v === 'cap') closeCap()
})
onUi('reset', () => {
  buildDone()
  clearTimeout(capTimer)
  set({ signin: undefined, cap: undefined, region: undefined, regionSeen: false, tried: false, visible: undefined })
})
