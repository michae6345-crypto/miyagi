/**
 * One bridge API for both runtimes:
 *   - Electron: window.tut from the preload (IPC to main, which owns the engine socket).
 *   - Browser (npm run dev:web): a local bus that mimics main's routing, plus a direct
 *     WebSocket to ENGINE_URL. If nothing answers, the mock engine runs inline.
 *
 * Browser: the mock runs INLINE by default (so parallel agents never share a mock server).
 * Query params: ?engine=socket (ws://localhost:8787) or ?engine=ws://host:port · ?scenario=<name> · ?os=win
 *   · &fallback=0 with a socket engine: never fall back to the inline mock, keep retrying like main does (to see the
 *     pill's "Can't reach miyagi · Retry" and the reconnect: start `PORT=<port> npm run mock` later)
 */
import { parseEngineMessage, type Incoming, type Outgoing } from '../../common/wire'
import { describePlatform } from '../../main/platform'
import type { Layout, TutBridge, UiSignal, Unsub } from '../../preload/api'
import { createMockEngine, type MockEngine } from '../../../mock/engine'
import { scenarios } from '../../../mock/scenarios'

export type EngineMode = 'electron' | 'socket' | 'inline'

type Cb = (payload?: unknown) => void

/** Browser-stage stand-ins for main-process feature handlers (e.g. settings → localStorage). */
const webHandlers = new Map<string, (...args: unknown[]) => unknown>()
export function registerWebHandler(channel: string, fn: (...args: unknown[]) => unknown): void {
  webHandlers.set(channel, fn)
}

/** The fake desktop in the browser stage is the 1600×1000 mockup; the Mac menu bar is 32px. */
export const STAGE: Layout = { origin: { x: 0, y: 0 }, width: 1600, height: 1000, workArea: { x: 0, y: 32, width: 1600, height: 968 } }

