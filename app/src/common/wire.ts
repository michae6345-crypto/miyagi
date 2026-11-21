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
  'config.status',
  // Michael's VS Code quick-pick rects (desktop test 9, A3 / A4; core/islandPlace.ts)
  'screen.avoid',
  // v2 (BUILD-PLAN W0-1): all optional; a feature that doesn't subscribe never sees them
  'engine.hello',
  'health',
  'lesson.paused',
  'lesson.resumed',
  'blocker',
  'library',
  'library.item',
  'progress'
] satisfies (keyof EngineEvents | 'config.status')[])

/**
 * v2 commands the app may send only when the engine listed them in engine.hello.capabilities (core/lesson.ts
 * `canSend`). An older engine would answer them with an error, so they are never sent blind.
 */
export const V2_COMMANDS = ['health.get', 'permission.open', 'library.list', 'library.get', 'library.start', 'progress.get', 'panel.state'] as const satisfies readonly (keyof AppCommands)[]
export type V2Command = (typeof V2_COMMANDS)[number]

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
