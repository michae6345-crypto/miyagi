/**
 * Feature: agegate. The record main keeps (main/features/agegate.ts), mirrored for the screens. Never the birth date:
 * the pickers' values live only in AgeStep's component state and are dropped when it unmounts.
 *
 *   loadAge()     agegate:get once per window (and again after Delete account: feat:agegate)
 *   saveAge(r)    agegate:set with the RESULT only ({band} or {blockedUntil}); main merges (a block in force wins)
 */
import { create } from 'zustand'
import { bridge } from '../../bridge'
import { cleanRecord, type AgeRecord } from './age'
import './web'

type State = { record: AgeRecord | null; loaded: boolean }

export const useAge = create<State>(() => ({ record: null, loaded: false }))

/** main's answer can't be waited on forever: after this the step shows (the safe side). */
const LOAD_WAIT_MS = 1200

let loading: Promise<void> | undefined
export function loadAge(): Promise<void> {
  if (loading) return loading
  const fallback = setTimeout(() => useAge.setState({ loaded: true }), LOAD_WAIT_MS)
  loading = bridge
    .invoke<unknown>('agegate:get')
    .then((r) => useAge.setState({ record: cleanRecord(r) ?? null, loaded: true }))
    .catch(() => useAge.setState({ loaded: true }))
    .finally(() => clearTimeout(fallback))
  return loading
}

/** → the record main now holds (a block in force stays, whatever was sent). */
export async function saveAge(next: AgeRecord): Promise<AgeRecord | null> {
  const r = await bridge.invoke<unknown>('agegate:set', next).catch(() => undefined)
  const record = cleanRecord(r) ?? null
  useAge.setState({ record, loaded: true })
  return record
}

bridge.onFeature('agegate', (r) => useAge.setState({ record: cleanRecord(r) ?? null, loaded: true }))
