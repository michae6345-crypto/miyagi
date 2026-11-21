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
import { cleanUser, LEGAL, LIVE, PROVIDER_LABEL, reasonLine, type Mode, type Provider, type SignInResult, type User } from './model'

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
export function say(note: string | undefined): void {
  clearTimeout(noteTimer)
  useAuth.setState({ note })
  if (note) noteTimer = setTimeout(() => useAuth.setState({ note: undefined }), 6000)
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

export async function signInWith(p: Provider): Promise<void> {
  if (useAuth.getState().pending) return
  if (!LIVE[p]) {
    say(`${PROVIDER_LABEL[p]} sign-in is coming soon. Nothing was sent.`)
    return
  }
  say(undefined)
  useAuth.setState({ pending: p })
  try {
    const r = await bridge.invoke<SignInResult>(`auth:${p}`, { mode: useAuth.getState().mode })
    if (r && r.ok) useAuth.setState({ user: cleanUser(r.user) })
    else say(reasonLine(r?.reason))
  } catch {
    say(reasonLine())
  } finally {
    useAuth.setState({ pending: undefined })
  }
}

/** Stop waiting for the browser (main closes its loopback listener). */
export function cancelSignIn(): void {
  bridge.invoke('auth:cancel').catch(() => undefined)
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
