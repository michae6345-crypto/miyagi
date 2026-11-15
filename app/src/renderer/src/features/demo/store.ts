/**
 * Feature: demo. The fake desktop's state (the learner's VS Code: nn.py and the terminal) and the "ghost learner"
 * that types into it.
 *
 * The desktop reacts the way a real screen would:
 *   - engine `metric` events print the epoch lines in the terminal (so the run and the curve stay in step)
 *   - the learner's own presses: Check on a step whose code isn't typed yet fills it in (manual use), Check on a
 *     run step runs `python nn.py`, Fix it rewrites the zero weights and reruns
 *   - the walkthrough (walkthrough.ts) calls typeStep / runInTerminal directly, at its own pace
 */
import { create } from 'zustand'
import { onMessage, onUi } from '../../core/bus'
import { useLesson } from '../../core/lesson'
import { usePressed } from '../../core/shortcuts'
import { BUG, EPOCH_EVERY, FILE, PREDICT_FIXED, PREDICT_ZEROS, PRINT_EVERY, RUN, STEPS, epochLine } from './lesson'

/** Is the demo on? The stage URL: ?scenario=demo (the Demo button reloads into it). */
export const demoOn = typeof location !== 'undefined' && new URLSearchParams(location.search).get('scenario') === 'demo'

export const PROMPT = 'nn-from-scratch % '

type Desk = {
  /** nn.py as typed so far (one string per line). Empty and closed until step 1. */
  lines: string[]
  open: boolean
  /** The caret: line (1-based) and column. */
  caret?: { line: number; col: number }
  /** Lines being rewritten (the fix): drawn selected. */
  selected?: [number, number]
  /** Terminal lines; the last one is the live prompt (plus whatever is being typed). */
  term: string[]
  /** The zero weights have been replaced by the lesson's random ones. */
  fixed: boolean
  busy: boolean
}

const initial = (): Desk => ({ lines: [], open: false, caret: undefined, selected: undefined, term: [PROMPT], fixed: false, busy: false })

export const useDesk = create<Desk>(initial)
const set = useDesk.setState
const get = useDesk.getState

// ---------------------------------------------------------------------------
// Timing: a fast, steady typist (the audience should be able to follow it).
// ---------------------------------------------------------------------------

const CHAR_MS = 16
const LINE_MS = 70
let epoch = 0 // bumps on reset: cancels any typing in flight
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
const alive = (e: number): boolean => e === epoch

/** The text the learner types for a step: the lesson's code, except the zero-weights shortcut in step 2. */
function stepText(from: number, to: number, fixed: boolean): string[] {
  const out: string[] = []
  for (let n = from; n <= to; n++) out.push(!fixed && BUG[n] ? BUG[n] : FILE[n - 1])
  return out
}

const typedThrough = (to: number): boolean => get().lines.length >= to

/** Type a step's lines into nn.py (opening the file on the first step). Resolves when done. */
export async function typeStep(stepId: string): Promise<void> {
  const s = STEPS.find((x) => x.id === stepId)
  if (!s || typedThrough(s.to)) return
  const e = epoch
  set({ busy: true, open: true })
  // Blank lines between steps come for free (Enter, Enter).
  const pad = Array.from({ length: Math.max(0, s.from - 1 - get().lines.length) }, () => '')
  set((d) => ({ lines: [...d.lines, ...pad] }))
  for (const text of stepText(s.from, s.to, get().fixed)) {
    if (!alive(e)) return
    const line = get().lines.length + 1
    set((d) => ({ lines: [...d.lines, ''], caret: { line, col: 0 } }))
    const indent = text.length - text.trimStart().length
    // Auto-indent: the editor puts the indent in, the typist types the rest.
    for (let i = indent; i <= text.length; i++) {
      if (!alive(e)) return
      const cur = text.slice(0, i)
      set((d) => ({ lines: [...d.lines.slice(0, -1), cur], caret: { line, col: i } }))
      if (i < text.length) await sleep(CHAR_MS)
    }
    await sleep(LINE_MS)
  }
  if (alive(e)) set({ busy: false })
}

