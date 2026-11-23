/**
 * Push to talk: the JSON-lines protocol with the miyagi-listen helper (miyagi-v2/PUSH-TO-TALK.md). Pure: no electron,
 * no I/O, so the parser, the command builders and the term list are tested offline (test/pttProtocol.test.ts).
 *
 *   helper -> main (stdout): ready, perm, ptt, listening, partial, final, cancelled, error
 *   main -> helper (stdin):  config, context, permissions, cancel, quit, capture, capture-release
 *   helper -> main, capture: the answer to one capture request (parseCaptureLine; never a HelperEvent)
 *
 * Whatever comes out of the helper is untrusted input: every line is validated, unknown types and malformed fields
 * are dropped (parseLine returns undefined), text is length-capped. Session bookkeeping (a stale id is dropped) lives in
 * common/pttState.ts, which this file feeds.
 */
import type { PttChord } from '../common/prefs'

export type PttErrorCode = 'input_denied' | 'mic_denied' | 'mic_undetermined' | 'assets_missing' | 'no_stt' | 'tap_failed'
export type PttCancelReason = 'esc' | 'keypress' | 'short' | 'empty' | 'timeout' | 'disabled'
export type MicPerm = 'granted' | 'denied' | 'undetermined'
export type InputPerm = 'granted' | 'denied'
export type AssetsState = 'installed' | 'missing' | 'downloading'
export type SttKind = 'speechanalyzer' | 'sfspeech' | 'none'

export type HelperEvent =
  | { type: 'ready'; stt: SttKind; locale: string; chord: string }
  | { type: 'perm'; mic: MicPerm; input: InputPerm; assets?: AssetsState }
  | { type: 'ptt'; state: 'down' | 'up'; id: string }
  | { type: 'listening'; id: string }
  | { type: 'partial'; id: string; text: string }
  | { type: 'final'; id: string; text: string }
  | { type: 'cancelled'; id: string; reason: PttCancelReason }
  | { type: 'error'; code: PttErrorCode; message: string }

export const ERROR_CODES: readonly PttErrorCode[] = ['input_denied', 'mic_denied', 'mic_undetermined', 'assets_missing', 'no_stt', 'tap_failed']
export const CANCEL_REASONS: readonly PttCancelReason[] = ['esc', 'keypress', 'short', 'empty', 'timeout', 'disabled']

/** One line from the helper. A real utterance is a sentence or two; anything beyond this is a fault, not speech. */
export const MAX_LINE = 16_384
export const MAX_TEXT = 2000
const MAX_ID = 64
/** A hold is capped at 60 s in the helper (the design); main and the island add margin before they give up. */
export const MAX_HOLD_MS = 60_000
export const HARD_CAP_MS = 65_000
/** Debounce the helper applies before it opens the mic. */
export const MIN_HOLD_MS = 250

const isStr = (v: unknown, max: number): v is string => typeof v === 'string' && v.length <= max
const oneOf = <T extends string>(v: unknown, list: readonly T[]): v is T => typeof v === 'string' && (list as readonly string[]).includes(v)
/** An id is a short token (UUID or counter). Not empty, no whitespace. */
const isId = (v: unknown): v is string => isStr(v, MAX_ID) && /^[\w.:-]+$/.test(v)
const clean = (s: string): string => s.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim()

