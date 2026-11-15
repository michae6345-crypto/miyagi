/**
 * Feature: cards. Which coach card is showing, plus the live metric series behind the curve.
 * The off-track payload itself lives in core/lesson; core doesn't keep metrics, so they live here.
 */
import { create } from 'zustand'
import type { Payload } from '../../../../common/wire'
import { bridge } from '../../bridge'
import { onMessage, onUi } from '../../core/bus'
import { sendAction, usePressed, type ActionKind } from '../../core/shortcuts'
import { seekVideo, useLesson, type CheckItem } from '../../core/lesson'

export type Point = { step: number; value: number }
/** `seq` = event order of its first point (compared with the off-track's), `at` = when its last point arrived (ms). */
export type Run = { runId: string; points: Point[]; seq: number; at: number }
/** One metric (any name the engine sends): the current run, and the run before it (e.g. before the fix). */
export type Series = { run: Run; before?: Run }

/** runId the engine may use for the tutorial's reference curve (open question 4 in FRONTEND-HANDOFF). */
export const TUTORIAL_RUN = 'tutorial'
/** Points kept per run. Past this, every other point is dropped (the shape survives, memory doesn't grow). */
const MAX_POINTS = 400
/** How long "Back on track" stays up. */
export const SUCCESS_MS = 4800

type CardsState = {
  /** The off-track card is open (it can be dismissed; hovering the pill reopens it). */
  offtrackOpen: boolean
  /** ✕ was pressed on this off-track: hovering must not reopen it (until a new off-track or step). */
  offtrackClosed: boolean
  /** Do it for me (apply_fix) was pressed: the off-track card collapses to a compact "applying the fix" card until the step passes. */
  fixing: boolean
  /** The current step went off-track at some point → show "Back on track" when it passes. */
  recovered: boolean
  /** An explain card or a diagram opened on top of the off-track card: closing it brings the off-track card back. */
  resume: boolean
  /** When the latest off-track fired: a run that starts after it is "after the fix". */
  offtrackSeq?: number
  /** "Back on track". `since` = the off-track's event order (so the curve can split before/after). */
  success?: { index: number; total: number; summary?: string; checks: CheckItem[]; at: number; since?: number }
  card?: Payload<'card'>
  /** The action the learner pressed that this card answers (show_me, check_step, run_command…), if it came soon after. */
  cardFrom?: ActionKind
  /** Live `metric` events, by metric name. */
  metrics: Record<string, Series>
  /** The tutorial's reference curve, if the engine streams it as runId "tutorial". */
  tutorial: Record<string, Point[]>
  /** Setup installs in flight, by tool id: the latest `setup.progress` line, or the failure once it ends. */
  installs: Record<string, Install>
  /**
   * A card button whose answer we're waiting for (download, open_editor, build, confirm…). The card stays up
   * so its button can show the spinner (never look dead); it closes when the engine answers or after PENDING_MS.
   */
  pending?: { kind: CardAction; at: number; sawThinking: boolean }
  /** What the finder said about each result (style, captions…), by videoId and url: the preflight card's meta line. */
  results: Record<string, ResultMeta>
}

export type ResultMeta = Pick<Payload<'search.result'>, 'style' | 'captions' | 'chapters' | 'durationS'>

/** One setup item's install: running (Install button disabled, spinner + latest line) until done. */
export type Install = { running: boolean; line?: string; error?: string }

const blank: CardsState = { offtrackOpen: false, offtrackClosed: false, fixing: false, recovered: false, resume: false, offtrackSeq: undefined, success: undefined, card: undefined, cardFrom: undefined, metrics: {}, tutorial: {}, installs: {}, pending: undefined, results: {} }
export const useCards = create<CardsState>(() => ({ ...blank }))

/**
 * The overlay's width in points (the display in Electron, 1600 in the browser stage), from an invisible
 * overlay layer (index.tsx). Its own store so lesson resets never touch it. The off-track card sizes from it.
 */
export const useOverlayWidth = create<{ w: number }>(() => ({ w: typeof window === 'undefined' ? 1600 : window.innerWidth }))
const set = useCards.setState
const get = useCards.getState

let successTimer: ReturnType<typeof setTimeout> | undefined

