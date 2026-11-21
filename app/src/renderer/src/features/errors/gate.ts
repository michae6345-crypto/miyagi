/**
 * Feature: errors. The lesson panel's link gate: what the panel may offer while miyagi can't answer, so the pill, the
 * cards and the panel never contradict each other (persona QA, round 3).
 *
 *   ok       the link is up: Check my work and the help tiles as usual
 *   wait     reconnecting, offline or busy: checks and help wait. Check my work turns into "Check when miyagi is back";
 *            pressed, it is queued and runs by itself the moment the link is ok again
 *   paused   a blocking card owns the screen (miyagi stopped responding, VS Code closed, a permission went away): the
 *            panel dims and goes inert, its primary disabled, so the card's action is the only primary on screen
 *
 * The panel (features/drawer/v2) reads useLinkGate(); the queue lives here so it survives the panel collapsing.
 */
import { create } from 'zustand'
import { notify, useLesson } from '../../core/lesson'
import { sendAction } from '../../core/shortcuts'
import { useOnboarding } from '../onboarding/store'
import { reconnectTry, TRIES, useErrors } from './store'

export type GateKind = 'ok' | 'wait' | 'paused'
export type Gate = {
  kind: GateKind
  /** Why, in one line under the primary ("Checks wait until miyagi is back"). */
  caption?: string
  /** The primary's label while waiting. */
  label?: string
  /** The "Need help" caption while help waits ("Help waits until you are back online"). */
  help?: string
  /** The caption under the queued Check, said once (the button already reads "Queued"). */
  queued?: string
  /** The Watch tile needs the network too. */
  offline?: boolean
}

const OK: Gate = { kind: 'ok' }

type Snap = {
  linkDown: boolean
  stopped: boolean
  offline: boolean
  busy: boolean
  editorClosed: boolean
  recovery: boolean
}

function gateOf(s: Snap): Gate {
  if (s.stopped) return { kind: 'paused', caption: 'Paused until miyagi restarts', help: 'Help waits until miyagi restarts' }
  if (s.recovery) return { kind: 'paused', caption: 'Paused until the permission is back on', help: 'Help waits until the permission is back on' }
  if (s.editorClosed) return { kind: 'paused', caption: 'Paused until VS Code is back', help: 'Help waits until VS Code is back' }
  if (s.linkDown) {
    return {
      kind: 'wait',
      label: 'Check when miyagi is back',
      caption: 'Reconnecting. Checks and help wait.',
      help: 'Help waits until miyagi is back',
      queued: 'Runs when miyagi is back'
    }
  }
  if (s.offline) {
    return {
      kind: 'wait',
      label: 'Check when back online',
      caption: 'Offline. Checks and help wait.',
      help: 'Help waits until you are back online',
      queued: 'Runs when you are back online',
      offline: true
    }
  }
  if (s.busy) {
    return {
      kind: 'wait',
      label: 'Check when miyagi is free',
      caption: 'miyagi is busy. Checks wait a moment.',
      help: 'Help waits a moment',
      queued: 'Runs when miyagi is free'
    }
  }
  return OK
}

/** The gate as a hook (React). One object per kind and caption, so a re-render only happens when it changes. */
export function useLinkGate(): Gate {
  const stopped = useErrors((s) => {
    const l = s.link
    return s.everOpen && !!l && !l.open && l.failures >= TRIES
  })
  const linkDown = useErrors((s) => reconnectTry(s) !== undefined)
  const offlineMac = useErrors((s) => !s.online)
  const offlineEngine = useLesson((s) => !!s.blockers.network)
  const busy = useLesson((s) => !!s.busy)
  const editorClosed = useLesson((s) => !!s.blockers.editor_closed || s.paused?.reason === 'editor_closed')
  const recovery = useOnboarding((s) => !!s.recovery)
  return gateOf({ stopped, linkDown, offline: offlineMac || offlineEngine, busy, editorClosed, recovery })
}

/** The same gate outside React. */
function gateNow(): Gate {
  const e = useErrors.getState()
  const l = useLesson.getState()
  const link = e.link
  return gateOf({
    stopped: e.everOpen && !!link && !link.open && link.failures >= TRIES,
    linkDown: reconnectTry(e) !== undefined,
    offline: !e.online || !!l.blockers.network,
    busy: !!l.busy,
    editorClosed: !!l.blockers.editor_closed || l.paused?.reason === 'editor_closed',
    recovery: !!useOnboarding.getState().recovery
  })
}

// ---- the queued check ---------------------------------------------------------------------------------------------

/** A Check pressed while waiting: the step it was pressed on. */
export const useQueuedCheck = create<{ stepId?: string }>(() => ({}))

/** Check my work while the gate waits: queue it (once), say so on the pill. */
export function queueCheck(): void {
  const stepId = useLesson.getState().stepId
  if (!stepId) return
  if (useQueuedCheck.getState().stepId === stepId) return
  useQueuedCheck.setState({ stepId })
  // One string for the queued state: the panel's caption and this pill line both come from the gate.
  notify(`Check queued. ${gateNow().queued ?? 'Runs when miyagi is back'}.`, 'info', { id: 'err-queued-check' })
}

function settleQueue(): void {
  const q = useQueuedCheck.getState().stepId
  if (!q) return
  const s = useLesson.getState()
  // The step moved on (or the lesson ended): the queued check is for a step that is gone.
  if (s.stepId !== q) return useQueuedCheck.setState({ stepId: undefined })
  if (gateNow().kind !== 'ok' || !s.connected) return
  useQueuedCheck.setState({ stepId: undefined })
  sendAction('check_step')
}
useErrors.subscribe(settleQueue)
useLesson.subscribe(settleQueue)
useOnboarding.subscribe(settleQueue)
