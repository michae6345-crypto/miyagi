/**
 * Scripted mock engine. Plays a scenario (a set of named segments of timed events)
 * in response to the same commands the real engine receives.
 *
 * Used three ways:
 *   1. `npm run mock`  -> mock/replay.ts serves it on ws://localhost:8787
 *   2. dev:web         -> runs inline in the browser when no server answers
 *   3. DEMO=1          -> runs inside Electron's main process as the demo safety net
 *
 * Scenario format (mock/scenarios/*.json), messages exactly as on the wire ({type, payload}):
 * {
 *   "name": "happy",
 *   "on": { "connect": "intro", "learn": "search", "build_lesson": "step4", "action:apply_fix": "fix" },
 *   "segments": {
 *     "search": [ { "wait": 400, "type": "search.result", "payload": {...} }, { "wait": 200, "goto": "other" } ]
 *   }
 * }
 * `wait` is milliseconds after the previous item. `goto` chains another segment.
 * Triggers: "connect", a command type ("learn", "build_lesson", "learn_url"), "learn:lesson" ("Just teach me",
 * falls back to "learn"), or "action:<kind>". A scenario with "full": false stays out of the merged "full" one.
 */
import type { Incoming, Outgoing } from '../src/common/wire'

export type ScenarioItem = { wait?: number; goto?: string; type?: string; payload?: unknown }

export type Scenario = {
  name: string
  on: Record<string, string>
  segments: Record<string, ScenarioItem[]>
}

export type MockEngine = {
  /** Feed a command from the app. */
  handle(cmd: Outgoing): void
  /** Call once the client is connected (plays the "connect" segment). */
  start(): void
  stop(): void
}

export function createMockEngine(scenario: Scenario, emit: (m: Incoming) => void, log = false): MockEngine {
  let timers: ReturnType<typeof setTimeout>[] = []
  /** Last "stepN" segment played, so triggers like "action:diagram@step6" can depend on it. */
  let current = ''

  const clear = (): void => {
    timers.forEach(clearTimeout)
    timers = []
    current = ''
  }

  const play = (segment: string): void => {
    if (!segment) return
    const items = scenario.segments[segment]
    if (!items) {
      if (log) console.warn(`[mock] no segment "${segment}"`)
      return
    }
    if (segment.startsWith('step')) current = segment
    if (log) console.log(`[mock] ▶ ${segment}`)
    let at = 0
    for (const item of items) {
      at += item.wait ?? 0
      const { goto, type, payload } = item
      timers.push(
        setTimeout(() => {
          if (goto) play(goto)
          else if (type) {
            if (log) console.log(`[mock]   → ${type}`)
            emit({ type, payload: payload ?? {} } as Incoming)
          }
        }, at)
      )
    }
  }

  const trigger = (key: string): void => {
    const seg = scenario.on[`${key}@${current}`] ?? scenario.on[key]
    if (seg) play(seg)
    else if (log) console.log(`[mock] (no trigger for ${key})`)
  }

  return {
    start: () => trigger('connect'),
    stop: clear,
    handle(cmd) {
      // The app streams these continuously; the mock just acknowledges keys like the engine would.
      if (cmd.type === 'overlay.bounds' || cmd.type === 'video.state') return
      if (cmd.type === 'config.keys') {
        const st = (k?: string) => (k ? 'ok' : 'env') as 'ok' | 'env'
        const p = cmd.payload
        emit({ type: 'config.status', payload: { anthropic: st(p.anthropic), gemini: st(p.gemini), brightdata: st(p.brightdata), elevenlabs: st(p.elevenlabs), tigerUrl: st(p.tigerUrl) } })
        return
      }
      if (log) console.log(`[mock] ← ${JSON.stringify(cmd)}`)
      if (cmd.type === 'dev.reset') {
        clear()
        trigger('connect')
        return
      }
      // Like the engine: stop every scripted timer, then lesson.ended + status idle (or the scenario's own 'end_lesson').
      if (cmd.type === 'end_lesson') {
        clear()
        if (scenario.on.end_lesson) return trigger('end_lesson')
        emit({ type: 'lesson.ended', payload: { reason: 'end_lesson' } })
        emit({ type: 'status', payload: { state: 'idle' } })
        return
      }
      if (cmd.type === 'action') trigger(`action:${cmd.payload.kind}`)
      // "Just teach me" (learn {mode:"lesson"}) has its own trigger when a scenario defines one; else it's plain "learn".
      else if (cmd.type === 'learn' && cmd.payload.mode === 'lesson' && scenario.on['learn:lesson']) trigger('learn:lesson')
      else trigger(cmd.type)
    }
  }
}
