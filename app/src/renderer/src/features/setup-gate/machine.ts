/**
 * The setup gate's state machine (pure: no store, no DOM; tests: test/setupGate.test.ts).
 *
 * User test Nov 25 (MacBook Neo, fresh install): while the lesson's packages were still installing, the lesson started and
 * the video played. The engine now sends setup.gate (server/orchestrator/setup_gate.py) on every change; while it
 * `holds`, the lesson waits: the player keeps the clip paused ('setup') and the overlay shows this calm loading panel:
 *
 *   running   "Installing tensorflow… 2/4", a row per item (Downloading 41% · 92 of 224 MB), the time it has taken,
 *             Skip on optional rows
 *   failed    "Setup didn't finish": what failed in plain words, Retry, Show details (the installer's last lines),
 *             Continue anyway
 *   done      the panel goes; the player starts the clip (store.ts applySetupHold)
 *
 * Events: 'gate' (an engine setup.gate), 'toggleLog' (Show details), 'reset' (a new lesson, the lesson ended, a reconnect).
 */
import type { SetupGate, SetupGateItem } from '../../../../../../shared/contracts/events'

export type GateState = {
  gate?: SetupGate
  /** performance-free wall clock (ms) when the gate arrived, for the elapsed time when the engine sent no startedAt. */
  receivedAt: number
  /** The row whose installer log is open (Show details). */
  logFor?: string
  /** What the learner pressed last, so the button can show it's working until the next setup.gate. */
  pressed?: 'retry' | 'continue' | `skip:${string}`
}

export type GateEvent =
  | { type: 'gate'; payload: SetupGate; now: number }
  | { type: 'toggleLog'; tool?: string }
  | { type: 'press'; what: NonNullable<GateState['pressed']> }
  | { type: 'reset' }

export const initial: GateState = { receivedAt: 0 }

export function reduce(s: GateState, e: GateEvent): GateState {
  switch (e.type) {
    case 'reset':
      return initial
    case 'press':
      return { ...s, pressed: e.what }
    case 'toggleLog': {
      const failed = s.gate?.items.filter((x) => x.status === 'failed') ?? []
      const tool = e.tool ?? failed[0]?.tool
      return { ...s, logFor: s.logFor === tool ? undefined : tool }
    }
    case 'gate': {
      const g = e.payload
      // A row that stopped failing (Retry) closes its log; a new round keeps the one still failing.
      const keepLog = s.logFor && g.items.some((x) => x.tool === s.logFor && x.status === 'failed') ? s.logFor : undefined
      return { gate: g, receivedAt: e.now, logFor: keepLog, pressed: undefined }
    }
  }
}

/** The lesson waits (the player holds the clip). */
export const holds = (s: GateState): boolean => !!s.gate?.holds

/** The loading panel shows while the gate holds. An optional row installing on its own never covers the lesson. */
export const panelOpen = (s: GateState): boolean => holds(s)

const settled = (x: SetupGateItem): boolean => x.status === 'done' || x.status === 'skipped'

/** "Installing tensorflow… 2/4" / "Getting your lesson ready" / "Setup didn't finish". */
export function headline(g: SetupGate | undefined): string {
  if (!g) return ''
  if (g.phase === 'failed') return "Setup didn't finish"
  const cur = g.items.find((x) => x.status === 'installing')
  if (!cur) return 'Getting your lesson ready'
  const n = g.items.filter(settled).length + 1
  const of = g.total > 1 ? ` ${Math.min(n, g.total)}/${g.total}` : ''
  return `Installing ${cur.label}…${of}`
}

/** The calm line under the headline. */
export function subline(g: SetupGate | undefined): string {
  if (!g) return ''
  if (g.phase === 'failed') {
    const n = g.items.filter((x) => x.status === 'failed' && !x.optional).length
    return n === 1 ? 'One thing needs another try. The lesson waits until it is ready.' : `${n} things need another try. The lesson waits until they are ready.`
  }
  const big = g.items.some((x) => x.status !== 'done' && (x.totalBytes ?? 0) > 100e6)
  return big ? 'The video starts when everything is installed. Big downloads can take a few minutes.' : 'The video starts when everything is installed.'
}

