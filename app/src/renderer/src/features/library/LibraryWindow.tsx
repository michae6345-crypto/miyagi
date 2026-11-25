/**
 * Feature: library. The home window (route `library`): the app shell (features/shell) with its sidebar and six pages.
 * Each open carries its own args:
 *   {}                        the page the learner was on (Home on a fresh window)
 *   {id}                      that lesson's preview, over Lessons (openLibrary(id))
 *   {page, section?}          that page, and for Settings that section (openPage in features/shell/store.ts)
 * Loads on open, whenever the window comes forward, and when the engine connects. The window title stays "miyagi".
 */
import { useEffect, type ReactNode } from 'react'
import { bridge, isElectron } from '../../bridge'
import { canSend, useLesson } from '../../core/lesson'
import { loadPlans } from '../plans/store'
import { useWindowArgs, type WindowArgs } from '../../core/surfaces'
import { color, font } from '../../core/theme'
import { Shell } from '../shell/Shell'
import { isPage, isSettingsSection, setPage, setSettingsSection } from '../shell/store'
import { closeDetail, openDetail, refresh } from './store'

/** Stage only: ?page=<id> (&section=<section>) opens the window on that page, for the shell's screenshots. */
const stageArgs: WindowArgs | undefined = (() => {
  if (!isElectron) {
    const q = new URLSearchParams(location.search)
    const page = q.get('page')
    if (isPage(page)) return { page, ...(isSettingsSection(q.get('section')) ? { section: q.get('section')! } : {}) }
  }
  return undefined
})()

function apply(args: WindowArgs | null | undefined): void {
  if (args && typeof args.id === 'string') {
    setPage('lessons')
    openDetail(args.id)
    return
  }
  if (args && isPage(args.page)) {
    if (isSettingsSection(args.section)) setSettingsSection(args.section)
    setPage(args.page)
    return
  }
  // Opened again with no args (openLibrary()): the page stays, a preview over it closes.
  closeDetail()
}

export function LibraryWindow(): ReactNode {
  const args = useWindowArgs('library')
  const connected = useLesson((s) => s.connected)
  const hello = useLesson((s) => s.hello)

  useEffect(() => {
    if (stageArgs) apply(stageArgs)
  }, [])
  useEffect(() => {
    apply(args)
  }, [args])
  // useWindowArgs can't tell "opened without args" from "not loaded yet", so a re-open with no args is read here:
  // openLibrary() on a window showing a preview closes the preview (the page stays). (Electron sends the args to this
  // window only; the stage's one bus tags them with the route.)
  useEffect(
    () =>
      bridge.onFeature('window:args', (p) => {
        const tagged = !!p && typeof p === 'object' && 'route' in p
        if (tagged && (p as { route?: unknown }).route !== 'library') return
        const a = (tagged ? (p as { args?: unknown }).args : p) as { id?: unknown } | null | undefined
        if (!a || typeof a.id !== 'string') closeDetail()
      }),
    []
  )

  useEffect(() => {
    void refresh()
    // The sidebar's Plans show on every page (plans/store feeds them), so ask once the engine says it answers.
    if (connected && canSend('plans.list')) loadPlans()
  }, [connected, hello])

  useEffect(() => {
    const onFocus = (): void => void refresh()
    addEventListener('focus', onFocus)
    return () => removeEventListener('focus', onFocus)
  }, [])

  return (
    <div data-window="library" className="h-full w-full select-none overflow-hidden" style={{ fontFamily: font.ui, background: color.window }}>
      <Shell />
    </div>
  )
}