/**
 * The off-track the learner closed with ✕. The engine re-sends `offtrack` while the step keeps
 * failing; an unchanged one must not pop the card back up. It reopens only for a new step, a
 * higher hint level or a different title (hovering the pill still brings it back; the pill keeps its off-track ring).
 */
type OfftrackSig = { stepId: string; level: number; title: string }
let dismissed: OfftrackSig | undefined
const sig = (o: Payload<'offtrack'>): OfftrackSig => ({ stepId: o.stepId, level: o.level ?? 1, title: o.title })
const stillDismissed = (o: Payload<'offtrack'>): boolean => {
  if (!dismissed) return false
  const n = sig(o)
  return n.stepId === dismissed.stepId && n.level <= dismissed.level && n.title === dismissed.title
}

/** Thin a run that grew past MAX_POINTS: keep every other point, always keep the newest. */
function thin(points: Point[]): Point[] {
  if (points.length <= MAX_POINTS) return points
  return points.filter((_, i) => i % 2 === 0 || i === points.length - 1)
}

function append(run: Run, p: Point): Run {
  const last = run.points[run.points.length - 1]
  const points = last && last.step === p.step ? [...run.points.slice(0, -1), p] : thin([...run.points, p])
  return { ...run, points, at: Date.now() }
}

/** Event order for metric runs and off-tracks: a run is "after the fix" if it started after the off-track. */
let seq = 0
const newRun = (runId: string, p: Point): Run => ({ runId, points: [p], seq: ++seq, at: Date.now() })

/** A card button → `action {kind}`. Do it for me (apply_fix) collapses the off-track card into the "applying the fix" view. */
export function act(kind: 'show_me' | 'explain' | 'apply_fix' | 'hint'): void {
  sendAction(kind)
  if (kind === 'apply_fix') set({ fixing: true, offtrackOpen: true })
}

/** Every button kind an engine card can carry (card.actions). */
export type CardAction = NonNullable<Payload<'card'>['actions']>[number]

/** Buttons that end the card right away. Every other kind waits for the engine with a spinner on the button. */
const CLOSE_NOW = new Set<CardAction>(['pick_another', 'skip_setup'])
/** Buttons that act on one row of the card (install / open a setup item): the card stays, no pending state. */
const PER_ITEM = new Set<CardAction>(['install', 'open_in_browser'])
/** Longest a card waits on its pressed button before it closes anyway (the engine may never say "thinking"). */
const PENDING_MS = 10_000
let pendingTimer: ReturnType<typeof setTimeout> | undefined
/**
 * Buttons with no answer to wait for: open_editor brings the editor forward and the engine says nothing back (no
 * "thinking", no card), so the button spun until PENDING_MS (Michael's desktop test 5). They spin SETTLE_MS, then the
 * card settles: it closes when that button was its only job (the where card's Open), else it stays for its other buttons.
 */
const SETTLE = new Set<CardAction>(['open_editor'])
const SETTLE_MS = 900
function settle(kind: CardAction): void {
  const card = get().card
  const at = Date.now()
  set({ pending: { kind, at, sawThinking: false } })
  clearTimeout(pendingTimer)
  pendingTimer = setTimeout(() => {
    if (get().pending?.at !== at) return // answered, replaced or closed meanwhile
    const rest = (card?.actions ?? []).filter((a) => a !== kind && !CLOSE_NOW.has(a))
    if (get().card !== card || rest.length > 0) set({ pending: undefined })
    else closeCard()
  }, SETTLE_MS)
}

/**
 * A button on an engine card → `action {kind}` (install / open_in_browser: text = the setup item's tool id).
 * pick_another / skip_setup close the card; open_editor settles after a short spin (SETTLE); the rest keep it up, the
 * pressed button spinning, until the engine answers (next card or event, status leaves "thinking") or PENDING_MS passes.
 */
export function cardAct(kind: CardAction, text?: string): void {
  if (kind === 'install' && text !== undefined) {
    // One install per tool: a double click can't start a second one.
    if (get().installs[text]?.running) return
    setInstall(text, { running: true, line: undefined, error: undefined })
  }
  // One answer at a time; Skip / Pick another always work (they just end the card).
  if (get().pending && !PER_ITEM.has(kind) && !CLOSE_NOW.has(kind)) return
  sendAction(kind, text)
  if (PER_ITEM.has(kind)) return
  if (CLOSE_NOW.has(kind)) {
    closeCard()
    // "Pick another": back to the results in the launcher (the launcher keeps them).
    if (kind === 'pick_another') bridge.emit('launcher:toggle')
    return
  }
  if (SETTLE.has(kind)) return settle(kind)
  const at = Date.now()
  set({ pending: { kind, at, sawThinking: false } })
  clearTimeout(pendingTimer)
  pendingTimer = setTimeout(() => {
    if (get().pending?.at === at) closeCard()
  }, PENDING_MS)
}

