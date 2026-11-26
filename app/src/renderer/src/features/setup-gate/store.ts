/**
 * Feature: setup-gate. The engine's setup.gate (server/orchestrator/setup_gate.py) folded through machine.ts.
 * Every window keeps its own copy (engine messages reach them all): the overlay draws the panel, the player window holds
 * the video while it `holds` (features/player/store.ts).
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
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
  dispatch({ type: 'press', what: a.kind === 'skip' ? `skip:${a.tool}` : a.kind })
  sendAction(act.kind, act.text)
}

onMessage('setup.gate', (p) => dispatch({ type: 'gate', payload: p, now: Date.now() }))
// A new lesson or the end of this one: the old gate is gone (the engine keeps one per lesson).
onMessage('lesson.ready', (p) => {
  if (p.replay !== true) dispatch({ type: 'reset' })
})
onMessage('lesson.ended', () => dispatch({ type: 'reset' }))
onUi('reset', () => dispatch({ type: 'reset' }))
