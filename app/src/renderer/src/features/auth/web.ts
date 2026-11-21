/**
 * Feature: auth. Browser-stage stand-ins for src/main/features/auth.ts (nothing here runs in Electron).
 *
 *   ?window=account&view=login      opens the login (intro first)
 *   ?window=account&view=login-now  opens it on the login, no intro
 *   ?auth=signedin                  auth:get answers a fixture learner
 *   ?auth=fail                      auth:google answers a failure (reason 'timeout')
 *   ?auth=unset                     auth:google answers reason 'not-configured'
 * auth:google waits 1.6 s (the browser round trip) and signs in the fixture. Mock data only.
 */
import { isElectron, registerWebHandler } from '../../bridge'
import type { SignInResult, User } from './model'

const FIXTURE: User = { name: 'Sam Rivera', email: 'sam@example.edu' }

function setupWeb(): void {
  const params = new URLSearchParams(location.search)
  const variant = params.get('auth')
  let user: User | null = variant === 'signedin' ? FIXTURE : null
  let pending: ((r: SignInResult) => void) | undefined
  let timer: ReturnType<typeof setTimeout> | undefined

  registerWebHandler('auth:get', () => (user ? { signedIn: true, ...user } : null))
  registerWebHandler(
    'auth:google',
    () =>
      new Promise<SignInResult>((resolve) => {
        pending = resolve
        timer = setTimeout(() => {
          pending = undefined
          if (variant === 'fail') return resolve({ ok: false, reason: 'timeout' })
          if (variant === 'unset') return resolve({ ok: false, reason: 'not-configured' })
          user = FIXTURE
          resolve({ ok: true, user: FIXTURE })
        }, 1600)
      })
  )
  registerWebHandler('auth:cancel', () => {
    clearTimeout(timer)
    pending?.({ ok: false, reason: 'cancelled' })
    pending = undefined
    return true
  })
  registerWebHandler('auth:sign-out', () => {
    user = null
    return true
  })
}

if (!isElectron) setupWeb()