/**
 * A card that's done waits this long before it goes (Michael's review A1): a card that arrives meanwhile takes its place
 * in the open island, so close-then-card in quick succession never flashes the island down to nothing. The pressed
 * button keeps its spinner until then.
 */
const CLOSE_DELAY_MS = 100
let closeTimer: ReturnType<typeof setTimeout> | undefined

function closeCard(): void {
  clearTimeout(pendingTimer)
  if (closeTimer) return // already on its way out
  const closing = get().card
  closeTimer = setTimeout(() => {
    closeTimer = undefined
    // Whatever replaced or cleared it meanwhile (a new card, ✕, a reset) has already decided.
    if (get().card === closing) set({ card: undefined, pending: undefined })
  }, CLOSE_DELAY_MS)
}
/** Anything that sets or clears the card itself drops a close still on its way. */
function cancelClose(): void {
  clearTimeout(closeTimer)
  closeTimer = undefined
}

function setInstall(tool: string, patch: Partial<Install>): void {
  const installs = get().installs
  set({ installs: { ...installs, [tool]: { ...(installs[tool] ?? { running: false }), ...patch } } })
}

// The engine answered the pressed card button: "thinking" came and went.
onMessage('status', (p) => {
  const pending = get().pending
  if (!pending) return
  if (p.state === 'thinking') set({ pending: { ...pending, sawThinking: true } })
  else if (pending.sawThinking) closeCard()
})
// Build on the preflight card: the lesson is being built, so the card is done.
onMessage('lesson.building', () => {
  if (get().card?.kind === 'preflight') closeCard()
})
// The finder's facts about each result, for the preflight card's meta line (style, captions…).
onMessage('search.result', (p) => {
  const meta: ResultMeta = { style: p.style, captions: p.captions, chapters: p.chapters, durationS: p.durationS }
  const results = { ...get().results }
  for (const key of [p.videoId, p.url]) if (key) results[key] = meta
  set({ results })
})

/** Install progress: lines while it runs, then {done, ok, error}. A re-sent setup card with the item ok flips the row to a check. */
onMessage('setup.progress', (p) => {
  if (p.done) setInstall(p.tool, { running: false, line: undefined, error: p.ok === false ? (p.error ?? 'Install failed') : undefined })
  else if (p.line) setInstall(p.tool, { running: true, line: p.line })
  else setInstall(p.tool, { running: true })
})

/** A card's video jump: core seekVideo sets the intent in every window; the player follows core/lesson.video. */
export function jumpTo(t: number): void {
  seekVideo(t, true)
  closeTop()
}

/** Close the card on top; if it opened over the off-track card, that card comes back. */
function closeTop(): void {
  const s = get()
  const offtrack = useLesson.getState().offtrack
  // ✕ on the off-track card itself (nothing on top of it): remember it, so a re-send stays closed.
  const closingOfftrack = !s.card && !s.success && !!offtrack
  if (closingOfftrack) dismissed = sig(offtrack)
  const back = s.resume && !!offtrack
  clearTimeout(pendingTimer)
  cancelClose()
  set({ card: undefined, success: undefined, resume: false, offtrackOpen: back, pending: undefined, ...(closingOfftrack ? { offtrackClosed: true } : {}) })
}
const over = (): boolean => get().offtrackOpen || get().resume

