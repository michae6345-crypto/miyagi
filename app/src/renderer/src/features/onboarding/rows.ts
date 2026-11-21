/**
 * Feature: onboarding (A3). The setup rows, derived from what the app and the engine know. Pure: no reads, no sends.
 *
 *   Screen Recording   main/permissions.ts (screen)
 *   Accessibility      main/permissions.ts (accessibility)
 *   VS Code companion  the engine's health (companion, vscode). Hidden when the engine reports no companion probe.
 *   miyagi engine      the link (connected), main/localEngine.ts, and the cloud install token (DISTRIBUTION-PLAN 4):
 *                      cloud:get's phase and config.status.cloud. Paused, over quota and offline are plain text.
 *
 * States map onto the shared status glyphs (core/ui/status.tsx): passed is the only green; notyet is the white ring;
 * watching is the gray dashed ring (miyagi waits for the learner's switch); unknown is gray too and never blocks the
 * start (an engine started in Terminal: macOS grants belong to that Terminal, so the app can't tell).
 * Copy: short, calm, no em dashes. Editor labels go through copy.editorName (never an unsupported editor's name).
 */
import { useShallow } from 'zustand/react/shallow'
import type { HealthItem } from '../../../../../../shared/contracts/events'
import { useLesson } from '../../core/lesson'
import { copy } from '../../core/theme'
import type { StatusState } from '../../core/ui/status'
import { useOnboarding, type Asked, type CloudView, type Permissions, type RowAction } from './store'

export type RowId = 'screen' | 'accessibility' | 'companion' | 'engine'
export type RowState = Extract<StatusState, 'passed' | 'notyet' | 'watching' | 'checking' | 'unknown'>

export type Row = {
  id: RowId
  label: string
  /** Why miyagi needs it (Onb-Setup-Full's second line). */
  why: string
  state: RowState
  /** The word on the right: On, Running, Connected, Watching, Not yet... */
  word: string
  /** The checklist's second line (Onb-Checklist-Mixed): the state in a sentence. */
  detail: string
  action?: { id: RowAction; label: string; item?: HealthItem }
  /** A second, quieter button beside the action (the engine's "Copy details"). */
  alt?: { id: RowAction; label: string }
}

/** main/localEngine.ts ENGINE_FAILED_LINE: the one line for an engine that didn't come up. */
export const ENGINE_FAILED = "miyagi couldn't start its engine."

export type RowInput = {
  perms?: Permissions
  health?: { items: HealthItem[] }
  asked: Asked
  installing: boolean
  connected: boolean
  localEngine?: { state: string }
  cloud?: CloudView
  cloudStatus?: string
}

const UNKNOWN_DETAIL = (external: boolean): string => (external ? "Can't check this while the engine runs in Terminal." : "miyagi can't check this from here.")

function screenRow(i: RowInput): Row {
  const base = { id: 'screen' as const, label: 'Screen Recording', why: 'So miyagi can see where you are.' }
  const s = i.perms?.screen
  if (s === 'granted') return { ...base, state: 'passed', word: 'On', detail: base.why }
  if (!i.perms || s === 'unknown') return { ...base, state: 'unknown', word: 'Not sure yet', detail: UNKNOWN_DETAIL(!!i.perms?.external) }
  // macOS often applies this grant only after a relaunch.
  if (i.asked.screen) return { ...base, state: 'watching', word: 'Watching', detail: 'Switch miyagi on, then relaunch it.', action: { id: 'relaunch', label: 'Relaunch' } }
  return { ...base, state: 'notyet', word: 'Not yet', detail: 'Not yet. Allow it, then switch miyagi on.', action: { id: 'allow-screen', label: 'Allow' } }
}

function accessibilityRow(i: RowInput): Row {
  const base = { id: 'accessibility' as const, label: 'Accessibility', why: 'So miyagi can point at real buttons.' }
  const s = i.perms?.accessibility
  if (s === 'granted') return { ...base, state: 'passed', word: 'On', detail: base.why }
  if (!i.perms || s === 'unknown') return { ...base, state: 'unknown', word: 'Not sure yet', detail: UNKNOWN_DETAIL(!!i.perms?.external) }
  const action = { id: 'open-accessibility' as const, label: 'Open System Settings' }
  if (i.asked.accessibility) return { ...base, state: 'watching', word: 'Watching', detail: 'Watching. Switch miyagi on, then come back.', action }
  return { ...base, state: 'notyet', word: 'Not yet', detail: 'Not yet. Switch miyagi on in System Settings.', action }
}

