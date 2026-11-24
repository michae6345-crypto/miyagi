/**
 * Feature: progress, v4 page state. Fed by the UI-V4 contract's messages (shared/contracts/UI-V4.md): `activity`
 * (week, 12 weeks, totals, recently passed), `bon` (the rail's buddy) and `plans` (the rail's Plans), plus the parts
 * of the engine's `progress` answer the contract does not carry yet (goal, review minutes, steps to master: model.ts
 * readV4). The dashboard store keeps its own reading of `progress` (tracks, completed, review).
 *
 * requestV4() asks for all three when the page opens, each only when engine.hello lists it (canSend). The engine
 * then pushes each one when it changes.
 */
import { create } from 'zustand'
import { cmd } from '../../../../../common/wire'
import { bridge } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { canSend } from '../../../core/lesson'
import { stageRebase } from '../../dashboard/stage'
import { EMPTY_V4, readActivity, readBon, readPlans, readV4, type V4 } from './model'

export const useV4 = create<{ v4: V4; seen: boolean }>(() => ({
  v4: EMPTY_V4,
  seen: false
}))

const merge = (part: Partial<V4>): void => useV4.setState((s) => ({ v4: { ...s.v4, ...part }, seen: true }))

onMessage('progress', (raw) => merge(readV4(stageRebase(raw))))
onMessage('activity', (raw) => merge(readActivity(raw)))
onMessage('bon', (raw) => {
  const bon = readBon(raw)
  if (bon) merge({ bon })
})
onMessage('plans', (raw) => merge({ plans: readPlans(raw) }))

/** Ask the engine for this page's ui-v4 data (Progress opened, or the engine reconnected). */
export function requestV4(): void {
  if (canSend('activity.get')) bridge.send(cmd('activity.get', {}))
  if (canSend('bon.get')) bridge.send(cmd('bon.get', {}))
  if (canSend('plans.list')) bridge.send(cmd('plans.list', {}))
}

/** The engine can send `activity`: wait for it rather than show an empty week. */
export const activityExpected = (): boolean => canSend('activity.get')
