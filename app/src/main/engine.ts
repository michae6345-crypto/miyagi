/**
 * The one connection to the engine. Main owns it and relays events to every window,
 * so the real engine only ever sees a single client.
 *
 *   ENGINE_URL=ws://localhost:8787 (default)  -> mock replay or the real engine, same contract
 *   DEMO=1                                     -> no network: the scripted run plays in-process
 */
import WebSocket from 'ws'
import { parseEngineMessage, V2_COMMANDS, type Incoming, type Outgoing } from '../common/wire'
import { createMockEngine, type MockEngine } from '../../mock/engine'
import { scenarios } from '../../mock/scenarios'
import { RunGuard } from './freshStart'

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

/** The header that carries the per-launch engine token (W0-5; the engine checks it in E2 when MIYAGI_ENGINE_TOKEN is set). */
export const TOKEN_HEADER = 'X-Miyagi-Token'
const V2 = new Set<string>(V2_COMMANDS)
/** The anonymous install token for the hosted proxy (main/features/cloud.ts): folded into config.keys, nowhere else.
 * miyagiCloud is the proxy's API root `https://<host>/v1` (cloudApiRoot), the form the engine's server/config.py uses. */
export type CloudKeys = { miyagiToken: string; miyagiCloud: string }
/** This Mac (the same test as localEngine.ts `local`). */
const LOOPBACK = /^wss?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?\/?$/i
/**
 * May secrets travel to this ENGINE_URL? Only to this Mac or over TLS: the engine token and the install token (which
 * can spend money at the proxy) must never cross the network in cleartext ws://.
 */
export function secureEngineUrl(url: string): boolean {
  return LOOPBACK.test(url) || /^wss:\/\//i.test(url)
}

export class EngineLink {
  /** Every event since the last learn/build, replayed to a window that reloads. */
  readonly log: Incoming[] = []
  connected = false
  private ws?: WebSocket
  private demo?: MockEngine
  private listeners = new Set<Listener>()
  private statusListeners = new Set<StatusListener>()
  private openHooks = new Set<() => void>()
  /** cloud.token_invalid hooks (features/cloud.ts): main only, never relayed to a window. */
  private cloudInvalidHooks = new Set<() => void>()
  private linkListeners = new Set<LinkListener>()
  /** When this outage began (or Retry / a window load restarted the fast retries): drives FAST_WINDOW_MS. */
  private downSince = Date.now()
  /** The current slow-retry delay, past the fast window (0 = not backing off yet). */
  private slow = 0
  private failures = 0
  private timer?: ReturnType<typeof setTimeout>
  /** Re-sent on reconnect so the engine's OCR keeps ignoring our UI. */
  private lastBounds?: Outgoing
  /** v2: the per-launch engine token (main/localEngine.ts), sent as a header on every connect. Memory only. */
  private token?: string
  /** v2: the install token + proxy URL, folded into every config.keys (never sent on its own: see send()). */
  private cloud?: CloudKeys
  /** v2: what the engine said it understands (engine.hello.capabilities); reset on every connect. */
  private caps = new Set<string>()
  /** v2: the last config.keys the settings feature sent (the full payload), so a later token can ride on it. */
  private lastKeys?: Extract<Outgoing, { type: 'config.keys' }>
  /** v2: ENGINE_URL is loopback or wss: (secureEngineUrl). Otherwise no token header and no install token, ever. */
  private readonly secure: boolean
  private warnedInsecure = false
  /** Fresh start (main/freshStart.ts): only a lesson started or chosen in this app run reaches the windows. */
  private readonly run: RunGuard