onUi('reset', (p) => {
  clearTimeout(successTimer)
  clearTimeout(pendingTimer)
  cancelClose()
  dropHeldOfftrack()
  dismissed = undefined
  // scope "lesson" (lesson.ended): a new search may be in flight, so keep what the finder said about its results.
  const keep = (p as { scope?: string } | undefined)?.scope === 'lesson'
  set({ ...blank, results: keep ? get().results : {} })
})
// ⌥H while the off-track card is closed brings it back (claimed: no new hint request). Open, ⌥H asks for a hint.
onUi('shortcut', (kind) => {
  if (kind !== 'hint') return
  const s = get()
  if (!useLesson.getState().offtrack || s.offtrackOpen || s.card || s.success) return
  dismissed = undefined
  set({ offtrackOpen: true })
  return true
})
onUi('dismiss', closeTop)
onMessage('lesson.ready', () => {
  dropHeldOfftrack()
  dismissed = undefined
  clearTimeout(pendingTimer)
  cancelClose()
  // Keep what the finder said about the results: a preflight card may still be up for the next pick.
  set({ ...blank, results: get().results })
})
// A card with buttons survives step.started when it's for this step or for no step
// (e.g. "Open VS Code?" or "Continue where you left off?"); plain cards are cleared as before.
onMessage('step.started', (p) => {
  const c = get().card
  const keep = !!c?.actions?.length && (!c.stepId || c.stepId === p.stepId)
  dropHeldOfftrack()
  dismissed = undefined
  set({ offtrackOpen: false, offtrackClosed: false, fixing: false, recovered: false, resume: false, offtrackSeq: undefined, card: keep ? c : undefined })
})
/**
 * A card the learner asked for (Explain, Hint, Show me, an answer) is held this long before an automatic off-track
 * may replace it (Michael's desktop test). An off-track that arrives meanwhile waits and opens when the hold ends.
 */
const CARD_HOLD_MS = 8000
/** A card this soon after the learner pressed one of these counts as the one they asked for. */
const ASKED_WITHIN_MS = 30000
const ASKED = new Set(['explain', 'hint', 'show_me', 'ask'])
let lastAsk = 0
/** The last press of any kind (for the card's tile: a Show me answer gets the Show me tile); spent once answered. */
let lastPress: { kind: ActionKind; at: number } | undefined
// core clears `pressed` as soon as a card arrives (possibly before our handler runs), so note presses as they happen.
usePressed.subscribe((s) => {
  if (s.kind && ASKED.has(s.kind)) lastAsk = s.at
  if (s.kind) lastPress = { kind: s.kind, at: s.at }
})
// A press answered by something other than a card (a spotlight, a video jump, a diagram) is spent.
for (const t of ['spotlight', 'video.seek', 'diagram', 'offtrack'] as const)
  onMessage(t, () => {
    lastPress = undefined
  })
let cardHeldUntil = 0
let heldOfftrack: Payload<'offtrack'> | undefined
let offtrackTimer: ReturnType<typeof setTimeout> | undefined
function dropHeldOfftrack(): void {
  clearTimeout(offtrackTimer)
  offtrackTimer = undefined
  heldOfftrack = undefined
  cardHeldUntil = 0
}

function openOfftrack(p: Payload<'offtrack'>): void {
  // A re-send of the off-track the learner closed: keep the state (off-track pill, recovered) but not the card.
  if (stillDismissed(p)) {
    set({ recovered: true })
    return
  }
  dismissed = undefined
  cancelClose()
  set({ offtrackOpen: true, offtrackClosed: false, fixing: false, recovered: true, resume: false, offtrackSeq: ++seq, card: undefined, pending: undefined, success: undefined })
}
/**
 * A card waiting on the learner's decision: a fix preview to confirm ("Type this for you?", card.diff) or the
 * resume card. The engine re-sends `offtrack` while the step keeps failing, which used to wipe this card before
 * the learner could press it (Michael's desktop test 3, 1:20 AM: "Do it for me" showed nothing). An automatic
 * off-track never replaces it: the pill keeps its off-track ring, and the off-track card can open once this one closes.
 */
