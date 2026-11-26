/**
 * Feature: onboarding. The macOS permissions step on its own, for any first-launch order (welcome → sign in →
 * permissions → tour; the tour lane calls this instead of reaching into the walk). One source: main/permissions.ts
 * through the onboarding store (feat:permissions reaches every window, so a grant clears every banner at once).
 *
 *   usePermissionsStep()    live while mounted (watches permissions while the window is on screen, reads again on
 *                           focus): the two grant rows, where they stand, and the actions. Never prompts by itself.
 *   permissionsDone(p)      pure: both grants read granted (Windows: always; an engine in Terminal: unknown counts
 *                           as done, it never traps the learner).
 *   <PermissionsStep>       the guided Screen Recording and Accessibility screens (Guided.tsx, flow chrome), with
 *                           the live refresh, Restart miyagi when only a restart applies a grant, and onDone once both
 *                           are on (or the learner moved past them). Nothing else of setup.
 */
import { useEffect, useMemo, type ReactNode } from 'react'
import { Guided } from './Guided'
import { useLive } from './Onboarding'
import { useRows, type Row } from './rows'
import { runAction, type Permissions } from './store'

export type GrantKind = 'screen' | 'accessibility'
export type GrantState = 'on' | 'off' | 'restart' | 'unknown'

const GRANTS: readonly GrantKind[] = ['screen', 'accessibility']

/** Both grants on (or not something the learner can fix from here). Pure. */
export function permissionsDone(p: Permissions | undefined): boolean {
  if (!p) return false
  return GRANTS.every((k) => p[k] === 'granted' || p[k] === 'unknown')
}

/** Where one grant stands, from its setup row (rows.ts). */
export function grantState(row: Row | undefined): GrantState {
  if (!row || row.state === 'passed') return 'on'
  if (row.restart) return 'restart'
  if (row.state === 'unknown') return 'unknown'
  return 'off'
}

export type PermissionsStepState = {
  /** The grant rows (none on Windows: nothing to grant there). */
  rows: Row[]
  states: Record<GrantKind, GrantState>
  /** Nothing left to grant (restart rows count as left). */
  done: boolean
  /** Something is on in System Settings and needs a restart. */
  restartNeeded: boolean
  /** The row's own fix: the macOS prompt and the pane the first time, only the pane for a grant that is on already. */
  allow(kind: GrantKind): Promise<void>
  /** Quit and reopen miyagi (the engine too): how macOS applies Screen Recording. */
  restart(): Promise<void>
}

export function usePermissionsStep(): PermissionsStepState {
  useLive()
  const all = useRows()
  return useMemo(() => {
    const rows = all.filter((r) => (GRANTS as readonly string[]).includes(r.id))
    const states = { screen: grantState(rows.find((r) => r.id === 'screen')), accessibility: grantState(rows.find((r) => r.id === 'accessibility')) }
    return {
      rows,
      states,
      done: GRANTS.every((k) => states[k] === 'on' || states[k] === 'unknown'),
      restartNeeded: GRANTS.some((k) => states[k] === 'restart'),
      allow: (kind) => runAction(kind === 'screen' ? 'allow-screen' : 'open-accessibility'),
      restart: () => runAction('relaunch')
    }
  }, [all])
}

/** The two grant screens on their own (flow chrome: the host draws the header). `onDone` once both are through. */
export function PermissionsStep({ width, height, onDone, enterDelay }: { width: number; height: number; onDone: () => void; enterDelay?: number }): ReactNode {
  const { rows } = usePermissionsStep()
  const none = rows.length === 0
  // Windows: nothing to grant. Hand straight back (once).
  useEffect(() => {
    if (none) onDone()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [none])
  if (none) return null
  return <Guided rows={rows} width={width} height={height} chrome="flow" enterDelay={enterDelay} onFinish={onDone} />
}
