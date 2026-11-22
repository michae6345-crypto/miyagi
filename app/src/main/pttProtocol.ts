/**
 * Push to talk: the JSON-lines protocol with the miyagi-listen helper (miyagi-v2/PUSH-TO-TALK.md). Pure: no electron,
 * no I/O, so the parser, the command builders and the term list are tested offline (test/pttProtocol.test.ts).
 *
 *   helper -> main (stdout): ready, perm, ptt, listening, partial, final, cancelled, error
 *   main -> helper (stdin):  config, context, permissions, cancel, quit
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