/** undefined = the engine has no companion probe: the row is hidden (BUILD-PLAN A3). */
function companionRow(i: RowInput): Row | undefined {
  const comp = i.health?.items.find((x) => x.id === 'companion')
  if (!comp) return undefined
  // VS Code is the one editor miyagi supports (copy.editorName with no label is "VS Code").
  const base = { id: 'companion' as const, label: `${copy.editorName()} companion`, why: 'Lets miyagi run and check your code.' }
  const vscode = i.health?.items.find((x) => x.id === 'vscode')
  if (comp.state === 'ok') return { ...base, state: 'passed', word: 'Connected', detail: 'Connected to VS Code.' }
  if (i.installing) return { ...base, state: 'checking', word: 'Installing', detail: 'Installing in VS Code.' }
  if (comp.state === 'checking') return { ...base, state: 'checking', word: 'Checking', detail: 'Checking VS Code.' }
  if (comp.state === 'unknown') return { ...base, state: 'unknown', word: 'Not sure yet', detail: "miyagi can't check this yet." }
  if (vscode && (vscode.state === 'missing' || vscode.state === 'off'))
    return { ...base, state: i.asked.companion ? 'watching' : 'notyet', word: i.asked.companion ? 'Watching' : 'Not yet', detail: "VS Code isn't on this Mac yet.", action: { id: 'get-vscode', label: 'Get VS Code' } }
  const action = { id: 'install-companion' as const, label: 'Install in VS Code', item: comp }
  if (i.asked.companion) return { ...base, state: 'watching', word: 'Watching', detail: 'Watching for VS Code to connect.', action }
  return { ...base, state: 'notyet', word: 'Not yet', detail: 'Not yet. One click, VS Code opens.', action }
}

/** The engine, with the cloud install token folded in (the first-run token step lives in this row). */
function engineRow(i: RowInput): Row {
  const base = { id: 'engine' as const, label: 'miyagi engine', why: 'Builds and checks your lessons.' }
  const local = i.localEngine?.state
  if (!i.connected) {
    if (local === 'checking' || local === 'installing' || local === 'starting') return { ...base, state: 'watching', word: 'Starting', detail: 'Starting on this Mac.' }
    // Never "Connecting" forever: main says failed (with its reason in engine.log) once the engine can't come up.
    if (local === 'failed' || local === 'missing')
      return { ...base, state: 'notyet', word: "Couldn't start", detail: ENGINE_FAILED, action: { id: 'retry-engine', label: 'Retry' }, alt: { id: 'copy-engine-details', label: 'Copy details' } }
    if (local === 'external') return { ...base, state: 'notyet', word: 'Not yet', detail: 'Start the engine in Terminal.' }
    return { ...base, state: 'watching', word: 'Connecting', detail: 'Looking for the engine.' }
  }
  const cloud = i.cloud?.state
  if (cloud === 'minting') return { ...base, state: 'checking', word: 'Setting up', detail: 'Setting up access for this Mac.' }
  if (cloud === 'failed') return { ...base, state: 'notyet', word: 'Not yet', detail: "Couldn't set up access. Check your connection.", action: { id: 'retry-cloud', label: 'Try again' } }
  if (cloud === 'ok' || i.cloudStatus) {
    switch (i.cloudStatus) {
      case 'paused':
        return { ...base, state: 'notyet', word: 'Paused', detail: 'miyagi is paused for now. Try again later.' }
      case 'quota':
        return { ...base, state: 'notyet', word: 'Not yet', detail: "Today's free use is used up. Back tomorrow." }
      case 'unauthorized':
        return { ...base, state: 'notyet', word: 'Not yet', detail: "This Mac's access was turned off." }
      case 'offline':
        return { ...base, state: 'notyet', word: 'Offline', detail: "Can't reach miyagi. Check your connection." }
    }
  }
  return { ...base, state: 'passed', word: 'Running', detail: local === 'external' ? 'Running in Terminal.' : 'Running on this Mac.' }
}

export function deriveRows(i: RowInput): Row[] {
  const comp = companionRow(i)
  return [screenRow(i), accessibilityRow(i), ...(comp ? [comp] : []), engineRow(i)]
}

export type Summary = {
  ready: number
  total: number
  /** Every row is green: the Ready view. */
  allOk: boolean
  /** Nothing left the learner can do (unknown rows don't block): Start learning is on. */
  canStart: boolean
  /** The footer line under the rows. */
  hint: string
}

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five']
const SHORT: Record<RowId, string> = { screen: 'Screen Recording', accessibility: 'Accessibility', companion: 'VS Code', engine: 'the engine' }

export function summarize(rows: Row[]): Summary {
  const ready = rows.filter((r) => r.state === 'passed').length
  const left = rows.filter((r) => r.state !== 'passed' && r.state !== 'unknown')
  const unknown = rows.some((r) => r.state === 'unknown')
  const hint =
    left.length === 0
      ? unknown
        ? "miyagi can't check everything from here. You can start."
        : 'All set.'
      : left.length <= 2
        ? `Turn on ${left.map((r) => SHORT[r.id]).join(' and ')} to start.`
        : `${WORDS[left.length] ?? left.length} more, then you can start.`
  return { ready, total: rows.length, allOk: rows.length > 0 && ready === rows.length, canStart: left.length === 0, hint }
}

/** The rows, live. */
export function useRows(): Row[] {
  const o = useOnboarding(useShallow((s) => ({ perms: s.perms, health: s.health, asked: s.asked, installing: s.installing, cloud: s.cloud, watching: s.recovery?.kind })))
  const l = useLesson(useShallow((s) => ({ connected: s.connected, localEngine: s.localEngine, cloudStatus: s.keyStatus?.cloud })))
  const { watching, ...rest } = o
  // An open recovery card watches its grant (Onb-Permission-Recovery: that row reads Watching).
  const asked = watching && !rest.asked[watching] ? { ...rest.asked, [watching]: 1 } : rest.asked
  return deriveRows({ ...rest, ...l, asked })
}