const DECISION = new Set<CardAction>(['confirm', 'resume'])
const awaitsDecision = (c: Payload<'card'> | undefined): boolean => !!c && (!!c.diff || !!c.actions?.some((a) => DECISION.has(a)))
onMessage('offtrack', (p) => {
  if (awaitsDecision(get().card)) {
    lastPress = undefined
    return
  }
  const left = cardHeldUntil - Date.now()
  if (get().card && left > 0) {
    heldOfftrack = p // the newest one wins
    if (!offtrackTimer)
      offtrackTimer = setTimeout(() => {
        const q = heldOfftrack
        dropHeldOfftrack()
        if (q) openOfftrack(q)
      }, left)
    return
  }
  dropHeldOfftrack()
  openOfftrack(p)
})
// "Apply this fix?" (a diff to confirm) replaces the "Waiting for the fix" view, so `fixing` ends here.
onMessage('card', (p) => {
  // A re-sent setup card: rows that are installed now drop their install state.
  const ok = new Set((p.setup?.items ?? []).filter((x) => x.ok).map((x) => x.tool))
  if (ok.size) set({ installs: Object.fromEntries(Object.entries(get().installs).filter(([t]) => !ok.has(t))) })
  clearTimeout(pendingTimer)
  cancelClose() // it takes the closing card's place
  const cardFrom = lastPress && Date.now() - lastPress.at < ASKED_WITHIN_MS ? lastPress.kind : undefined
  lastPress = undefined
  set({ card: p, cardFrom, pending: undefined, resume: over(), offtrackOpen: false, ...(p.diff ? { fixing: false } : {}) })
  if (lastAsk && Date.now() - lastAsk < ASKED_WITHIN_MS) {
    cardHeldUntil = Date.now() + CARD_HOLD_MS
    lastAsk = 0
  }
})
onMessage('diagram', () => {
  cancelClose()
  set({ card: undefined, pending: undefined, resume: over(), offtrackOpen: false })
})
onMessage('step.passed', (p) => {
  const { recovered, offtrackSeq } = get()
  set({ offtrackOpen: false, fixing: false, resume: false })
  if (!recovered || p.skipped) return
  const lesson = useLesson.getState()
  const index = lesson.steps.findIndex((x) => x.id === p.stepId)
  const summary = (p as typeof p & { summary?: string }).summary
  set({ success: { index, total: lesson.steps.length, summary, checks: lesson.checks, at: Date.now(), since: offtrackSeq } })
  clearTimeout(successTimer)
  successTimer = setTimeout(() => set({ success: undefined }), SUCCESS_MS)
})

/**
 * metric {runId, step, name, value}. A new run starts when the runId changes or the step goes
 * backwards (the learner re-ran the script); the old run is kept as `before` for "now vs before fix".
 */
onMessage('metric', (p) => {
  if (!Number.isFinite(p.step) || !Number.isFinite(p.value)) return
  const pt: Point = { step: p.step, value: p.value }
  const s = get()

  if (p.runId === TUTORIAL_RUN) {
    const prev = s.tutorial[p.name] ?? []
    set({ tutorial: { ...s.tutorial, [p.name]: thin([...prev.filter((x) => x.step !== pt.step), pt].sort((a, b) => a.step - b.step)) } })
    return
  }

  const cur = s.metrics[p.name]
  let next: Series
  if (!cur) next = { run: newRun(p.runId, pt) }
  else if (cur.before && p.runId === cur.before.runId && p.runId !== cur.run.runId) next = { ...cur, before: append(cur.before, pt) } // late point from the old run
  else {
    const last = cur.run.points[cur.run.points.length - 1]
    const restart = p.runId !== cur.run.runId || (last !== undefined && p.step < last.step)
    next = restart ? { run: newRun(p.runId, pt), before: cur.run } : { ...cur, run: append(cur.run, pt) }
  }
  set({ metrics: { ...s.metrics, [p.name]: next } })
})

/**
 * The series a card should draw: the metric named `label` (the off-track curve's label) if it
 * streams, else the most recently updated one. `after` = the run that started after the off-track
 * (the re-run), if any; `before` = the run it replaced (or the current run, until the re-run starts).
 */
export function useSeries(label?: string, since?: number): { name?: string; series?: Series; tutorial?: Point[]; after?: Run; before?: Run } {
  const metrics = useCards((c) => c.metrics)
  const tutorial = useCards((c) => c.tutorial)
  const offtrackSeq = useCards((c) => since ?? c.offtrackSeq)
  const name = label && metrics[label] ? label : latest(metrics)
  const series = name ? metrics[name] : undefined
  const after = series && offtrackSeq !== undefined && series.run.seq > offtrackSeq ? series.run : undefined
  const before = after ? series?.before : series?.run
  return { name, series, tutorial: name ? tutorial[name] : undefined, after, before }
}

function latest(metrics: Record<string, Series>): string | undefined {
  let best: string | undefined
  for (const [k, v] of Object.entries(metrics)) if (!best || v.run.at > metrics[best].run.at) best = k
  return best
}