function createWebBridge(): TutBridge & { mode: () => EngineMode } {
  const params = new URLSearchParams(location.search)
  const platform = describePlatform(params.get('os') === 'win' ? 'win32' : 'darwin')
  const bus = new Map<string, Set<Cb>>()
  const fire = (name: string, payload?: unknown): void => bus.get(name)?.forEach((cb) => cb(payload))
  const sub = (name: string, cb: Cb): Unsub => {
    if (!bus.has(name)) bus.set(name, new Set())
    bus.get(name)!.add(cb)
    return () => bus.get(name)!.delete(cb)
  }

  let mode: EngineMode = 'socket'
  let ws: WebSocket | undefined
  let inline: MockEngine | undefined
  let everConnected = false
  const queue: string[] = []
  const log: Incoming[] = []

  const dispatch = (e: Incoming): void => {
    log.push(e)
    fire('engine:event', e)
  }
  const setStatus = (c: boolean): void => fire('engine:status', c)

  const startInline = (): void => {
    if (inline) return
    mode = 'inline'
    const name = params.get('scenario') ?? 'full'
    inline = createMockEngine(scenarios[name] ?? scenarios.full, dispatch, true)
    if (!scenarios[name]) console.warn(`[tut] no scenario "${name}"; have: ${Object.keys(scenarios).join(', ')}`)
    console.info(`[tut] no engine answered: running the "${name}" mock inline`)
    setStatus(true)
    fire('feat:engine-link', { open: true, attempting: false, failures: 0 })
    inline.start()
    for (const m of queue.splice(0)) inline.handle(JSON.parse(m))
  }

  // The engine link as main reports it (main/engine.ts LinkInfo, review A16), same retry timing: every 1 s for the first
  // 30 s of an outage (or after Retry), then backing off to every 5 s.
  const fallback = params.get('fallback') !== '0'
  let failures = 0
  let downSince = Date.now()
  let slow = 0
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  const link = (): { open: boolean; attempting: boolean; failures: number } =>
    inline ? { open: true, attempting: false, failures: 0 } : { open: ws?.readyState === WebSocket.OPEN, attempting: ws?.readyState === WebSocket.CONNECTING, failures }
  const emitLink = (): void => fire('feat:engine-link', link())
  const schedule = (): void => {
    clearTimeout(retryTimer)
    const fast = Date.now() - downSince < 30_000
    retryTimer = setTimeout(connect, fast ? 1000 : (slow = Math.min(5000, slow ? slow * 2 : 2000)))
    emitLink()
  }

  const connect = (): void => {
    clearTimeout(retryTimer)
    const url = params.get('engine')?.startsWith('ws://') ? params.get('engine')! : 'ws://localhost:8787'
    const sock = new WebSocket(url)
    ws = sock
    let opened = false
    // No engine at first: the inline mock (default). Otherwise the same timer is main's handshake timeout.
    const first = fallback && !everConnected
    const giveUp = setTimeout(() => !opened && (sock.close(), first && startInline()), first ? 900 : 4000)
    sock.onopen = () => {
      clearTimeout(giveUp)
      if (ws !== sock) return sock.close()
      opened = true
      everConnected = true
      failures = 0
      slow = 0
      mode = 'socket'
      setStatus(true)
      emitLink()
      for (const m of queue.splice(0)) sock.send(m)
    }
    sock.onmessage = (m) => {
      const e = parseEngineMessage(String(m.data))
      if (e) dispatch(e)
    }
    sock.onclose = () => {
      clearTimeout(giveUp)
      if (ws !== sock || inline) return
      if (!everConnected && fallback) return startInline()
      if (opened) {
        downSince = Date.now()
        slow = 0
      } else failures++
      setStatus(false)
      schedule()
    }
    emitLink()
  }
  // The pill's Retry, and every window on load (main/features/pill.ts): try now, fast retries again.
  webHandlers.set('engine-link:retry', () => {
    if (!inline && ws?.readyState !== WebSocket.OPEN) {
      downSince = Date.now()
      slow = 0
      if (ws?.readyState !== WebSocket.CONNECTING) connect()
    }
    return link()
  })

  const engineParam = params.get('engine')
  if (engineParam === 'socket' || engineParam?.startsWith('ws://')) connect()
  else startInline()

  let launcherOpen = false
  let islandSize = { w: 300, h: 34 }

  return {
    platform,
    mode: () => mode,
    onEvent: (cb) => sub('engine:event', cb as Cb),
    onStatus: (cb) => sub('engine:status', cb as Cb),
    send(cmd: Outgoing) {
      if (cmd.type === 'dev.reset') log.length = 0
      if (inline) return inline.handle(cmd)
      const msg = JSON.stringify(cmd)
      if (ws?.readyState === WebSocket.OPEN) ws.send(msg)
      else queue.push(msg)
    },
    ready() {
      setTimeout(() => {
        fire('ui:layout', STAGE)
        setStatus(mode === 'inline' || ws?.readyState === WebSocket.OPEN)
      })
    },
    on: (signal, cb) => sub(`ui:${signal}`, cb),
    emit(signal: UiSignal, payload?: unknown) {
      // Mirror of main/index.ts routing.
      switch (signal) {
        case 'island:size':
          islandSize = payload as typeof islandSize
          break
        case 'island:yield':
        case 'island:return':
          fire(`ui:${signal}`, payload)
          break
        case 'launcher:toggle':
          launcherOpen = !launcherOpen
          // One bus in the browser: the launcher opens from the island's shape and the island hides.
          fire(launcherOpen ? 'ui:launcher:open' : 'ui:launcher:close', launcherOpen ? { from: islandSize } : undefined)
          break
        case 'launcher:hidden':
          launcherOpen = false
          fire('ui:launcher:closed')
          break
        case 'launcher:built':
          launcherOpen = false
          fire('ui:pill:receive')
          fire('ui:launcher:closed')
          break
        case 'shortcut':
          fire('ui:shortcut', payload)
          break
      }
    },
    async invoke<T>(channel: string, ...args: unknown[]): Promise<T> {
      const fn = webHandlers.get(channel)
      if (!fn) throw new Error(`[tut] no web handler for "${channel}" (registerWebHandler in the feature)`)
      return (await fn(...args)) as T
    },
    onFeature: (channel, cb) => sub(`feat:${channel}`, cb)
  }
}

const web = window.tut ? undefined : createWebBridge()

export const bridge: TutBridge = window.tut ?? web!

export const engineMode = (): EngineMode => (web ? web.mode() : 'electron')

export const isElectron = !!window.tut
