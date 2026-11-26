/**
 * Feature: library. Home v4's link to the ui-v4 contract (shared/contracts/UI-V4.md): `activity.get` and `plans.list`,
 * each sent only when engine.hello lists it (core/lesson canSend), and the `activity` / `plans` answers and pushes kept
 * here for the page (home/data.ts fromContract maps them).
 */
import { useEffect } from 'react'
import { create } from 'zustand'
import type { Activity, PlanState } from '../../../../../../../shared/contracts/events'
import { cmd } from '../../../../../common/wire'
import { bridge } from '../../../bridge'
import { onMessage } from '../../../core/bus'
import { canSend, useCapability } from '../../../core/lesson'

export const useV4 = create<{ activity?: Activity; plans?: PlanState[] }>(() => ({}))

onMessage('activity', (p) => useV4.setState({ activity: p }))
onMessage('plans', (p) => useV4.setState({ plans: Array.isArray(p?.items) ? p.items : [] }))

/** Asks for the week and the plans when Home opens, and again once the engine's hello lists them. */
export function useAskV4(): void {
  const activity = useCapability('activity.get')
  const plans = useCapability('plans.list')
  useEffect(() => {
    if (activity && canSend('activity.get')) bridge.send(cmd('activity.get', {}))
  }, [activity])
  useEffect(() => {
    if (plans && canSend('plans.list')) bridge.send(cmd('plans.list', {}))
  }, [plans])
}
