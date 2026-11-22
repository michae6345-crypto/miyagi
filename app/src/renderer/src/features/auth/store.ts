/**
 * Feature: auth. The login's state, and the signed-in learner for every window (the shell's Account page and sidebar
 * chip read `user` from here). Memory only: nothing here goes to localStorage or a log.
 *
 *   phase    intro (the branded intro grows in) → login
 *   mode     New user / Returning user (only the copy and the provider labels change; OAuth is the same call)
 *   pending  the provider whose browser sign-in is running
 *   user     the signed-in learner {name, email, avatarInitial}, or null
 *   loaded   auth:get answered once in this window
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { BACK_LINE, CANCELLED_LINE, cleanUser, LEGAL, LIVE, PROVIDER_LABEL, reasonLine, type Mode, type Provider, type SignInResult, type User } from './model'

type State = {
  phase: 'intro' | 'login'
  mode: Mode
  pending?: Provider
  user: User | null
  loaded: boolean
  note?: string
}

export const useAuth = create<State>(() => ({ phase: 'intro', mode: 'new', user: null, loaded: false }))

let noteTimer: ReturnType<typeof setTimeout> | undefined
/** stay: keep the line until the next click (a failed sign-in's reason must not vanish while the learner reads it). */
export function say(note: string | undefined, stay = false): void {
  clearTimeout(noteTimer)
  useAuth.setState({ note })
  if (note && !stay) noteTimer = setTimeout(() => useAuth.setState({ note: undefined }), 6000)
}

export const setMode = (mode: Mode): void => useAuth.setState({ mode })
export const endIntro = (): void => useAuth.setState({ phase: 'login' })

export async function loadAuth(): Promise<void> {
  try {
    useAuth.setState({ user: cleanUser(await bridge.invoke<unknown>('auth:get')), loaded: true })
  } catch {
    useAuth.setState({ user: null, loaded: true })
  }
}

// Main tells every window when the learner signs in or out (feat:auth:changed), so the home window's chip follows
// a sign-in that happened in the login window.
bridge.onFeature('auth:changed', (u) => useAuth.setState({ user: cleanUser(u), loaded: true }))

// ---- the browser round trip (R20: a Cancel, a closed tab or a timeout never leaves the learner waiting) ----------
/**
 * turn: which signInWith call owns the screen. The wait can end before main answers (Cancel here, Cancel on Google's
 * page, coming back to miyagi); bumping turn then drops that call's late failure, so it never overwrites the line
 * shown or a newer try. A late SUCCESS still signs in (main finished a real sign-in; the tab's Try again can do that).
 * open: auth:google calls not answered yet in this window (main may still be listening after the wait ended).
 * away: when this window lost focus during the current wait (see the focus listeners below).
 */
let turn = 0
let open = 0
let away: number | undefined

/** End the wait now with this line (undefined: no line). Main is told separately (or keeps listening on purpose). */
function endWait(line: string | undefined): void {
  turn++
  useAuth.setState({ pending: undefined })
  say(line, true)
}

export async function signInWith(p: Provider): Promise<void> {
  if (useAuth.getState().pending) return
  if (!LIVE[p]) {
    say(`${PROVIDER_LABEL[p]} sign-in is coming soon. Nothing was sent.`)
    return
  }
  say(undefined)
  const mine = ++turn
  away = undefined
  useAuth.setState({ pending: p })
  open++
  try {
    const r = await bridge.invoke<SignInResult>(`auth:${p}`, { mode: useAuth.getState().mode })
    if (r && r.ok) {
      useAuth.setState({ user: cleanUser(r.user) })
      say(undefined)
    } else if (mine === turn) say(reasonLine(r?.reason, r?.message), true)
  } catch {
    if (mine === turn) say(reasonLine(), true)
  } finally {
    open--
    if (mine === turn) useAuth.setState({ pending: undefined })
  }
}

/** The Cancel link and Esc: the wait ends at once with a calm line (Try again under it), and main stops listening. */
export function cancelSignIn(): void {
  if (useAuth.getState().pending) endWait(CANCELLED_LINE)
  bridge.invoke('auth:cancel').catch(() => undefined)
}

/** A browser sign-in runs in this window, shown as waiting or not (main may still be listening after the wait ended). */
export const signInOpen = (): boolean => !!useAuth.getState().pending || open > 0

/** Leaving the login (it unmounts, its window closes): stop quietly. Nothing is left on screen for a later visit. */
export function leaveSignIn(): void {
  if (!signInOpen()) return
  endWait(undefined)
  bridge.invoke('auth:cancel').catch(() => undefined)
}

// Main tells every window when a browser attempt came back without a sign-in (feat:auth:attempt): Cancel on Google's
// page, Google's or Supabase's error, a refused code. The window that is waiting stops at once and says why. Main keeps
// its listener up on purpose (the tab's Try again still works; a forged error callback can't end a real sign-in), so
// a later success there still signs in. Another try from the tab that fails again just updates the line.
bridge.onFeature('auth:attempt', (raw) => {
  if (!signInOpen()) return
  const why = (raw && typeof raw === 'object' ? raw : {}) as { reason?: unknown; message?: unknown }
  endWait(reasonLine(typeof why.reason === 'string' ? why.reason : undefined, why.message))
})

/**
 * Closing the browser tab sends nothing back: the only sign is the learner coming back to miyagi. If this window lost
 * focus while waiting (the browser came up) for at least AWAY_MS and then gets it back, the wait ends after BACK_MS
 * with "Didn't finish in the browser? Try again." A real sign-in brings miyagi forward too, but its answer lands well
 * inside BACK_MS, so it never flashes the line; one finished later in the still-open tab still signs in.
 */
const AWAY_MS = 2000
const BACK_MS = 1500
if (typeof window !== 'undefined') {
  window.addEventListener('blur', () => {
    if (useAuth.getState().pending) away = Date.now()
  })
  window.addEventListener('focus', () => {
    const left = away
    away = undefined
    if (left === undefined || !useAuth.getState().pending || Date.now() - left < AWAY_MS) return
    const mine = turn
    setTimeout(() => {
      if (mine === turn && useAuth.getState().pending && document.hasFocus()) endWait(BACK_LINE)
    }, BACK_MS)
  })
}

export function signOut(): void {
  bridge.invoke('auth:sign-out').catch(() => undefined)
  useAuth.setState({ user: null })
}

/**
 * Done with the login (signed in, or "Continue without an account"). Main remembers the choice (the login never shows
 * on launch again), opens guided setup on the first run, and closes the login window once setup is showing.
 */
export function continueToSetup(): void {
  bridge.invoke('auth:continue').catch(() => undefined)
}

export function openLegal(page: keyof typeof LEGAL): void {
  bridge.invoke('open:external', LEGAL[page]).catch(() => undefined)
}
