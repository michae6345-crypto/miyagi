/**
 * The account window (app window, route `account`; decision 4). One window, four views, picked by openAccount(view)
 * (core/surfaces.ts, args {view}) and by the views themselves (Upgrade → Pricing, Sign out → Sign in).
 *
 *   menu     Plan-AccountMenu (needs an account; signed out → Sign in)
 *   upgrade  Plan-Upgrade
 *   signin   Plan-SignIn
 *   pricing  Plan-Pricing, on paper
 *
 * Esc goes back one view, or closes the window when there is nothing to go back to. Nothing here can block a lesson:
 * the window only reads the account and opens Settings, Library or main's fixed links.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import type { Layout } from '../../../../preload/api'
import { closeWindow, useWindowArgs } from '../../core/surfaces'
import { spring, surface } from '../../core/theme'
import { isView, type View } from './model'
import { Menu } from './Menu'
import { Pricing } from './Pricing'
import { SignIn } from './SignIn'
import { Upgrade } from './Upgrade'
import { loadAccount, useAccount } from './store'
import { Note } from './ui'

export function AccountWindow({ layout }: { layout: Layout }): ReactNode {
  const args = useWindowArgs('account')
  const [stack, setStack] = useState<View[]>(['menu'])
  const account = useAccount((s) => s.account)
  const loaded = useAccount((s) => s.loaded)
  const note = useAccount((s) => s.note)

  // Every open (and re-open with another view) starts fresh on that view, with fresh data.
  useEffect(() => {
    const v = args?.view
    setStack([isView(v) ? v : 'menu'])
    void loadAccount()
  }, [args])

  const go = useCallback((v: View) => setStack((s) => [...s, v]), [])
  const close = useCallback(() => void closeWindow('account'), [])
  const back = useCallback(() => {
    if (stack.length > 1) setStack((s) => s.slice(0, -1))
    else close()
  }, [stack.length, close])

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault()
      back()
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [back])

  let view = stack[stack.length - 1]
  // The menu belongs to someone: signed out (or no account backend yet) it is Sign in.
  if (view === 'menu' && loaded && !account?.signedIn) view = 'signin'
  const paper = view === 'pricing'

  return (
    <div data-account-view={view} className="relative h-full w-full overflow-y-auto" style={{ background: paper ? undefined : surface.sheet }}>
      <div data-drag className="absolute inset-x-0 top-0 z-10" style={{ height: 28 }} />
      {!loaded ? null : paper ? (
        <Pricing account={account} width={layout.width} />
      ) : (
        <div className="flex min-h-full flex-col items-center justify-center gap-[12px]" style={{ padding: '44px 16px 24px' }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={view} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={spring}>
              {view === 'menu' && account ? <Menu account={account} go={go} /> : view === 'upgrade' ? <Upgrade account={account} go={go} close={close} /> : <SignIn />}
            </motion.div>
          </AnimatePresence>
          <Note text={note} />
        </div>
      )}
      {paper && note && (
        <div className="sticky bottom-0 pb-[12px]">
          <Note text={note} tone="paper" />
        </div>
      )}
    </div>
  )
}
