/**
 * Feature: onboarding (A3). The Onboarding app window (route `onboarding`, kind 'app'; BUILD-PLAN decision 4).
 *
 *   welcome    Onb-Setup-Full: the first run, two panes (main/features/onboarding.ts opens it at 944×640)
 *   checklist  Onb-Checklist-Mixed: the compact sheet (720×560: openOnboarding() from Settings, a later run)
 *   ready      Onb-Setup-Ready: every row green, whatever view it opened with
 *
 * Live, never prompting: permissions are watched only while this window is focused (main polls only then), health is
 * asked for on open and every HEALTH_MS while focused, and only when the engine said it understands health.get.
 * The window is done once every row is green (onboarding.json in userData).
 */
import { useEffect, useMemo, type ReactNode } from 'react'
import type { Layout } from '../../../../preload/api'
import { isElectron } from '../../bridge'
import { useLesson } from '../../core/lesson'
import { useWindowArgs } from '../../core/surfaces'
import { color, font } from '../../core/theme'
import { Checklist } from './Checklist'
import { Ready } from './Ready'
import { summarize, useRows } from './rows'
import { SetupList } from './SetupList'
import { markDone, refreshCloud, refreshPerms, requestHealth, useOnboarding, watchPerms, type OnbView } from './store'
import { Welcome, WELCOME_W } from './Welcome'

const HEALTH_MS = 4000
/** Below this the two panes don't fit (the window is resizable): the checklist instead. */
const TWO_PANE_MIN = WELCOME_W + 528

function useLive(): void {
  const hello = useLesson((s) => !!s.hello)
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined
    const focus = (): void => {
      watchPerms('window', true)
      requestHealth()
      refreshCloud()
      clearInterval(timer)
      timer = setInterval(requestHealth, HEALTH_MS)
    }
    const blur = (): void => {
      // The stage is one page: it never "leaves" the window.
      if (!isElectron) return
      watchPerms('window', false)
      clearInterval(timer)
      timer = undefined
    }
    void refreshPerms()
    if (!isElectron || document.hasFocus()) focus()
    window.addEventListener('focus', focus)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('focus', focus)
      window.removeEventListener('blur', blur)
      clearInterval(timer)
      watchPerms('window', false)
    }
  }, [hello])
}

export function Onboarding({ layout }: { layout: Layout }): ReactNode {
  useLive()
  const args = useWindowArgs('onboarding')
  const done = useOnboarding((s) => s.done)
  const rows = useRows()
  const sum = useMemo(() => summarize(rows), [rows])
  const asked: OnbView | undefined = args?.view === 'welcome' || args?.view === 'checklist' ? args.view : undefined
  const view = sum.allOk ? 'ready' : (asked ?? (done ? 'checklist' : 'welcome')) === 'welcome' && layout.width >= TWO_PANE_MIN ? 'welcome' : 'checklist'

  useEffect(() => {
    if (sum.allOk) markDone()
  }, [sum.allOk])

  return (
    <div data-onb-window className="flex h-full w-full select-none overflow-hidden" style={{ background: color.window, color: color.text, fontFamily: font.ui }}>
      {view === 'ready' ? (
        <Ready rows={rows} sum={sum} />
      ) : view === 'welcome' ? (
        <div data-onb-view="welcome" role="dialog" aria-labelledby="onb-title" className="flex h-full w-full">
          <Welcome />
          <SetupList rows={rows} sum={sum} />
        </div>
      ) : (
        <Checklist rows={rows} sum={sum} />
      )}
    </div>
  )
}
