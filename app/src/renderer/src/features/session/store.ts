/**
 * Feature: session. The account's plan, today's use and the cloud's sign-in mode, for every window (Settings › Your own
 * key reads it; signincard reads it at the start of a build). Memory only: nothing here goes to localStorage or a log.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { useAuth } from '../auth/store'
import { cleanSession, type SessionView } from './model'
import './web' // the stage's session:get must exist before the first load below, whoever imports this store first

type State = { view: SessionView | null; loaded: boolean }

export const useSession = create<State>(() => ({ view: null, loaded: false }))

export async function loadSession(): Promise<void> {
  try {
    useSession.setState({ view: cleanSession(await bridge.invoke<unknown>('session:get')), loaded: true })
  } catch {
    useSession.setState({ view: null, loaded: true }) // no main handler (an older build): show nothing
  }
}

// Main tells every window when the cache changes (a 200, a sign-out).
bridge.onFeature('session', (v) => useSession.setState({ view: cleanSession(v), loaded: true }))

// Signed in or out in any window: ask again (main drops the account's numbers on sign-out).
useAuth.subscribe((s, prev) => {
  if (!!s.user !== !!prev.user) void loadSession()
})

void loadSession()
