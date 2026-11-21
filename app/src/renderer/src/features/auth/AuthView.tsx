/**
 * Feature: auth. The whole first-run login surface: Intro, then Login, in one LayoutGroup so the bonsai flies from
 * the middle of the window into the login's header. Mounted by the account window for view 'login' (until core
 * allowlists an 'auth' route of its own; see agents/auth.md, Core requests).
 */
import { AnimatePresence, LayoutGroup } from 'motion/react'
import { useEffect, type ReactNode } from 'react'
import { surface } from '../../core/theme'
import { Intro } from './Intro'
import { Login } from './Login'
import { loadAuth, useAuth } from './store'

export function AuthView({ skipIntro = false }: { skipIntro?: boolean }): ReactNode {
  const phase = useAuth((s) => s.phase)

  useEffect(() => {
    useAuth.setState({ phase: skipIntro ? 'login' : 'intro', pending: undefined, note: undefined })
    void loadAuth()
  }, [skipIntro])

  return (
    <div data-auth-phase={phase} className="relative h-full w-full overflow-hidden" style={{ background: surface.window }}>
      <div data-drag className="absolute inset-x-0 top-0 z-10" style={{ height: 28 }} />
      <LayoutGroup>
        <AnimatePresence>{phase === 'intro' ? <Intro key="intro" /> : <Login key="login" />}</AnimatePresence>
      </LayoutGroup>
    </div>
  )
}
