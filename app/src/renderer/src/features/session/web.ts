/**
 * Feature: session. Browser-stage stand-in for src/main/features/cloudSession.ts (nothing here runs in Electron).
 *
 *   ?session=caps      signed in (pair with &auth=signedin), Free plan, $0.42 of $3.00 today, resets at the next UTC
 *                      midnight in local time (the default with &auth=signedin)
 *   ?session=pro       signed in, Pro plan, no daily cap
 *   ?session=build     a guest; the cloud needs an account to build new lessons (signin_mode "build")
 *   ?session=all       a guest; the cloud needs an account for everything (signin_mode "all")
 *   ?session=none      nothing cached yet (signed out, or a cloud that never answered)
 * Mock data only.
 */
import { isElectron, registerWebHandler } from '../../bridge'
import type { SessionView } from './model'

const nextUtcMidnight = (): string => {
  const d = new Date()
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1)).toISOString()
}

function setupWeb(): void {
  const params = new URLSearchParams(location.search)
  const signedIn = params.get('auth') === 'signedin'
  const variant = params.get('session') ?? (signedIn ? 'caps' : 'none')
  const fetchedAt = new Date().toISOString()
  registerWebHandler('session:get', (): SessionView => {
    if (variant === 'build' || variant === 'all') return { signedIn: false, linked: false, signinMode: variant, fetchedAt }
    if (variant === 'pro' && signedIn)
      return { signedIn, linked: true, signinMode: 'off', plan: 'pro', caps: { dailyUsd: null, usedUsd: 1.27, tokens: null, usedTokens: 412000, resetsAt: nextUtcMidnight() }, fetchedAt }
    if (variant === 'caps' && signedIn)
      return { signedIn, linked: true, signinMode: 'off', plan: 'free', caps: { dailyUsd: 3, usedUsd: 0.42, tokens: 20000000, usedTokens: 183000, resetsAt: nextUtcMidnight() }, fetchedAt }
    return { signedIn, linked: signedIn, signinMode: 'off' }
  })
}

if (!isElectron) setupWeb()