const mb = (b: number): string => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`)

/** One row's status words (a failure's reason goes on its own line under the row: x.error). */
export function rowText(x: SetupGateItem): string {
  switch (x.status) {
    case 'queued':
      return 'Waiting'
    case 'done':
      return x.note && /couldn't confirm/i.test(x.note) ? 'Installed (first import is slow)' : 'Installed'
    case 'skipped':
      return x.errorCode === 'skipped_incompatible' ? 'Skipped: GPU add-on incompatible, runs on CPU' : 'Skipped'
    case 'failed':
      return "Didn't install"
    case 'installing':
      break
  }
  if (x.phase === 'downloading' && x.totalBytes) {
    const pct = x.pct ?? Math.round((100 * (x.bytes ?? 0)) / x.totalBytes)
    return `Downloading ${pct}% · ${mb(x.bytes ?? 0)} of ${mb(x.totalBytes)}`
  }
  if (x.phase === 'retrying') return `Connection stalled, trying again${x.attempt ? ` (try ${x.attempt})` : ''}`
  if (x.phase === 'verifying') return 'Checking it works'
  if (x.phase === 'installing') return 'Unpacking'
  if (x.phase === 'preparing') return 'Preparing the Python environment'
  return 'Starting'
}

/** 0..1 for a row's bar, or undefined (no bar: an indeterminate phase). */
export function rowFraction(x: SetupGateItem): number | undefined {
  if (x.status === 'done' || x.status === 'skipped') return 1
  if (x.status !== 'installing' || x.phase !== 'downloading' || !x.totalBytes) return undefined
  return Math.max(0, Math.min(1, (x.pct ?? (100 * (x.bytes ?? 0)) / x.totalBytes) / 100))
}

/** Seconds since this round of installs began: the engine's startedAt, else its elapsedS plus the time since it arrived. */
export function elapsedS(s: GateState, now: number): number {
  const g = s.gate
  if (!g) return 0
  if (g.startedAt) return Math.max(0, Math.floor((now - g.startedAt) / 1000))
  return Math.max(0, Math.floor((g.elapsedS ?? 0) + (now - s.receivedAt) / 1000))
}

/** "0:42", "12:05", "1:02:10". */
export function clock(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const ss = String(sec % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

export type GateAction = { kind: 'retry' | 'details' | 'continue' | 'continue_without' } | { kind: 'skip'; tool: string }

/** A required install running this long gets "Continue without it" (review H4: a slow link must never trap the lesson). */
export const CONTINUE_WITHOUT_S = 60

/** How long the row has been installing: its elapsedS when the gate arrived, plus the time since. */
export function rowElapsedS(x: SetupGateItem, receivedAt: number, now: number): number {
  return (x.elapsedS ?? 0) + Math.max(0, (now - receivedAt) / 1000)
}

/**
 * The buttons. failed: Retry (primary), Show details (when a log exists), Continue anyway. running: Skip on each
 * optional row still waiting or installing, and "Continue without it" once a required install has run
 * CONTINUE_WITHOUT_S (pass the state and now for that; the install keeps going, the lesson starts).
 */
export function actions(g: SetupGate | undefined, at?: { receivedAt: number; now: number }): GateAction[] {
  if (!g) return []
  if (g.phase === 'failed') {
    const out: GateAction[] = [{ kind: 'retry' }]
    if (g.items.some((x) => x.status === 'failed' && x.log)) out.push({ kind: 'details' })
    out.push({ kind: 'continue' })
    return out
  }
  const out: GateAction[] = g.items
    .filter((x) => x.optional && (x.status === 'queued' || x.status === 'installing'))
    .map((x) => ({ kind: 'skip' as const, tool: x.tool }))
  const slow = !!at && g.holds && g.items.some((x) => !x.optional && x.status === 'installing' && rowElapsedS(x, at.receivedAt, at.now) >= CONTINUE_WITHOUT_S)
  if (slow) out.push({ kind: 'continue_without' })
  return out
}

/** The engine action for a button (Show details is local). */
export function actionFor(a: GateAction): { kind: 'setup_retry' | 'setup_continue' | 'setup_skip'; text?: string } | undefined {
  if (a.kind === 'retry') return { kind: 'setup_retry' }
  if (a.kind === 'continue' || a.kind === 'continue_without') return { kind: 'setup_continue' }
  if (a.kind === 'skip') return { kind: 'setup_skip', text: a.tool }
  return undefined
}