/** Parse and validate one stdout line. Anything that is not a well-formed event is dropped (undefined). */
export function parseLine(line: string): HelperEvent | undefined {
  if (typeof line !== 'string' || line.length === 0 || line.length > MAX_LINE) return undefined
  let o: unknown
  try {
    o = JSON.parse(line)
  } catch {
    return undefined
  }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return undefined
  const r = o as Record<string, unknown>
  switch (r.type) {
    case 'ready':
      return oneOf(r.stt, ['speechanalyzer', 'sfspeech', 'none'] as const) && isStr(r.locale, 35) && isStr(r.chord, 40) ? { type: 'ready', stt: r.stt, locale: r.locale, chord: r.chord } : undefined
    case 'perm': {
      if (!oneOf(r.mic, ['granted', 'denied', 'undetermined'] as const) || !oneOf(r.input, ['granted', 'denied'] as const)) return undefined
      const assets = oneOf(r.assets, ['installed', 'missing', 'downloading'] as const) ? r.assets : undefined
      return { type: 'perm', mic: r.mic, input: r.input, ...(assets ? { assets } : {}) }
    }
    case 'ptt':
      return (r.state === 'down' || r.state === 'up') && isId(r.id) ? { type: 'ptt', state: r.state, id: r.id } : undefined
    case 'listening':
      return isId(r.id) ? { type: 'listening', id: r.id } : undefined
    case 'partial':
    case 'final':
      return isId(r.id) && isStr(r.text, MAX_TEXT) ? { type: r.type, id: r.id, text: clean(r.text) } : undefined
    case 'cancelled':
      return isId(r.id) && oneOf(r.reason, CANCEL_REASONS) ? { type: 'cancelled', id: r.id, reason: r.reason } : undefined
    case 'error':
      return oneOf(r.code, ERROR_CODES) ? { type: 'error', code: r.code, message: isStr(r.message, 300) ? clean(r.message) : '' } : undefined
    default:
      return undefined
  }
}

/** stdout arrives in arbitrary chunks: this joins them and yields whole lines. A runaway line without a newline is dropped. */
export function lineBuffer(): { push(chunk: string): string[]; reset(): void } {
  let rest = ''
  return {
    push(chunk) {
      rest += chunk
      const lines = rest.split('\n')
      rest = lines.pop() ?? ''
      if (rest.length > MAX_LINE) rest = ''
      return lines.map((l) => l.replace(/\r$/, '')).filter((l) => l.length > 0)
    },
    reset() {
      rest = ''
    }
  }
}

// ---- commands (main -> helper) --------------------------------------------------------------------------------------

export type PttConfig = { enabled: boolean; chord: PttChord; locale?: string }

const line = (o: object): string => `${JSON.stringify(o)}\n`

export const configCommand = (c: PttConfig): string =>
  line({ cmd: 'config', enabled: c.enabled, chord: c.chord, minHoldMs: MIN_HOLD_MS, maxHoldMs: MAX_HOLD_MS, locale: c.locale ?? 'en-US' })
export const contextCommand = (terms: readonly string[]): string => line({ cmd: 'context', terms: cleanTerms(terms) })
export const permissionsCommand = (request: 'input' | 'mic' | 'assets'): string => line({ cmd: 'permissions', request })
export const CANCEL_COMMAND = line({ cmd: 'cancel' })
export const QUIT_COMMAND = line({ cmd: 'quit' })

const MAX_TERMS = 80
const MAX_TERM = 48

/** Trim, drop empties and duplicates (case-insensitive), cap the length and the count. Order is kept. */
export function cleanTerms(terms: readonly unknown[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const t of terms) {
    if (typeof t !== 'string') continue
    const s = clean(t).slice(0, MAX_TERM).trim()
    const k = s.toLowerCase()
    if (!s || seen.has(k)) continue
    seen.add(k)
    out.push(s)
    if (out.length >= MAX_TERMS) break
  }
  return out
}

/** The words worth teaching the recognizer: the lesson's title, the step's title, its concepts and library names. */
export type TermSource = { lessonTitle?: string; stepTitle?: string; concepts?: readonly string[]; libraries?: readonly string[] }

export function contextTerms(src: TermSource): string[] {
  return cleanTerms([src.lessonTitle ?? '', src.stepTitle ?? '', ...(src.libraries ?? []), ...(src.concepts ?? [])])
}

/**
 * Library-looking words out of a block of lesson text (code, step instructions): `import numpy as np`, `from torch import nn`,
 * `pip install pandas`. Only the top-level package names.
 */
export function libraryNames(text: string): string[] {
  const out: string[] = []
  const re = /^\s*(?:import|from)\s+([A-Za-z_][\w]*)|pip3?\s+install\s+([A-Za-z][\w.-]*)/gm
  for (const m of text.matchAll(re)) out.push(m[1] ?? m[2])
  return out
}

// ---- macOS grants that went stale ------------------------------------------------------------------------------------

/** miyagi is signed ad hoc, so every reinstall is a "different" app to macOS: the Privacy list can show miyagi switched ON
 *  while macOS answers "denied" for the new build. Resetting miyagi's own row (and the helper's) makes the next ask a
 *  real prompt again. Only ever run on an explicit Allow click while the grant reads denied. */
