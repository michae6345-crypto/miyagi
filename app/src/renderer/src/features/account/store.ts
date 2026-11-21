/**
 * Feature: account. The account window's state: the account (or null: signed out / no backend), whether the learner
 * has their own key (read from the settings feature's `settings:get`, which only ever returns {set, last4}), and a
 * short line for actions that are not live yet. Memory only: nothing here goes to localStorage or a log.
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { cleanAccount, type Account, type AccountLink } from './model'

type State = {
  account: Account | null
  loaded: boolean
  /** Any BYOK key saved in Settings. undefined = unknown (settings feature not answering). */
  ownKey?: boolean
  /** One calm line under the surface ("Sign in is not live yet. Nothing was sent."). */
  note?: string
}

export const useAccount = create<State>(() => ({ account: null, loaded: false }))

let noteTimer: ReturnType<typeof setTimeout> | undefined
export function say(note: string): void {
  clearTimeout(noteTimer)
  useAccount.setState({ note })
  noteTimer = setTimeout(() => useAccount.setState({ note: undefined }), 5000)
}

export async function loadAccount(): Promise<void> {
  const [acc, keys] = await Promise.allSettled([bridge.invoke<unknown>('account:get'), bridge.invoke<unknown>('settings:get')])
  const account = acc.status === 'fulfilled' ? cleanAccount(acc.value) : null
  let ownKey: boolean | undefined
  if (keys.status === 'fulfilled' && keys.value && typeof keys.value === 'object') {
    const k = (keys.value as { keys?: Record<string, { set?: unknown } | undefined> }).keys
    if (k && typeof k === 'object') ownKey = Object.values(k).some((v) => v?.set === true)
  }
  useAccount.setState({ account, ownKey, loaded: true })
}

/** Open one of main's fixed account links in the browser. Never a URL from here. */
export function openLink(link: AccountLink): void {
  bridge.invoke<boolean>('account:open', link).then(
    (ok) => {
      if (!ok) say('That page is not available yet.')
    },
    () => say('That page is not available yet.')
  )
}

/** Sign out: nothing is stored on this Mac in this push, so it only forgets the account in this window. */
export function signOut(): void {
  bridge.invoke('account:sign-out').catch(() => undefined)
  useAccount.setState({ account: null })
}
