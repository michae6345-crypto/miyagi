/**
 * Feature: auth. The login window's state. Memory only: nothing here goes to localStorage or a log.
 *
 *   phase    intro (the bonsai grows in) → login
 *   mode     New user / Returning user (only the copy and the provider labels change; OAuth is the same call)
 *   pending  the provider whose browser sign-in is running
 *   user     the signed-in learner (name, email), or null
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { closeWindow, openOnboarding } from '../../core/surfaces'
import { cleanUser, LIVE, PROVIDER_LABEL, reasonLine, type Mode, type Provider, type SignInResult, type User } from './model'

type State = {
  phase: 'intro' | 'login'
  mode: Mode
  pending?: Provider
  user: User | null
  note?: string
}

export const useAuth = create<State>(() => ({ phase: 'intro', mode: 'new', user: null }))

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
    useAuth.setState({ user: cleanUser(await bridge.invoke<unknown>('auth:get')) })
  } catch {
    useAuth.setState({ user: null })
  }
}

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
    if (r && r.ok) useAuth.setState({ user: cleanUser({ ...r.user, signedIn: true }) })
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
 * Login done (or skipped): on to guided setup. The flow is intro → login → setup → home.
 * The login lives in the account window (view 'login') until core allowlists its own 'auth' route (Core requests).
 */
export function continueToSetup(): void {
  void openOnboarding().then(() => closeWindow('account'))
}
