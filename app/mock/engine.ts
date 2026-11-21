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
 * Triggers: "connect", a command type ("learn", "build_lesson", "learn_url"), "learn:<mode>" (a learn with that mode,
 * when the scenario has it), or "action:<kind>".
 */
import { V2_COMMANDS, type Incoming, type Outgoing } from '../src/common/wire'

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

/** main/engine.ts LinkInfo: what a `_link` item fakes (the browser stage's feat:engine-link). */
export type MockLink = { open: boolean; attempting: boolean; failures: number }

/**
 * v2 (W0-5):
 *   - `{ "type": "_link", "payload": { "open": false, "attempting": true, "failures": 2 } }` fakes main's engine link
 *     (reconnecting "2 of 5", offline) through `onLink`; it never reaches the app as an engine event. Where nothing
 *     listens (replay.ts, DEMO=1) it's dropped.
 *   - Every other type passes through as-is, the v2 events included (engine.hello, health, blocker, library, ...).
 *   - v2 commands trigger like any other: "health.get", "progress.get", "panel.state"; library.get / library.start try
 *     "<type>:<id>" first ("library.start:nn_intro"), then "<type>".
 *   - Like the v2 engine, the mock says `engine.hello` (every V2_COMMANDS capability) on connect, on dev.reset and when a
 *     `_link` item comes back open, before the scenario's own items. A scenario that sends its own engine.hello later
 *     replaces it (core/lesson.ts keeps the last one), so a scenario can still narrow the capabilities or set `restored`.
 */
export function createMockEngine(scenario: Scenario, emit: (m: Incoming) => void, log = false, onLink?: (l: MockLink) => void): MockEngine {
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
          else if (type === '_link') {
            const l = (payload ?? {}) as Partial<MockLink>
            onLink?.({ open: !!l.open, attempting: !!l.attempting, failures: Number(l.failures) || 0 })
            // A fake reconnect is a new engine as far as the app knows (lesson.ts drops hello on disconnect): say it again.
            if (l.open) hello()
          } else if (type) {
            if (log) console.log(`[mock]   → ${type}`)
            emit({ type, payload: payload ?? {} } as Incoming)
          }
        }, at)
      )
    }
  }

  /** The default v2 hello, so canSend()/useCapability() hold in every scenario, not only the ones that script it. */
  const hello = (): void => emit({ type: 'engine.hello', payload: { version: 'mock', contract: '2026-11-20', capabilities: [...V2_COMMANDS] } })

  const trigger = (key: string): void => {
    const seg = scenario.on[`${key}@${current}`] ?? scenario.on[key]
    if (seg) play(seg)
    else if (log) console.log(`[mock] (no trigger for ${key})`)
  }

  return {
    start: () => {
      hello()
      trigger('connect')
    },
    stop: clear,
    handle(cmd) {
      // The app streams these continuously; the mock just acknowledges keys like the engine would.
      if (cmd.type === 'overlay.bounds' || cmd.type === 'video.state') return
      if (cmd.type === 'config.keys') {
        const st = (k?: string) => (k ? 'ok' : 'env') as 'ok' | 'env'
        const p = cmd.payload
        emit({ type: 'config.status', payload: { anthropic: st(p.anthropic), gemini: st(p.gemini), elevenlabs: st(p.elevenlabs), tigerUrl: st(p.tigerUrl) } })
        return
      }
      if (log) console.log(`[mock] ← ${JSON.stringify(cmd)}`)
      if (cmd.type === 'dev.reset') {
        clear()
        hello()
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
      else if ((cmd.type === 'library.get' || cmd.type === 'library.start') && scenario.on[`${cmd.type}:${cmd.payload.id}`]) trigger(`${cmd.type}:${cmd.payload.id}`)
      // learn {mode}: a scenario can answer "Just teach me" / "Demo" apart from a video search ("learn:lesson", "learn:demo").
      else if (cmd.type === 'learn' && cmd.payload.mode && scenario.on[`learn:${cmd.payload.mode}`]) trigger(`learn:${cmd.payload.mode}`)
      else trigger(cmd.type)
    }
  }
}