  /**
   * `token` (v2): the per-launch engine token (localEngine ENGINE_TOKEN). Given here, not later, because the first
   * WebSocket attempt starts inside this constructor and must already carry X-Miyagi-Token.
   */
  constructor(private url: string, demoScenario?: string, token?: string) {
    this.token = token || undefined
    this.secure = secureEngineUrl(url)
    this.run = new RunGuard(!!demoScenario)
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

  /**
   * v2 (W0-5): the per-launch token the app passed to the engine it started (env MIYAGI_ENGINE_TOKEN). Sent as the
   * X-Miyagi-Token header from the next connect on; an engine started elsewhere without a token ignores it.
   */
  setToken(token: string | undefined): void {
    this.token = token || undefined
  }

  /** v2: the anonymous install token for the proxy. Every later config.keys carries it (memory only, never logged). */
  setCloud(keys: CloudKeys | undefined): void {
    this.cloud = keys
    // Minted after the settings feature already sent this connect's keys: send the same full payload again, now
    // with the token (only ever the full payload, so nothing the learner saved is cleared).
    if (this.lastKeys && this.connected) this.send(this.lastKeys)
  }

  /**
   * Install token self-heal: the engine says the proxy does not know the install token it was given (a 401,
   * `cloud.token_invalid`). Only while this link holds a token it may send (setCloud + a secure URL); the event carries
   * no token. features/cloud.ts mints a new one (with its own backoff) and hands it back through setCloud.
   */
  onCloudTokenInvalid(fn: () => void): void {
    this.cloudInvalidHooks.add(fn)
  }

  /** v2: did the engine list this command type in engine.hello.capabilities? */
  can(type: string): boolean {
    return this.caps.has(type)
  }

  send(cmd: Outgoing): void {
    if (cmd.type === 'learn' || cmd.type === 'learn_url' || cmd.type === 'dev.reset') this.log.length = 0
    if (cmd.type === 'overlay.bounds') this.lastBounds = cmd
    // v2 commands only to an engine that announced them (an older engine answers an unknown type with an error).
    if (V2.has(cmd.type) && !this.demo && !this.caps.has(cmd.type)) return
    // The install token rides along with the BYOK keys the settings feature sends: a separate config.keys would
    // clear them (the engine's set_app_keys drops names that are missing). A BYOK key the learner set still wins
    // engine side for its provider.
    if (cmd.type === 'config.keys') {
      this.lastKeys = cmd
      if (this.cloud && this.allowSecrets()) cmd = { ...cmd, payload: { ...cmd.payload, ...this.cloud } }
    }
    // Fresh start: a lesson this run starts or chooses (learn, library.start, Continue) may reach the windows, but
    // only once the command really leaves (one dropped offline must not admit the next connect's old snapshot).
    if (this.demo) {
      this.run.command(cmd)
      return this.demo.handle(cmd)
    }
    const msg = JSON.stringify(cmd)
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.run.command(cmd)
      return this.ws.send(msg)
    }
    // Offline (audit P1-3): never queue a learner command and replay it stale on reconnect (a build_lesson
    // whose resultIds a restarted engine doesn't know). Fail it visibly instead. overlay.bounds is re-sent
    // from lastBounds and config.keys from the onOpen hooks, so nothing else needs remembering.
    if (OFFLINE_FAILS.has(cmd.type)) this.notify({ type: 'error', payload: { message: 'miyagi is offline. Start the engine, then try again.' } })
  }

  /** To every window, but not into the replay log (a reloaded window must not see a stale error). */
  private notify(e: Incoming): void {
    for (const l of this.listeners) l(e)
  }

  /** A `cloud.token_invalid` frame: run the hooks (main only: not logged, not relayed, not replayed). */
  private cloudTokenInvalid(text: string): boolean {
    if (!text.includes('cloud.token_invalid')) return false
    try {
      if ((JSON.parse(text) as { type?: unknown })?.type !== 'cloud.token_invalid') return false
    } catch {
      return false
    }
    if (this.cloud && this.secure) for (const fn of this.cloudInvalidHooks) fn()
    return true
  }

  /**
   * Secrets (the engine token header, the install token in config.keys) only to a loopback or wss: engine. Warns once
   * when one is held back, naming neither the value nor the URL's credentials.
   */
  private allowSecrets(): boolean {
    if (this.secure) return true
    if (!this.warnedInsecure) {
      this.warnedInsecure = true
      console.warn('[engine] ENGINE_URL is neither this Mac nor wss:, so the engine token and install token are not sent')
    }
    return false
  }

  private connect(): void {
    clearTimeout(this.timer)
    this.timer = undefined
    let ws: WebSocket
    const header = this.token && this.allowSecrets() ? { headers: { [TOKEN_HEADER]: this.token } } : {}
    try {
      ws = new WebSocket(this.url, { handshakeTimeout: HANDSHAKE_TIMEOUT_MS, ...header })
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
      this.caps.clear()
      // Fresh start: a start that went out on the old socket is lost (the learner retries); only the run's lesson replays.
      this.run.connected()
      this.setConnected(true)
      for (const fn of this.openHooks) fn()
      if (this.lastBounds) ws.send(JSON.stringify(this.lastBounds))
    })
    ws.on('message', (data) => {
      if (this.ws !== ws) return
      const text = String(data)
      if (this.cloudTokenInvalid(text)) return
      const e = parseEngineMessage(text)
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
    if (e.type === 'engine.hello') this.caps = new Set(Array.isArray(e.payload.capabilities) ? e.payload.capabilities.filter((c) => typeof c === 'string') : [])
    // speak.audioUrl is relative (/tts/<hash>.mp3): make it absolute against the engine's http origin once,
    // here, so every window can play it (audit P1-1).
    if (e.type === 'speak' && e.payload.audioUrl && !/^(https?:|data:|blob:)/.test(e.payload.audioUrl)) {
      e = { ...e, payload: { ...e.payload, audioUrl: new URL(e.payload.audioUrl, this.url.replace(/^ws/, 'http')).href } }
    }
    // A lesson this run never started (the engine's snapshot of an old one): not relayed, not logged, not replayed.
    if (!this.run.admit(e)) return
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
