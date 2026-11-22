/**
 * Feature: onboarding. The guided setup's four steps, one per screen, from the same live rows the checklist uses
 * (rows.ts). Pure: no reads, no sends.
 *
 *   1 screen         Screen Recording   (Allow, then the System Settings pane; Relaunch after the click)
 *   2 accessibility  Accessibility      (Open System Settings)
 *   3 companion      VS Code companion  (Install in VS Code; Get VS Code or Skip when VS Code isn't on this Mac)
 *   4 engine         engine + cloud     (nothing to click: it advances on its own once it is green)
 *
 * The step list never changes length on one computer (stable steps): when the engine has no companion probe yet the
 * companion step reads Checking, and Not sure yet (with Continue) when this engine can't tell at all.
 * Windows (device.ts): Screen Recording and Accessibility are macOS grants, so a PC walks two steps, VS Code then the
 * engine. Same screens, same order, same copy otherwise.
 * Copy: short, calm, no em dashes, the brand lowercase. VS Code is the one editor miyagi names.
 */
import { Code, Monitor, MousePointer2, Settings2, type LucideIcon } from 'lucide-react'
import { needsGrants, osNow, type Os } from './device'
import type { Row, RowId } from './rows'

export type StepId = RowId
export const STEP_ORDER: readonly StepId[] = ['screen', 'accessibility', 'companion', 'engine']

/** The steps this computer walks: all four on a Mac, VS Code and the engine on Windows. */
export function stepOrder(os: Os = osNow()): readonly StepId[] {
  return needsGrants(os) ? STEP_ORDER : STEP_ORDER.filter((id) => id !== 'screen' && id !== 'accessibility')
}

export type StepCopy = { title: string; body: string; icon: LucideIcon; short: string }

export const STEP_COPY: Record<StepId, StepCopy> = {
  screen: { title: 'Let miyagi see your screen', body: 'So it knows which step you are on and where to point.', icon: Monitor, short: 'Screen Recording' },
  accessibility: { title: 'Let miyagi point at buttons', body: 'So it can point at the real buttons in your apps.', icon: MousePointer2, short: 'Accessibility' },
  companion: { title: 'Connect VS Code', body: 'A small extension that runs your code and checks it.', icon: Code, short: 'VS Code' },
  engine: { title: 'Getting miyagi ready', body: 'The engine builds your lessons and checks your work.', icon: Settings2, short: 'Engine' }
}

/** The companion step when the engine hasn't said anything about it (yet, or ever). */
export function companionPlaceholder(canAsk: boolean): Row {
  return canAsk
    ? { id: 'companion', label: 'VS Code companion', why: STEP_COPY.companion.body, state: 'checking', word: 'Checking', detail: 'Looking for VS Code.' }
    : { id: 'companion', label: 'VS Code companion', why: STEP_COPY.companion.body, state: 'unknown', word: 'Not sure yet', detail: "miyagi can't check this from here." }
}

/** This computer's steps in order: the live row for each, the placeholder for a companion the engine hasn't reported. */
export function guidedRows(rows: Row[], canAskHealth: boolean, os: Os = osNow()): Row[] {
  return stepOrder(os).map((id) => rows.find((r) => r.id === id) ?? companionPlaceholder(canAskHealth))
}

/** Done for the walk: green, or skipped by the learner (the companion only). */
export function isDone(row: Row, skipped: ReadonlySet<StepId>): boolean {
  return row.state === 'passed' || skipped.has(row.id)
}

/** Where a walk starts: the first step not done; undefined = every step is done (straight to You're ready). */
export function firstOpen(rows: Row[], skipped: ReadonlySet<StepId>): number | undefined {
  const i = rows.findIndex((r) => !isDone(r, skipped))
  return i < 0 ? undefined : i
}

/** After step `from` turns green: the next step not done, wrapping to an earlier one left open; undefined = finished. */
export function nextOpen(rows: Row[], from: number, skipped: ReadonlySet<StepId>): number | undefined {
  for (let k = 1; k < rows.length; k++) {
    const i = (from + k) % rows.length
    if (!isDone(rows[i], skipped)) return i
  }
  return undefined
}

/** The status line under the copy: the row's own sentence, with the passed and waiting cases said plainly. */
export function statusLine(row: Row): string {
  if (row.state === 'passed') {
    if (row.id === 'engine') return row.detail
    if (row.id === 'companion') return 'Connected to VS Code.'
    return 'On. miyagi can use it now.'
  }
  // The word sits beside it already ("Not yet", "Watching"): don't say it twice.
  return row.detail.replace(/^(Not yet|Watching)\. /, '')
}

/** The companion can be skipped only when VS Code itself isn't on this computer (Not sure yet already offers Continue). */
export function canSkip(row: Row): boolean {
  return row.id === 'companion' && row.state !== 'passed' && row.action?.id === 'get-vscode'
}
