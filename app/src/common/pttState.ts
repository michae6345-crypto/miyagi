/**
 * Push to talk: the one state every window shows, and the pure reducer that turns helper events into it. Main runs it
 * (main/features/ptt.ts) and broadcasts the result as `ptt:state`; the browser stage's mock helper runs the same one.
 *
 *   idle | arming | listening(text) | sending | error(code), plus the current session id.
 *
 * Session bookkeeping (Clicky #142, #130, #35): every hold has an id and every helper event carries it. An event whose
 * id is not the current one is dropped, so a late partial or final from a session that was cancelled can never show
 * or send. A release (ptt up) while the helper is still starting the mic is remembered, so the session still ends
 * (the island never waits on a mic that opens after the key is up). A final is accepted once; its id is then spent.
 */
import type { AssetsState, HelperEvent, InputPerm, MicPerm, PttCancelReason, PttErrorCode, SttKind } from '../main/pttProtocol'

export type PttPhase = 'idle' | 'arming' | 'listening' | 'sending' | 'error'

export type PttPerms = { mic: MicPerm | 'unknown'; input: InputPerm | 'unknown'; assets?: AssetsState }

export type PttState = {
  phase: PttPhase
  /** The current session's id (absent at rest and after the session ended). */
  id?: string
  /** The live partial text while listening (the best text so far while sending). */
  text: string
  /** Why it is in the error phase. */
  code?: PttErrorCode
  /** The key came up while the helper was still starting. */
  released: boolean
  /** The helper is running and said ready. */
  available: boolean
  stt?: SttKind
  perms: PttPerms
  /** Why the last session ended without text (for tests and the stage; nothing is shown for it). */
  lastCancel?: PttCancelReason
}

export const PTT_REST: PttState = { phase: 'idle', text: '', released: false, available: false, perms: { mic: 'unknown', input: 'unknown' } }

/** Events the reducer takes besides the helper's own. */
export type PttInternal =
  | { type: 'exit' } // the helper process ended
  | { type: 'reset' } // hard cap, disconnect, quit: back to rest
  | { type: 'clear-error' }

export type PttInput = HelperEvent | PttInternal

/** What a reduce step produced besides the new state. */
export type PttResult = { state: PttState; final?: { id: string; text: string } }

/** A session is in flight: the island owns itself while true. */
export const active = (s: Pick<PttState, 'phase'>): boolean => s.phase === 'arming' || s.phase === 'listening' || s.phase === 'sending'

const rest = (s: PttState, extra: Partial<PttState> = {}): PttState => ({ ...s, phase: 'idle', id: undefined, text: '', code: undefined, released: false, ...extra })

export function reducePtt(s: PttState, e: PttInput): PttResult {
  switch (e.type) {
    case 'ready':
      return { state: { ...s, available: true, stt: e.stt } }
    case 'perm':
      return { state: { ...s, perms: { mic: e.mic, input: e.input, assets: e.assets ?? s.perms.assets } } }
    case 'exit':
    case 'reset':
      return { state: rest(s, e.type === 'exit' ? { available: false } : {}) }
    case 'clear-error':
      return { state: s.phase === 'error' ? rest(s) : s }
    case 'error': {
      // A permission error is also a fact about the permissions: keep the rows honest. "Never asked" (mic_undetermined)
      // is not "denied": the first shows the Allow card, the second the Open settings one.
      const perms =
        e.code === 'mic_denied' ? { ...s.perms, mic: 'denied' as const } : e.code === 'mic_undetermined' ? { ...s.perms, mic: 'undetermined' as const } : e.code === 'input_denied' ? { ...s.perms, input: 'denied' as const } : s.perms
      // The helper reports a missing Input Monitoring grant or a failed key listener as soon as it is switched on, with
      // no hold in flight. That is a fact about the permissions only (the Settings row and the once-a-run card show it);
      // it must not put the island into an error face or cancel anything.
      if ((e.code === 'input_denied' || e.code === 'tap_failed') && !active(s)) return { state: perms === s.perms ? s : { ...s, perms } }
      return { state: { ...rest(s), phase: 'error', code: e.code, perms } }
    }
    case 'ptt':
      if (e.state === 'down') return { state: { ...rest(s), phase: 'arming', id: e.id, lastCancel: undefined } }
      // up: only for the current session. While arming it is remembered; while listening the wait for the final starts.
      if (e.id !== s.id) return { state: s }
      if (s.phase === 'listening') return { state: { ...s, phase: 'sending', released: true } }
      if (s.phase === 'arming') return { state: { ...s, released: true } }
      return { state: s }
    case 'listening':
      if (e.id !== s.id || s.phase !== 'arming') return { state: s }
      // Opened after the key was already up: nothing to listen to, wait for the final (or the cancel).
      return { state: { ...s, phase: s.released ? 'sending' : 'listening' } }
    case 'partial':
      if (e.id !== s.id || (s.phase !== 'listening' && s.phase !== 'sending' && s.phase !== 'arming')) return { state: s }
      return { state: { ...s, text: e.text } }
    case 'final': {
      if (e.id !== s.id || !active(s)) return { state: s } // stale, or a second final for a spent id
      const state = rest(s)
      return e.text.trim() ? { state, final: { id: e.id, text: e.text.trim() } } : { state: { ...state, lastCancel: 'empty' } }
    }
    case 'cancelled':
      if (e.id !== s.id) return { state: s }
      return { state: rest(s, { lastCancel: e.reason }) }
  }
}
