/**
 * The one connection to the engine. Main owns it and relays events to every window,
 * so the real engine only ever sees a single client.
 *
 *   ENGINE_URL=ws://localhost:8787 (default)  -> mock replay or the real engine, same contract
 *   DEMO=1                                     -> no network: the scripted run plays in-process
 */
import WebSocket from 'ws'
import { parseEngineMessage, type Incoming, type Outgoing } from '../common/wire'
import { createMockEngine, type MockEngine } from '../../mock/engine'
import { scenarios } from '../../mock/scenarios'

type Listener = (m: Incoming) => void

/** Learner commands that fail visibly while offline instead of being queued. */
const OFFLINE_FAILS = new Set<string>(['learn', 'learn_url', 'build_lesson', 'action', 'end_lesson'])
type StatusListener = (connected: boolean) => void

/**
 * Reconnect timing (Michael's review A16: the pill said "Offline" for ~10 s after an engine reload while the engine
 * was already answering, because the backoff had reached 4 s). For the first FAST_WINDOW_MS of an outage (and after a
 * window loads or the learner presses Retry) try every FAST_RETRY_MS, so a restarted engine is picked up within about
 * a second; after that back off (2 s, 4 s, then every SLOW_RETRY_MAX_MS) so a stopped engine isn't hammered.
 */
export const FAST_RETRY_MS = 1000
export const FAST_WINDOW_MS = 30_000
export const SLOW_RETRY_MAX_MS = 5000
/** An attempt the engine never answers (busy at startup, a half-open port) fails after this, so the next one can start. */
export const HANDSHAKE_TIMEOUT_MS = 4000

/**
 * Where the socket is, for the pill (review A16: never say "can't reach" before an attempt has actually failed).
 * failures: attempts that failed since the link was last open; 0 while the first attempt (startup, right after a
 * drop) is still in flight.
 */
export type LinkInfo = { open: boolean; attempting: boolean; failures: number }
type LinkListener = (l: LinkInfo) => void

export class EngineLink {
  /** Every event since the last learn/build, replayed to a window that reloads. */
  readonly log: Incoming[] = []
  connected = false
  private ws?: WebSocket
  private demo?: MockEngine
  private listeners = new Set<Listener>()
  private statusListeners = new Set<StatusListener>()
  private openHooks = new Set<() => void>()
  private linkListeners = new Set<LinkListener>()
  /** When this outage began (or Retry / a window load restarted the fast retries): drives FAST_WINDOW_MS. */
  private downSince = Date.now()
  /** The current slow-retry delay, past the fast window (0 = not backing off yet). */
  private slow = 0
  private failures = 0
  private timer?: ReturnType<typeof setTimeout>
  /** Re-sent on reconnect so the engine's OCR keeps ignoring our UI. */
  private lastBounds?: Outgoing

  constructor(private url: string, demoScenario?: string) {
    if (demoScenario) {
      const scenario = scenarios[demoScenario] ?? scenarios.full
      this.demo = createMockEngine(scenario, (e) => this.dispatch(e))
      this.setConnected(true)
      this.demo.start()
    } else {
      this.connect()
    }
  }

  onEvent(l: Listener): void {
    this.listeners.add(l)
  }

  onStatus(l: StatusListener): void {
    this.statusListeners.add(l)
  }

  /** Runs on every (re)connect, before queued messages flush. E.g. settings sends config.keys here. */
  onOpen(fn: () => void): void {
    this.openHooks.add(fn)
    if (this.connected) fn()
  }

  onLink(l: LinkListener): void {
    this.linkListeners.add(l)
  }

  link(): LinkInfo {
    return { open: this.connected, attempting: !this.demo && this.ws?.readyState === WebSocket.CONNECTING, failures: this.demo ? 0 : this.failures }
  }

  /**
   * Try now, and go back to the fast retries: the pill's Retry, or a window that just loaded (review A16: "connect as
   * soon as the renderer loads"). Nothing to do when open, in DEMO, or while an attempt is already in flight.
   */
  reconnect(): void {
    if (this.demo || this.connected) return
    this.downSince = Date.now()
    this.slow = 0
    if (this.ws?.readyState === WebSocket.CONNECTING) return
    this.connect()
  }

