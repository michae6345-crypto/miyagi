/**
 * v2 (A2): the Mini pill's way back into the lesson panel (Les-Mini: "Click to open").
 *
 * The panel is A1's (features/drawer). Ask it the core way first (the `panel` UI event, core/bus.ts: "the Mini pill
 * (A2) ... asks through this"); if nothing claims it, A1's `openPanel` export (`useDrawer.openPanel` in the plan) when
 * it's there; with no panel at all, just leave the Mini state so the step pill shows again.
 *
 * Stage only: `?pc=mini` collapses the (stand-in) panel to the Mini pill once a step starts, `?pc=panel` marks it open,
 * so the pill-cards scenario can show Les-Mini and the panel-routed cards without A1. A1's own `?panel=` wins when
 * it sets the dock itself.
 */
import { isElectron } from '../../bridge'
import { emitUi, onMessage } from '../../core/bus'
import { setDock, useDock } from '../../core/dock'
import { drawerExport } from '../cards/panel'

export function openPanel(): void {
  if (emitUi('panel', 'open')) return
  const fn = drawerExport('openPanel')
  if (fn) {
    try {
      fn()
      return
    } catch {
      // A1's opener failed: fall through to the plain dock state.
    }
  }
  setDock({ collapsed: false })
}

/** The panel is in play (shown or collapsed to the Mini pill): the lesson panel, not the video, paces the steps. */
export const panelInPlay = (): boolean => {
  const d = useDock.getState()
  return d.open || d.collapsed
}

const stageParam = !isElectron ? new URLSearchParams(location.search).get('pc') : null
if (stageParam === 'mini' || stageParam === 'panel') {
  onMessage('step.started', () => {
    const d = useDock.getState()
    if (d.open || d.collapsed) return // A1 (or the learner) already decided
    setDock(stageParam === 'mini' ? { open: false, collapsed: true } : { open: true, collapsed: false })
  })
}
