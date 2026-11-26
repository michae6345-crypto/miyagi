/**
 * Feature: settings. What the Permissions and General sections read, without ever prompting (Section 6).
 *
 *   usePermissions(live)   main/permissions.ts: `permissions:get` once, then `permissions:watch` while the section is on
 *                          show (main polls only while someone watches) and `feat:permissions` updates. Turn on calls
 *                          `permissions:open(kind)`: System Settings at that switch, a fixed URL in main. No prompt.
 *                          A grant main sees only after a restart (`relaunch`) offers Restart miyagi instead.
 *   useHealth(live)        the engine's `health` rows (companion, VS Code, Jupyter). Asks with `health.get` only when
 *                          engine.hello lists it; an older engine never answers and the rows that need it stay hidden.
 */
import { useEffect, useState } from 'react'
import { create } from 'zustand'
import type { HealthItem, PermissionKind } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage } from '../../core/bus'
import { canSend, useLesson } from '../../core/lesson'

export type PermissionState = 'granted' | 'denied' | 'not-determined' | 'unknown'
/** `relaunch`: switched on in System Settings, seen only after miyagi restarts (main/permissions.ts). */
export type Permissions = Record<PermissionKind, PermissionState> & { external: boolean; relaunch?: Array<'screen' | 'accessibility'> }

const STATES: readonly PermissionState[] = ['granted', 'denied', 'not-determined', 'unknown']
const KINDS: readonly PermissionKind[] = ['screen', 'accessibility', 'automation']

/** IPC input: anything unexpected reads as unknown (gray), never as granted. */
function clean(raw: unknown): Permissions | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const r = raw as Record<string, unknown>
  const out = { external: r.external === true } as Permissions
  for (const k of KINDS) out[k] = STATES.includes(r[k] as PermissionState) ? (r[k] as PermissionState) : 'unknown'
  if (Array.isArray(r.relaunch)) {
    const kinds = r.relaunch.filter((k): k is 'screen' | 'accessibility' => k === 'screen' || k === 'accessibility')
    if (kinds.length) out.relaunch = kinds
  }
  return out
}

export function usePermissions(live: boolean): Permissions | undefined {
  const [perms, setPerms] = useState<Permissions>()
  useEffect(() => {
    if (!live) return
    let on = true
    bridge
      .invoke('permissions:get')
      .then((p) => on && setPerms(clean(p)))
      .catch(() => {})
    bridge.invoke('permissions:watch', true).catch(() => {})
    const off = bridge.onFeature('permissions', (p) => {
      const c = clean(p)
      if (c) setPerms(c)
    })
    return () => {
      on = false
      off()
      bridge.invoke('permissions:watch', false).catch(() => {})
    }
  }, [live])
  return perms
}

/** Quit and reopen miyagi (onboarding:relaunch; a dev copy can't, and says so in its log). */
export function relaunchApp(): void {
  bridge.invoke('onboarding:relaunch').catch(() => {})
}

/** System Settings at that switch. Never a URL from here: main maps the kind to its fixed pane. */
export function openPermission(kind: PermissionKind): void {
  bridge.invoke('permissions:open', kind).catch(() => {})
}

// ---- health ----------------------------------------------------------------------------------------

const useHealthStore = create<{ items?: HealthItem[] }>(() => ({}))

onMessage('health', (p) => useHealthStore.setState({ items: Array.isArray(p?.items) ? p.items : undefined }))

export function useHealth(live: boolean): Record<string, HealthItem | undefined> {
  const items = useHealthStore((s) => s.items)
  const capable = useLesson((s) => !!s.hello?.capabilities.includes('health.get'))
  useEffect(() => {
    if (live && capable && canSend('health.get')) bridge.send(cmd('health.get', {}))
  }, [live, capable])
  const byId: Record<string, HealthItem | undefined> = {}
  for (const i of items ?? []) if (i && typeof i.id === 'string') byId[i.id] = i
  return byId
}