export const TCC_IDS = ['dev.sandhacks.miyagi', 'dev.sandhacks.miyagi.listen'] as const
export const TCC_SERVICE = { input: 'ListenEvent', mic: 'Microphone' } as const

/** The `tccutil` argument lists that clear miyagi's stale row for one permission. */
export function tccResetArgs(kind: 'input' | 'mic'): string[][] {
  return TCC_IDS.map((id) => ['reset', TCC_SERVICE[kind], id])
}

// ---- respawn backoff ------------------------------------------------------------------------------------------------

export const BACKOFF_MS = [500, 1000, 2000, 5000, 10_000, 30_000] as const
/** The helper stayed up this long: it counts as healthy and the backoff starts over. */
export const HEALTHY_MS = 20_000
/** After this many quick deaths in a row, stop respawning for the rest of the run (a crash loop helps nobody). */
export const GIVE_UP_AFTER = 8

export function backoffMs(failures: number): number {
  return BACKOFF_MS[Math.min(Math.max(failures, 0), BACKOFF_MS.length - 1)]
}

// ---- capture (circle to ask) ------------------------------------------------------------------------------------------
//
//   main -> helper  {"cmd":"capture","id","rect":{x,y,w,h},"displayId","margin"}   /   {"cmd":"capture-release","id"}
//   helper -> main  {"type":"capture","id","path","w","h","pxPerPoint","rect":{x,y,w,h},"displayId","ms"}
//              or   {"type":"capture","id","error","message","ms"}
//
// Kept out of HelperEvent on purpose: a capture answer is a reply to one request, not a push-to-talk state change, so it
// never reaches reducePtt (common/pttState.ts). parseLine drops it; parseCaptureLine reads it.
// rect is global screen points, top-left origin (the contract's ScreenRegion space; displayId = Electron's Display.id).

/** Long edge of the JPEG, in pixels (the helper never goes above it). */
export const MAX_CAPTURE_EDGE = 1092
/** The helper answers in about 50 to 400 ms; past this main gives up and answers 'timeout'. */
export const CAPTURE_TIMEOUT_MS = 2000
/** The circle plus this much on every side (the speed plan's 15%). The answer's rect says what was really captured. */
export const CAPTURE_MARGIN = 0.15
const MAX_PATH = 1024
const MAX_COORD = 100_000

export type CaptureRect = { x: number; y: number; w: number; h: number }
/** The helper's codes, then main's own (no helper running, no answer in time, a request that made no sense). */
export type CaptureErrorCode = 'screen_denied' | 'no_display' | 'bad_rect' | 'unsupported' | 'failed' | 'unavailable' | 'timeout' | 'bad_request' | 'busy'
export const HELPER_CAPTURE_ERRORS: readonly CaptureErrorCode[] = ['screen_denied', 'no_display', 'bad_rect', 'unsupported', 'failed']

/** What the circle feature asks for: a ScreenRegion (its scale is ignored: the helper reads the display's own). */
export type CaptureRequest = CaptureRect & { displayId: number; margin?: number }

export type CaptureOk = {
  ok: true
  id: string
  /** Absolute path of a 0600 JPEG in the helper's private folder. The engine deletes it after reading (action ask
   *  {capture}); the helper deletes it 30 s after writing, on capture-release, or after 8 newer captures. */
  path: string
  /** Pixels. max(w, h) <= MAX_CAPTURE_EDGE. */
  w: number
  h: number
  /** Output pixels per point (w / rect.w). */
  pxPerPoint: number
  /** The box really captured: margin added, clamped to the display, whole points. Map crop pixels back with this. */
  rect: CaptureRect
  displayId: number
  ms: number
}
export type CaptureFail = { ok: false; id: string; error: CaptureErrorCode; message: string; ms?: number }
export type CaptureResult = CaptureOk | CaptureFail

const finiteNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const parseRect = (v: unknown): CaptureRect | undefined => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return undefined
  const r = v as Record<string, unknown>
  if (!finiteNum(r.x) || !finiteNum(r.y) || !finiteNum(r.w) || !finiteNum(r.h) || r.w <= 0 || r.h <= 0) return undefined
  if ([r.x, r.y, r.w, r.h].some((n) => Math.abs(n) > MAX_COORD)) return undefined
  return { x: r.x, y: r.y, w: r.w, h: r.h }
}
/** The helper's own file names only: <...>/cap-<uuid>.jpg, absolute, nothing odd in the path. */
const isCapturePath = (v: unknown): v is string =>
  isStr(v, MAX_PATH) && v.startsWith('/') && !v.includes('/../') && !/[\u0000-\u001f]/.test(v) && /\/cap-[a-z0-9-]{8,64}\.jpg$/.test(v)
const isDim = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 1 && (v as number) <= MAX_CAPTURE_EDGE
const isDisplayId = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= 0xffffffff

/** Parse one stdout line as a capture answer. Anything else (or anything malformed) is undefined. */
export function parseCaptureLine(text: string): CaptureResult | undefined {
  if (typeof text !== 'string' || text.length === 0 || text.length > MAX_LINE) return undefined
  let o: unknown
  try {
    o = JSON.parse(text)
  } catch {
    return undefined
  }
  if (!o || typeof o !== 'object' || Array.isArray(o)) return undefined
  const r = o as Record<string, unknown>
  if (r.type !== 'capture' || !isId(r.id)) return undefined
  const ms = finiteNum(r.ms) && r.ms >= 0 ? r.ms : undefined
  if (r.error !== undefined) {
    if (!oneOf(r.error, HELPER_CAPTURE_ERRORS)) return undefined
    return { ok: false, id: r.id, error: r.error, message: isStr(r.message, 300) ? clean(r.message) : '', ...(ms !== undefined ? { ms } : {}) }
  }
  const rect = parseRect(r.rect)
  if (!isCapturePath(r.path) || !isDim(r.w) || !isDim(r.h) || !rect || !isDisplayId(r.displayId)) return undefined
  if (!finiteNum(r.pxPerPoint) || r.pxPerPoint <= 0 || r.pxPerPoint > 16) return undefined
  return { ok: true, id: r.id, path: r.path, w: r.w, h: r.h, pxPerPoint: r.pxPerPoint, rect, displayId: r.displayId, ms: ms ?? 0 }
}

/**
 * Check a capture request from a renderer (any window can invoke, so it is untrusted). A ScreenRegion passes as is;
 * margin defaults to CAPTURE_MARGIN and is capped at 0.5. undefined = not a request.
 */
export function captureRequest(raw: unknown): CaptureRequest | undefined {
  const rect = parseRect(raw)
  if (!rect) return undefined
  const o = raw as Record<string, unknown>
  if (!isDisplayId(o.displayId)) return undefined
  if (o.margin !== undefined && !finiteNum(o.margin)) return undefined
  const margin = finiteNum(o.margin) ? Math.min(Math.max(o.margin, 0), 0.5) : CAPTURE_MARGIN
  return { ...rect, displayId: o.displayId, margin }
}

export const captureCommand = (id: string, req: CaptureRequest): string =>
  line({ cmd: 'capture', id, rect: { x: req.x, y: req.y, w: req.w, h: req.h }, displayId: req.displayId, margin: req.margin ?? CAPTURE_MARGIN })

/** Delete that capture now: main gave up on it (timeout, a late answer) or the circle no longer needs it. */
export const captureReleaseCommand = (id: string): string => line({ cmd: 'capture-release', id })

/** At most this many captures wait for the helper at once; one more is answered 'busy'. */
export const MAX_PENDING_CAPTURES = 2

/** Whether a new capture may go to the helper now. undefined = yes; else the code to answer with. */
export function captureAdmit(pending: number, helperUp: boolean): 'busy' | 'unavailable' | undefined {
  if (!helperUp) return 'unavailable'
  return pending >= MAX_PENDING_CAPTURES ? 'busy' : undefined
}

/** An id main gave out for a capture (what 'ptt:capture-release' accepts). */
export const isCaptureId = (v: unknown): v is string => isId(v) && /^cap-\d{1,12}$/.test(v)

// Mapping crop pixels back to the screen is the engine's (it reads the model's [DRAW:x,y,r] line):
// screen = (rect.x + px * rect.w / w, rect.y + py * rect.h / h), r_pt = r * rect.w / w, with (px, py) clamped to
// [0, w] x [0, h] first. shared/capture_file.py crop_to_screen does exactly this.
