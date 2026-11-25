/**
 * Feature: ambient (help outside a lesson; shared/contracts/AMBIENT-HELP.md). The state behind its four surfaces:
 *
 *   chip     error.seen while no lesson runs: "Error in Terminal · Explain" in the notch, one at a time, for CHIP_MS
 *            (the pointer resting on it holds it). The same id again only updates it; an id that had its turn never
 *            comes back as a new chip. {id, clear} fades it.
 *   explain  Explain on the chip: error.explain {id} (the one moment the error leaves the Mac, and only its text, which
 *            the engine redacts), then error.explanation {pending} and the answer. Close sends error.dismiss.
 *   setup    "Set up this project" (launcher): setup.scan, then every setup.report fills the card; Fix sends setup.fix
 *            {tool, root}; setup.progress lines show under that row; "Fix all" fixes the rows one after another.
 *   help     "How do I ..." (launcher): help.ask {text, app}, then help.steps: bon points at steps[current].target and
 *            the notch shows the step line. Next / Back / close send help.nav. done closes it HELP_DONE_MS later.
 *
 * Model calls happen only on a click (Explain, a sent help.ask), never on their own. Nothing here sends a screenshot.
 * The launcher lives in its own window in Electron: it sends setup.scan / help.ask itself, and the overlay opens the
 * card when the answer arrives (every window gets every engine event).
 */
import { create } from 'zustand'
import type { ErrorExplanation, HelpSteps, SeenError, SetupReport } from '../../../../../../shared/contracts/events'
import { cmd } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { canSend, useLesson } from '../../core/lesson'
import { CHIP_MS, FAIL_MS, fixable, HELP_DONE_MS, isSeenError, offerError, ASK_MAX } from './model'
import { pointAt, pointAway, STEP_HOLD_MS } from './point'
import { useAmbientPrefs } from './prefs'

export type Install = { tool: string; line?: string; running: boolean; ok?: boolean; error?: string }

type State = {
  /** The error on the chip, or behind the open card. */
  error?: SeenError
  /** The chip shows (outside a card). */
  chip: boolean
  /** The pointer rests on the chip: its timer waits. */
  chipHeld: boolean
  /** The explanation card is open for `error`. */
  explainOpen: boolean
  explanation?: ErrorExplanation
  /** The error went away while its card was open ({id, clear}). */
  cleared: boolean
  /** The setup card is open; the newest report. */
  setupOpen: boolean
  report?: SetupReport
  /** setup.fix in flight and their last lines, by tool. */
  installs: Record<string, Install>
  /** Fix all: tools still to send, one after another. */
  queue: string[]
  /** The help line; the newest help.steps. */
  helpOpen: boolean
  help?: HelpSteps
  /** The help line is waiting for the first help.steps (the ask went out). */
  helpAsked?: string
}

const blank: State = { chip: false, chipHeld: false, explainOpen: false, cleared: false, setupOpen: false, installs: {}, queue: [], helpOpen: false }

export const useAmbient = create<State>(() => ({ ...blank }))
const get = useAmbient.getState
const set = useAmbient.setState

/** Errors that had their turn (closed, explained, timed out): never a new chip again this session. */
const seen = new Set<string>()
let chipTimer: ReturnType<typeof setTimeout> | undefined
let helpTimer: ReturnType<typeof setTimeout> | undefined
/** Help walk-throughs the learner closed: a late re-send never reopens them. */
const closedHelp = new Set<string>()
/** The scan whose card the learner closed: its later reports (after a fix) do not reopen it. */
let closedScan: string | undefined
let reqs = 0
const reqId = (kind: string): string => `amb-${kind}-${Date.now().toString(36)}-${++reqs}`

const lessonOn = (): boolean => {
  const l = useLesson.getState()
  return !!l.lesson || !!l.building || !!l.stepId
}

function stopChipTimer(): void {
  clearTimeout(chipTimer)
  chipTimer = undefined
}

function armChip(ms = CHIP_MS): void {
  stopChipTimer()
  chipTimer = setTimeout(() => {
    chipTimer = undefined
    if (get().chipHeld) return armChip(1500) // the pointer is on it: look again shortly
    hideChip()
  }, ms)
}

