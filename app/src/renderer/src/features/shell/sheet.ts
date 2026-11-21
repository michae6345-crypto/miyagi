/**
 * Feature: shell. The account sheet's state (Michael, Nov 21: "one polished app, not windows stacked on windows").
 * Sign-in and the account live INSIDE the home window: a sheet that slides down from the top of the content area
 * (AccountSheet.tsx), never a second window.
 *
 *   kind     signin   "Sign in to sync": the login's own pieces (features/auth store: auth:google, auth:cancel,
 *                     auth:continue), New user / Returning user and the provider boxes
 *            account  who is signed in, Use your own key, Sign out (v2Cloud: the plan, the help meter, Upgrade)
 *            signout  "Sign out of miyagi?" with Cancel and Sign out
 *            plans    v2Cloud only: Pick a plan (features/account Pricing), on paper
 *   back     where Cancel goes from signout (the account sheet when it came from there, else it closes)
 *
 *   openSheet(kind)             show (or switch to) a kind
 *   closeSheet()                hide; a browser sign-in still running is cancelled (auth:cancel), like Esc in the
 *                               login window
 *   openAccountSurface(kind)    for code that may run outside the home window (StatusArea): the sheet when a home
 *                               window is hosting it, otherwise the old account / login window
 */
import { create } from 'zustand'
import { openAccount, openLogin } from '../../core/surfaces'
import { authOn } from '../auth/model'
import { cancelSignIn, useAuth } from '../auth/store'

export type SheetKind = 'signin' | 'account' | 'signout' | 'plans'
export const SHEET_KINDS: readonly SheetKind[] = ['signin', 'account', 'signout', 'plans']
export const isSheetKind = (v: unknown): v is SheetKind => typeof v === 'string' && (SHEET_KINDS as readonly string[]).includes(v)

type State = {
  kind: SheetKind | null
  back?: SheetKind
  /** How many AccountSheet hosts are mounted (the home window has one). */
  hosts: number
}

export const useSheet = create<State>(() => ({ kind: null, hosts: 0 }))

export function openSheet(kind: SheetKind, back?: SheetKind): void {
  useSheet.setState({ kind, back })
}

export function closeSheet(): void {
  if (!useSheet.getState().kind) return
  // Leaving mid-flow cancels the browser sign-in (main closes its loopback listener), as the login window does.
  if (useAuth.getState().pending) cancelSignIn()
  useSheet.setState({ kind: null, back: undefined })
}

/** Cancel on the sign-out confirm: back to the account sheet when it came from there, else close. */
export function backFromSheet(): void {
  const { back } = useSheet.getState()
  if (back) openSheet(back)
  else closeSheet()
}

export function registerSheetHost(): () => void {
  useSheet.setState((s) => ({ hosts: s.hosts + 1 }))
  return () => useSheet.setState((s) => ({ hosts: Math.max(0, s.hosts - 1), kind: s.hosts <= 1 ? null : s.kind }))
}

/** The sheet in the home window; elsewhere (no host), the account or login window as before. */
export function openAccountSurface(kind: 'signin' | 'account' | 'plans'): void {
  if (useSheet.getState().hosts > 0) {
    openSheet(kind)
    return
  }
  if (kind === 'signin') void (authOn ? openLogin('login') : openAccount('signin'))
  else void openAccount(kind === 'plans' ? 'pricing' : 'menu')
}
