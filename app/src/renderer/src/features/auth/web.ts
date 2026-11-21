/**
 * Feature: auth. Browser-stage stand-ins for src/main/features/auth.ts (nothing here runs in Electron).
 *
 *   ?window=auth&view=intro         the first run: the branded intro, then the login
 *   ?window=auth&view=login         the login, no intro
 *   ?auth=signedin                  auth:get answers a fixture learner (also the shell's Account page and chip)
 *   ?auth=fail                      auth:google answers a failure (reason 'timeout')
 *   ?auth=unset                     auth:google answers reason 'not-configured'
 * auth:google waits 1.6 s (the browser round trip) and signs in the fixture. auth:continue opens guided setup
 * (onboarding, view setup) and closes the login, like main on a first run. Mock data only.
 */
import { bridge, isElectron, registerWebHandler } from '../../bridge'
import { closeWindow, openWindow } from '../../core/surfaces'
import type { SignInResult, User } from './model'

const FIXTURE: User = { name: 'Sam Rivera', email: 'sam@example.edu', avatarInitial: 'S' }

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
  registerWebHandler('auth:continue', async () => {
    // Like main: guided setup only while it isn't done (a later sign-in from the Account page just closes the login).
    const onb = await bridge.invoke<{ done?: boolean }>('onboarding:get').catch(() => undefined)
    const setup = !onb?.done
    if (setup) await openWindow('onboarding', { view: 'setup' })
    await closeWindow('auth')
    return { next: setup ? 'setup' : 'none' }
  })
  registerWebHandler('auth:sign-out', () => {
    user = null
    return true
  })
}

if (!isElectron) setupWeb()
