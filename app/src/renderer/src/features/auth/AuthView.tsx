/**
 * Feature: auth. The login window (route `auth`, kind 'app'): the branded intro (features/onboarding's Intro, the
 * bonsai grows up out of its pot in the middle of the window), then "miyagi login", in one LayoutGroup so the tree
 * travels from the middle of the window into the login's header (shared layoutId).
 *
 * Window args {view}: 'intro' (the first run, main/features/onboarding.ts) plays the intro first; 'login' (a later
 * "Sign in", or a first run whose intro already played) opens on the login.
 */
import { AnimatePresence, LayoutGroup } from 'motion/react'
import { useEffect, useState, type ReactNode } from 'react'
import { useWindowArgs } from '../../core/surfaces'
import { color, copy, font, v4c } from '../../core/theme'
import { Intro } from '../onboarding/Intro'
import { BackButton } from '../onboarding/v4'
import { Login } from './Login'
import { endIntro, loadAuth, useAuth } from './store'

/** How long the window waits for its open args before it opens on the login. */
const ARGS_WAIT_MS = 250

export function AuthView(): ReactNode {
  const args = useWindowArgs('auth')
  const [waited, setWaited] = useState(false)
  /** The view the store's phase was last reset for: nothing renders before that, so a 'login' open never flashes the intro. */
  const [synced, setSynced] = useState<string | undefined>(undefined)
  const phase = useAuth((s) => s.phase)
  const view = args?.view === 'intro' ? 'intro' : args ? 'login' : waited ? 'login' : undefined

  useEffect(() => {
    const t = setTimeout(() => setWaited(true), ARGS_WAIT_MS)
    if (document.title !== copy.name) document.title = copy.name
    return () => clearTimeout(t)
  }, [])

  // Every open (and re-open with another view) starts fresh on that view, with fresh data.
  useEffect(() => {
    if (!view) return
    useAuth.setState({ phase: view, pending: undefined, note: undefined })
    setSynced(view)
    void loadAuth()
  }, [view, args])

  // Esc and leaving mid-wait cancel a waiting sign-in: Login does that itself (useCancelOnEsc), in every host.

  return (
    <div data-window="auth" data-auth-phase={view ? phase : 'loading'} className="relative h-full w-full select-none overflow-hidden" style={{ background: v4c.page, color: color.text, fontFamily: font.ui }}>
      <div data-drag className="absolute inset-x-0 top-0 z-10" style={{ height: 40 }}>
        {/* The one Back of the sign-in (onboarding/back.ts), right of the traffic lights. */}
        <span className="mg-onb4-backslot">
          <BackButton />
        </span>
      </div>
      {view && synced === view && (
        <LayoutGroup>
          <AnimatePresence>{phase === 'intro' ? <Intro key="intro" onDone={endIntro} /> : <Login key="login" />}</AnimatePresence>
        </LayoutGroup>
      )}
    </div>
  )
}