/** The chip had its turn: it goes, and that id never comes back as a chip. */
export function hideChip(): void {
  stopChipTimer()
  const e = get().error
  if (e) seen.add(e.id)
  if (get().chip) set({ chip: false, chipHeld: false, ...(get().explainOpen ? {} : { error: undefined }) })
}

export function holdChip(on: boolean): void {
  if (get().chipHeld !== on) set({ chipHeld: on })
}

/** error.seen: a new error (or the same one again) outside a lesson. */
export function seeError(p: unknown): void {
  if (!p || typeof p !== 'object') return
  const c = p as { id?: string; clear?: boolean }
  if (c.clear && typeof c.id === 'string') return clearError(c.id)
  if (!isSeenError(p)) return
  const s = get()
  const showing = s.chip || s.explainOpen ? s.error?.id : undefined
  if (!offerError(p, { prefs: useAmbientPrefs.getState(), lesson: lessonOn(), seen, showing })) return
  // An open card about another error stays: the new one waits its turn (it may come again).
  if (s.explainOpen && s.error?.id !== p.id) return
  if (s.error?.id === p.id) {
    set({ error: { ...s.error, ...p } })
    return
  }
  if (s.error && s.chip) seen.add(s.error.id) // one at a time: the newer error takes the chip
  set({ error: p, chip: true, chipHeld: false, explanation: undefined, cleared: false })
  armChip()
}

/** {id, clear}: that error is gone (the next run printed none, the dialog closed). */
export function clearError(id: string): void {
  const s = get()
  if (s.error?.id !== id) return
  if (s.explainOpen) {
    set({ cleared: true, chip: false })
    return
  }
  stopChipTimer()
  set({ chip: false, chipHeld: false, error: undefined })
}

/** Explain on the chip: open the card and ask the engine once (the same id again answers from its memory). */
export function explain(): void {
  const e = get().error
  if (!e) return
  stopChipTimer()
  seen.add(e.id)
  const have = get().explanation
  const fresh = !have || have.id !== e.id || !!have.error
  set({ chip: false, chipHeld: false, explainOpen: true, cleared: false, ...(fresh ? { explanation: { id: e.id, pending: true } } : {}) })
  if (fresh) askExplain(e.id)
}

function askExplain(id: string): void {
  if (!canSend('error.explain')) {
    set({ explanation: { id, error: 'offline' } })
    return
  }
  bridge.send(cmd('error.explain', { id, reqId: reqId('x') }))
}

/** Try again after a busy / offline / failed answer. */
export function retryExplain(): void {
  const e = get().error
  if (!e) return
  set({ explanation: { id: e.id, pending: true } })
  askExplain(e.id)
}

/** Close the explanation card (✕, Esc): the engine forgets the error. */
export function closeExplain(): void {
  const e = get().error
  if (e && canSend('error.dismiss')) bridge.send(cmd('error.dismiss', { id: e.id }))
  if (e) seen.add(e.id)
  pointAway()
  set({ explainOpen: false, chip: false, chipHeld: false, error: undefined, explanation: undefined, cleared: false })
}

/** The chip's ✕: not now. The engine forgets it too. */
export function dismissChip(): void {
  const e = get().error
  if (e && canSend('error.dismiss')) bridge.send(cmd('error.dismiss', { id: e.id }))
  hideChip()
}

/** Show me: bon points at where to look (the explanation's target, else the error itself). */
export function showError(): boolean {
  const s = get()
  const t = s.explanation?.target ?? s.error?.rect
  return pointAt(s.error?.id ?? 'error', t)
}

function onExplanation(p: ErrorExplanation): void {
  const s = get()
  if (!p || s.error?.id !== p.id) return
  set({ explanation: p })
}

// ---- setup ----------------------------------------------------------------------------------------------------------

