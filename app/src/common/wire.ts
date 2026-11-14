/**
 * Wire helpers around shared/contracts/events.ts (Michael's contract is the source of truth).
 * Every message is `{ type, payload }`, both directions.
 */
import type { AppCommands, AppMessage, EngineEvents, EngineMessage } from '../../../shared/contracts/events'

export type { AppMessage, EngineEvents, EngineMessage }

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
  'error'
] satisfies (keyof EngineEvents)[])

/** Parse one WebSocket frame. Accepts `{type, payload}` (contract) and, leniently, flat `{type, ...fields}`. */
export function parseEngineMessage(raw: unknown): EngineMessage | null {
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
  return { type, payload: payload && typeof payload === 'object' ? payload : rest } as EngineMessage
}

/** Payload type for one event, e.g. Payload<'offtrack'>. */
export type Payload<K extends keyof EngineEvents> = EngineEvents[K]
