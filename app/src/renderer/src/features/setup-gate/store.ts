/**
 * Feature: setup-gate. The engine's setup.gate (server/orchestrator/setup_gate.py) folded through machine.ts.
 * Every window keeps its own copy (engine messages reach them all): the overlay draws the panel, the player window holds
 * the video while it `holds` (features/player/store.ts).
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { sendAction } from '../../core/shortcuts'
import { actionFor, holds, initial, reduce, type GateAction, type GateEvent, type GateState } from './machine'

export const useSetupGate = create<GateState & { holds: boolean }>(() => ({ ...initial, holds: false }))

export function dispatch(e: GateEvent): void {
  const next = reduce(useSetupGate.getState(), e)
  useSetupGate.setState({ ...next, holds: holds(next) }, true)
}

/** A button on the panel. Show details is local; the rest go to the engine (action setup_*). */
export function press(a: GateAction): void {
  if (a.kind === 'details') return dispatch({ type: 'toggleLog' })
  const act = actionFor(a)
  if (!act) return
  dispatch({ type: 'press', what: a.kind === 'skip' ? `skip:${a.tool}` : a.kind === 'continue_without' ? 'continue' : a.kind })
  sendAction(act.kind, act.text)
}

onMessage('setup.gate', (p) => dispatch({ type: 'gate', payload: p, now: Date.now() }))
// A new lesson, a replay of this one (an engine restart mid-install), or its end: the old gate goes. The engine sends
// setup.gate right after every lesson.ready (replays too) and on every connect, so a live gate comes straight back.
onMessage('lesson.ready', () => dispatch({ type: 'reset' }))
onMessage('lesson.ended', () => dispatch({ type: 'reset' }))
onUi('reset', () => dispatch({ type: 'reset' }))
// The engine went away: nothing is installing for us any more until it says so again (never a stuck "Installing…").
useLesson.subscribe((s, prev) => {
  if (prev.connected && !s.connected) dispatch({ type: 'reset' })
})