  send(cmd: Outgoing): void {
    if (cmd.type === 'learn' || cmd.type === 'learn_url' || cmd.type === 'dev.reset') this.log.length = 0
    if (cmd.type === 'overlay.bounds') this.lastBounds = cmd
    if (this.demo) return this.demo.handle(cmd)
    const msg = JSON.stringify(cmd)
    if (this.ws?.readyState === WebSocket.OPEN) return this.ws.send(msg)
    // Offline (audit P1-3): never queue a learner command and replay it stale on reconnect (a build_lesson
    // whose resultIds a restarted engine doesn't know). Fail it visibly instead. overlay.bounds is re-sent
    // from lastBounds and config.keys from the onOpen hooks, so nothing else needs remembering.
    if (OFFLINE_FAILS.has(cmd.type)) this.notify({ type: 'error', payload: { message: 'miyagi is offline. Start the engine, then try again.' } })
  }

  /** To every window, but not into the replay log (a reloaded window must not see a stale error). */
  private notify(e: Incoming): void {
    for (const l of this.listeners) l(e)
  }

  private connect(): void {
    clearTimeout(this.timer)
    this.timer = undefined
    let ws: WebSocket
    try {
      ws = new WebSocket(this.url, { handshakeTimeout: HANDSHAKE_TIMEOUT_MS })
    } catch {
      // A malformed ENGINE_URL: count it as a failed attempt and keep the retry loop (never throw out of main).
      this.failures++
      return this.schedule()
    }
    this.ws = ws
    let opened = false
    ws.on('open', () => {
      if (this.ws !== ws) return ws.close()
      opened = true
      this.failures = 0
      this.slow = 0
      // The engine sends a full snapshot on every connect: forget what the old connection said.
      this.log.length = 0
      this.setConnected(true)
      for (const fn of this.openHooks) fn()
      if (this.lastBounds) ws.send(JSON.stringify(this.lastBounds))
    })
    ws.on('message', (data) => {
      if (this.ws !== ws) return
      const e = parseEngineMessage(String(data))
      if (e) this.dispatch(e)
    })
    ws.on('close', () => {
      // A newer attempt (Retry) took over: this socket's end means nothing.
      if (this.ws !== ws) return
      if (opened) {
        // A drop: a fresh outage, so fast retries again. Not a failed attempt yet (the pill waits for one).
        this.downSince = Date.now()
        this.slow = 0
      } else this.failures++
      this.setConnected(false)
      this.schedule()
    })
    ws.on('error', () => {
      /* 'close' follows and schedules the retry */
    })
    this.emitLink()
  }

  /** The next attempt: every FAST_RETRY_MS early in an outage, then backing off to SLOW_RETRY_MAX_MS. */
  private schedule(): void {
    clearTimeout(this.timer)
    const fast = Date.now() - this.downSince < FAST_WINDOW_MS
    const delay = fast ? FAST_RETRY_MS : (this.slow = Math.min(SLOW_RETRY_MAX_MS, this.slow ? this.slow * 2 : 2000))
    this.timer = setTimeout(() => this.connect(), delay)
    this.emitLink()
  }

  private lastLink = ''
  private emitLink(): void {
    const l = this.link()
    const key = `${l.open}${l.attempting}${l.failures}`
    if (key === this.lastLink) return
    this.lastLink = key
    for (const fn of this.linkListeners) fn(l)
  }

  private dispatch(e: Incoming): void {
    // speak.audioUrl is relative (/tts/<hash>.mp3): make it absolute against the engine's http origin once,
    // here, so every window can play it (audit P1-1).
    if (e.type === 'speak' && e.payload.audioUrl && !/^(https?:|data:|blob:)/.test(e.payload.audioUrl)) {
      e = { ...e, payload: { ...e.payload, audioUrl: new URL(e.payload.audioUrl, this.url.replace(/^ws/, 'http')).href } }
    }
    if (e.type === 'lesson.ready') this.log.splice(0, this.log.length, ...this.log.filter((x) => x.type.startsWith('search')))
    // An ended lesson must not be replayed into a window that (re)loads: keep only the search rows.
    if (e.type === 'lesson.ended') this.log.splice(0, this.log.length, ...this.log.filter((x) => x.type.startsWith('search')))
    this.log.push(e)
    for (const l of this.listeners) l(e)
  }

  private setConnected(c: boolean): void {
    this.connected = c
    for (const l of this.statusListeners) l(c)
    this.emitLink()
  }
}