/** "Set up this project": scan the folder open in the front editor. Opens the card at once (it says it is reading). */
export function scanProject(path?: string): boolean {
  if (!canSend('setup.scan')) return false
  const id = reqId('scan')
  bridge.send(cmd('setup.scan', { ...(path ? { path } : {}), reqId: id }))
  set({ setupOpen: true, report: { reqId: id, files: [], items: [], ready: 0, total: 0, scanning: true }, queue: [], installs: runningOnly(get().installs), helpOpen: false })
  closedScan = undefined
  return true
}

/** Fix one row (its button is the learner's yes). */
export function fixRow(tool: string): void {
  const r = get().report
  if (!canSend('setup.fix') || get().installs[tool]?.running) return
  bridge.send(cmd('setup.fix', { tool, ...(r?.root ? { root: r.root } : {}), reqId: reqId('fix') }))
  set((s) => ({ installs: { ...s.installs, [tool]: { tool, running: true } } }))
}

/** Fix all: the installable missing rows, one after another (never a licensed app). */
export function fixAll(): void {
  const tools = fixable(get().report?.items ?? []).filter((t) => !get().installs[t]?.running)
  if (!tools.length) return
  const [first, ...rest] = tools
  set({ queue: rest })
  fixRow(first)
}

export function closeSetup(): void {
  closedScan = get().report?.reqId ?? ''
  set({ setupOpen: false, queue: [] })
}

/** The installs still in flight (a fresh report is the truth for the finished ones). */
const runningOnly = (all: Record<string, Install>): Record<string, Install> => Object.fromEntries(Object.entries(all).filter(([, i]) => i.running))

/** One install ended (its done line, or a report that says the row is now there): the next queued one goes. */
function finish(tool: string, ok: boolean | undefined, error?: string): void {
  set((s) => ({ installs: { ...s.installs, [tool]: { tool, running: false, ok, error: ok ? undefined : error ?? 'failed' } } }))
  const [next, ...rest] = get().queue
  if (next) {
    set({ queue: rest })
    fixRow(next)
  }
}

function onReport(p: SetupReport): void {
  if (!p) return
  const s = get()
  // A scan answer opens the card (the launcher may have asked from its own window); a lesson's card wins over it.
  if (lessonOn() && !s.setupOpen) return
  // A later quick "scanning" answer never replaces a full one for the same request.
  if (p.scanning && s.report && !s.report.scanning && s.report.reqId === p.reqId) return
  // A row an install was running for is there now: that install is over, even if its done line never came.
  for (const x of p.items ?? []) if (s.installs[x.tool]?.running && x.ok) finish(x.tool, true)
  // Finished installs give way to the report (it says what is there now); a failed one keeps its line.
  const installs = Object.fromEntries(Object.entries(get().installs).filter(([, i]) => i.running || i.ok === false))
  // The report after an install from the explanation card: kept, but the learner is reading that card. And a card the
  // learner closed stays closed for that scan's later reports (a fresh scan, or its quick first answer, opens it).
  if ((s.explainOpen && !s.setupOpen) || (!s.setupOpen && !p.scanning && p.reqId !== undefined && p.reqId === closedScan)) return void set({ report: p, installs })
  closedScan = undefined
  set({ report: p, setupOpen: true, installs })
}

function onProgress(p: { tool: string; line?: string; done?: boolean; ok?: boolean; error?: string }): void {
  const s = get()
  if (!p?.tool) return
  // Only rows this card started (a lesson's own setup card has its own installs).
  if (!s.installs[p.tool]) return
  const cur = s.installs[p.tool]
  if (!p.done) {
    set({ installs: { ...s.installs, [p.tool]: { ...cur, line: p.line ?? cur.line, running: true } } })
    return
  }
  finish(p.tool, p.ok, p.error)
}

// ---- help -----------------------------------------------------------------------------------------------------------

/** "How do I ...": ask about `app` (the app that was in front before the launcher). */
export function askHelp(text: string, app?: string): boolean {
  const t = text.trim().slice(0, ASK_MAX)
  if (!t || !canSend('help.ask')) return false
  const id = reqId('help')
  clearTimeout(helpTimer)
  pointAway()
  bridge.send(cmd('help.ask', { text: t, reqId: id, ...(app ? { app } : {}), source: 'typed' }))
  set({ setupOpen: false, helpOpen: true, helpAsked: id, help: { reqId: id, app: app ?? '', goal: '', steps: [], current: 0, pending: true } })
  return true
}