/** Manual use (Check pressed with nothing typed): put the step's code in at once. */
function fillStep(stepId: string): void {
  const s = STEPS.find((x) => x.id === stepId)
  if (!s || typedThrough(s.to)) return
  const lines = [...get().lines]
  while (lines.length < s.from - 1) lines.push('')
  for (let n = s.from; n <= s.to; n++) lines[n - 1] = stepText(n, n, get().fixed)[0]
  set({ lines, open: true, caret: { line: s.to, col: lines[s.to - 1].length } })
}

/** Type `python nn.py` at the prompt and press Enter. The output arrives with the engine's metric events. */
export async function runInTerminal(): Promise<void> {
  const e = epoch
  const last = get().term[get().term.length - 1]
  if (!last.startsWith(PROMPT) || last.length > PROMPT.length) return
  for (let i = 1; i <= RUN.length; i++) {
    if (!alive(e)) return
    // The run's output may already be arriving (the engine is quick): never type over it.
    const cur = get().term[get().term.length - 1]
    if (!cur.startsWith(PROMPT) || !RUN.startsWith(cur.slice(PROMPT.length))) return
    set((d) => ({ term: [...d.term.slice(0, -1), PROMPT + RUN.slice(0, i)] }))
    await sleep(CHAR_MS + 10)
  }
  await sleep(180)
}

/** Fix it: select the zero-weight lines, retype them random, like the lesson. */
async function applyFix(): Promise<void> {
  if (get().fixed) return
  const e = epoch
  const rows = Object.keys(BUG).map(Number)
  set({ fixed: true, selected: [Math.min(...rows), Math.max(...rows)] })
  await sleep(450)
  if (!alive(e)) return
  set({ selected: undefined })
  for (const n of rows) {
    if (!alive(e) || get().lines.length < n) continue
    const text = FILE[n - 1]
    for (let i = 0; i <= text.length; i += 2) {
      if (!alive(e)) return
      set((d) => ({ lines: d.lines.map((l, j) => (j === n - 1 ? text.slice(0, i) : l)), caret: { line: n, col: i } }))
      await sleep(10)
    }
    set((d) => ({ lines: d.lines.map((l, j) => (j === n - 1 ? text : l)) }))
  }
  await runInTerminal()
}

// ---------------------------------------------------------------------------
// The terminal follows the run the engine is watching: one epoch line every PRINT_EVERY epochs.
// ---------------------------------------------------------------------------

let runId = ''
const LAST_STEP = (20 - 1) * EPOCH_EVERY

onMessage('metric', (p) => {
  // The tutorial's reference curve isn't something the learner's terminal prints.
  if (!demoOn || p.runId === 'tutorial') return
  set((d) => {
    let term = [...d.term]
    const last = term[term.length - 1]
    // A new run: make sure its command is on the prompt line, then the output starts below it.
    if (p.runId !== runId) {
      runId = p.runId
      if (last.startsWith(PROMPT)) term[term.length - 1] = PROMPT + RUN
      else term.push(PROMPT + RUN)
    }
    if (p.step % PRINT_EVERY === 0) term.push(epochLine(p.step, p.value))
    if (p.step === LAST_STEP) {
      if (d.lines.length >= FILE.length) term.push(d.fixed ? PREDICT_FIXED : PREDICT_ZEROS)
      term.push(PROMPT)
    }
    if (term.length > 40) term = term.slice(-40)
    return { term }
  })
})

/** The learner's presses, from any surface (shortcut bar, cards, keys). */
usePressed.subscribe((p, prev) => {
  if (!demoOn || !p.kind || p.at === prev.at) return
  const stepId = useLesson.getState().stepId
  if (!stepId) return
  const step = STEPS.find((s) => s.id === stepId)
  if (p.kind === 'check_step' || p.kind === 'skip_step') {
    fillStep(stepId)
    if (p.kind === 'check_step' && step?.runs) void runInTerminal()
  }
  if (p.kind === 'apply_fix') void applyFix()
})

/** A step that passes or is skipped is on screen in full (whatever path got it there). */
onMessage('step.passed', (p) => demoOn && fillStep(p.stepId))

export function resetDesk(): void {
  epoch++
  runId = ''
  set(initial())
}
onUi('reset', () => demoOn && resetDesk())
onMessage('lesson.ended', () => demoOn && resetDesk())
