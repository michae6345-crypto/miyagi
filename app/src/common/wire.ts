/**
 * Wire helpers around shared/contracts/events.ts (Michael's contract is the source of truth).
 * Every message is `{ type, payload }`, both directions.
 */
import type { AppCommands, AppMessage, EngineEvents, EngineMessage, KeyStatusEvent } from '../../../shared/contracts/events'

export type { AppMessage, EngineEvents, EngineMessage }

/** config.status lives in its own interface in the contract; fold it into what the app can receive. */
export type ConfigStatus = { type: 'config.status'; payload: KeyStatusEvent['config.status'] }
export type Incoming = EngineMessage | ConfigStatus

/** Dev-only: the mock replay restarts its scenario. The real engine ignores it. */
export type DevReset = { type: 'dev.reset'; payload: Record<string, never> }

export type Outgoing = AppMessage | DevReset

/** Typed command builder: cmd('learn', { query }) */
export function cmd<K extends keyof AppCommands>(type: K, payload: AppCommands[K]): AppMessage {
  return { type, payload } as AppMessage
}

export const devReset: DevReset = { type: 'dev.reset', payload: {} }

const KNOWN = new Set<string>([
  'search.result',
  'search.done',
  'lesson.building',
  'lesson.ready',
  'lesson.updated',
  'lesson.ended',
  'step.started',
  'check.updated',
  'step.passed',
  'offtrack',
  'spotlight',
  'video.seek',
  'video.pause',
  'video.play',
  'card',
  'diagram',
  'speak',
  'metric',
  'status',
  'error',
  'screen.seen',
  'setup.progress',
  'config.status'
] satisfies (keyof EngineEvents | 'config.status')[])

/** Parse one WebSocket frame. Accepts `{type, payload}` (contract) and, leniently, flat `{type, ...fields}`. */
export function parseEngineMessage(raw: unknown): Incoming | null {
  let m: unknown = raw
  if (typeof raw === 'string') {
    try {
      m = JSON.parse(raw)
    } catch {
      return null
    }
  }
  if (!m || typeof m !== 'object') return null
  const { type, payload, ...rest } = m as { type?: unknown; payload?: unknown }
  if (typeof type !== 'string' || !KNOWN.has(type)) return null
  return { type, payload: payload && typeof payload === 'object' ? payload : rest } as Incoming
}

/** Payload type for one event, e.g. Payload<'offtrack'>. */
export type Payload<K extends keyof EngineEvents> = EngineEvents[K]