export function helpNav(to: 'next' | 'back' | 'close'): void {
  const h = get().help
  if (canSend('help.nav')) bridge.send(cmd('help.nav', { ...(h?.reqId ? { reqId: h.reqId } : {}), to }))
  if (to === 'close') return closeHelp()
  // Move at once; the engine's re-send confirms (or corrects) it.
  if (h && h.steps.length) {
    const current = Math.max(0, Math.min(h.steps.length - 1, h.current + (to === 'next' ? 1 : -1)))
    if (current !== h.current) setHelp({ ...h, current })
  }
}

export function closeHelp(): void {
  clearTimeout(helpTimer)
  const id = get().help?.reqId
  if (id) closedHelp.add(id)
  pointAway()
  set({ helpOpen: false, help: undefined, helpAsked: undefined })
}

/** Point bon at the step to do now, when it (or where it is) changed. */
function setHelp(h: HelpSteps): void {
  const prev = get().help
  set({ help: h, helpOpen: true })
  const step = h.steps[h.current]
  const before = prev?.steps[prev.current]
  const moved = !before || before.id !== step?.id || JSON.stringify(before.target) !== JSON.stringify(step?.target)
  if (!step || h.done) return pointAway()
  if (moved) {
    pointAway()
    pointAt(`${h.reqId ?? 'help'}-${step.id}`, step.target, STEP_HOLD_MS)
  }
}

function onSteps(p: HelpSteps): void {
  if (!p) return
  // One help at a time, and a new help.ask replaces the one before (the engine stops the old one), so the newest
  // help.steps is the one: also when the launcher's own window sent the ask.
  if (lessonOn() || (p.reqId && closedHelp.has(p.reqId))) return
  clearTimeout(helpTimer)
  if (p.pending) {
    if (get().help?.reqId !== p.reqId) pointAway()
    set({ helpOpen: true, help: p, helpAsked: p.reqId, setupOpen: false })
    return
  }
  setHelp(p)
  if (p.done) helpTimer = setTimeout(closeHelp, HELP_DONE_MS)
  else if (p.error) helpTimer = setTimeout(closeHelp, FAIL_MS)
}

// ---- wiring ---------------------------------------------------------------------------------------------------------

onMessage('error.seen', (p) => seeError(p))
onMessage('error.explanation', (p) => onExplanation(p))
onMessage('setup.report', (p) => onReport(p))
onMessage('setup.progress', (p) => onProgress(p))
onMessage('help.steps', (p) => onSteps(p))

// A lesson starting takes the island: the chip goes, the help walk-through ends (the engine stops it too).
onMessage('lesson.ready', () => {
  if (get().chip) hideChip()
  if (get().helpOpen) closeHelp()
})

// Turning the setting off (or muting the app on screen) takes the chip away at once.
useAmbientPrefs.subscribe((p) => {
  const e = get().error
  if (!e || !get().chip) return
  if (!p.errors || p.mutedApps.some((m) => m.trim().toLowerCase() === e.app.trim().toLowerCase())) hideChip()
})

/** Esc: the top ambient surface closes (explain, then setup, then help, then the chip). Never claims the event. */
onUi('dismiss', () => {
  const s = get()
  if (s.explainOpen) return void closeExplain()
  if (s.setupOpen) return void closeSetup()
  if (s.helpOpen) return void helpNav('close')
  if (s.chip) hideChip()
})

onUi('reset', (p) => {
  if ((p as { scope?: string } | undefined)?.scope === 'lesson') return
  stopChipTimer()
  clearTimeout(helpTimer)
  seen.clear()
  closedHelp.clear()
  set({ ...blank }, true)
})

/** Test seam: forget the seen ids and timers. */
export function resetAmbient(): void {
  stopChipTimer()
  clearTimeout(helpTimer)
  seen.clear()
  closedHelp.clear()
  set({ ...blank }, true)
}
