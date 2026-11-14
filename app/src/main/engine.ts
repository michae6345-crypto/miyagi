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
type StatusListener = (connected: boolean) => void

export class EngineLink {
  /** Every event since the last learn/build, replayed to a window that reloads. */
  readonly log: Incoming[] = []
  connected = false
  private ws?: WebSocket
  private demo?: MockEngine
  private queue: string[] = []
  private listeners = new Set<Listener>()
  private statusListeners = new Set<StatusListener>()
  private openHooks = new Set<() => void>()
  private retry = 500
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

  send(cmd: Outgoing): void {
    if (cmd.type === 'learn' || cmd.type === 'learn_url' || cmd.type === 'dev.reset') this.log.length = 0
    if (cmd.type === 'overlay.bounds') this.lastBounds = cmd
    if (this.demo) return this.demo.handle(cmd)
    const msg = JSON.stringify(cmd)
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(msg)
    else this.queue.push(msg)
  }

  private connect(): void {
    const ws = new WebSocket(this.url)
    this.ws = ws
    ws.on('open', () => {
      this.retry = 500
      this.setConnected(true)
      for (const fn of this.openHooks) fn()
      if (this.lastBounds) ws.send(JSON.stringify(this.lastBounds))
      for (const m of this.queue.splice(0)) ws.send(m)
    })
    ws.on('message', (data) => {
      const e = parseEngineMessage(String(data))
      if (e) this.dispatch(e)
    })
    ws.on('close', () => {
      this.setConnected(false)
      setTimeout(() => this.connect(), this.retry)
      this.retry = Math.min(this.retry * 2, 4000)
    })
    ws.on('error', () => {
      /* 'close' follows and schedules the retry */
    })
  }

  private dispatch(e: Incoming): void {
    if (e.type === 'lesson.ready') this.log.splice(0, this.log.length, ...this.log.filter((x) => x.type.startsWith('search')))
    this.log.push(e)
    for (const l of this.listeners) l(e)
  }

  private setConnected(c: boolean): void {
    this.connected = c
    for (const l of this.statusListeners) l(c)
  }
}
