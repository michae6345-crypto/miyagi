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

/**
 * The fake desktop in the browser stage is the 1600×1000 mockup; the Mac menu bar is 32px. v2 (W0-4): ?size=1440x900
 * sets another stage size (the v2 mockups are 1440×900), 640 to 3840 by 400 to 2400.
 */
function stageSize(): { width: number; height: number } {
  const m = typeof location !== 'undefined' ? /^(\d{3,4})x(\d{3,4})$/.exec(new URLSearchParams(location.search).get('size') ?? '') : null
  const w = m ? Number(m[1]) : 1600
  const h = m ? Number(m[2]) : 1000
  return w >= 640 && w <= 3840 && h >= 400 && h <= 2400 ? { width: w, height: h } : { width: 1600, height: 1000 }
}
const SIZE = stageSize()
export const STAGE: Layout = { origin: { x: 0, y: 0 }, width: SIZE.width, height: SIZE.height, workArea: { x: 0, y: 32, width: SIZE.width, height: SIZE.height - 32 } }

/** The engine link as main reports it (main/engine.ts LinkInfo). */
type LinkInfo = { open: boolean; attempting: boolean; failures: number }

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
  /** v2 (W0-5): a scenario's `_link` items fake main's engine link (reconnecting, N failures, offline). */
  let fakeLink: LinkInfo | undefined
  const onFakeLink = (l: LinkInfo): void => {
    fakeLink = l.open ? undefined : l
    setStatus(!!l.open)
    fire('feat:engine-link', l)
  }

  const startInline = (): void => {
    if (inline) return
    mode = 'inline'
    const name = params.get('scenario') ?? 'full'
    inline = createMockEngine(scenarios[name] ?? scenarios.full, dispatch, true, onFakeLink)
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
  const link = (): LinkInfo =>
    inline ? (fakeLink ?? { open: true, attempting: false, failures: 0 }) : { open: ws?.readyState === WebSocket.OPEN, attempting: ws?.readyState === WebSocket.CONNECTING, failures }
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

  // ---- v2 stand-ins for main's core handlers (W0-4 / W0-5) -------------------------------------------------------
  // App windows (main/appWindows.ts): the stage shows them over the desktop (dev/Stage.tsx listens to window:stage).
  const appArgs = new Map<string, unknown>()
  const appOpen = new Set<string>()
  const APP_ROUTES = new Set(['onboarding', 'library', 'progress', 'account', 'auth'])
  webHandlers.set('window:open', (route, args) => {
    if (typeof route !== 'string' || !APP_ROUTES.has(route)) return false
    appArgs.set(route, args ?? null)
    appOpen.add(route)
    fire('feat:window:stage', { route, open: true })
    fire('feat:window:args', { route, args: args ?? undefined })
    return true
  })
  webHandlers.set('window:close', (route) => {
    const r = typeof route === 'string' ? route : [...appOpen].pop()
    if (!r || !appOpen.delete(r)) return false
    fire('feat:window:stage', { route: r, open: false })
    return true
  })
  webHandlers.set('window:focus', (route) => typeof route === 'string' && appOpen.has(route))
  webHandlers.set('window:args', (route) => (typeof route === 'string' ? (appArgs.get(route) ?? null) : null))
  /** Stage only: the app windows open right now (dev/Stage.tsx). */
  webHandlers.set('window:stage-list', () => [...appOpen])
  // ?window=<route> opens one on load (with ?id=<lesson> for the library's detail, ?view=<v> for the account sheet).
  const startWindow = params.get('window')
  if (startWindow && APP_ROUTES.has(startWindow)) {
    const args: Record<string, string> = {}
    for (const k of ['id', 'view', 'section']) if (params.get(k)) args[k] = params.get(k)!
    appArgs.set(startWindow, Object.keys(args).length ? args : null)
    appOpen.add(startWindow)
  }

  // Permissions (main/permissions.ts): all granted, or ?perm=<kind>-off (accessibility-off, screen-off, ...) and
  // ?perm=external (an engine started in Terminal: unknown).
  const permParam = params.get('perm') ?? ''
  const perms = (): Record<string, unknown> => {
    const external = permParam === 'external'
    const state = (k: string): string => (external ? 'unknown' : k === 'automation' ? 'unknown' : permParam.split(',').includes(`${k}-off`) ? 'denied' : 'granted')
    return { screen: state('screen'), accessibility: state('accessibility'), automation: state('automation'), external, at: Date.now() }
  }
  webHandlers.set('permissions:get', () => perms())
  webHandlers.set('permissions:open', (kind) => {
    console.info(`[tut] stage: would open System Settings (${String(kind)})`)
    return typeof kind === 'string' && ['screen', 'accessibility', 'automation'].includes(kind)
  })
  webHandlers.set('permissions:watch', () => true)

  // Copy details (A7 builds the allowlisted text; main copies it with Electron's clipboard).
  webHandlers.set('diagnostics:copy', async (text) => {
    if (typeof text !== 'string' || !navigator.clipboard?.writeText) return false
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      return false
    }
  })
  // The stage never leaves the page.
  webHandlers.set('open:external', (url) => {
    console.info(`[tut] stage: would open ${typeof url === 'string' ? url.slice(0, 80) : '?'}`)
    return true
  })
  // Restart (main/localEngine.ts): the mock is always up; ?engine=external says "Restart it in Terminal".
  webHandlers.set('engine-local:restart', () => {
    if (params.get('engine-local') === 'external') return { ok: false, state: 'external' }
    fire('feat:engine-local', { state: 'starting' })
    setTimeout(() => fire('feat:engine-local', { state: 'running' }), 800)
    return { ok: true, state: 'starting' }
  })
  if (params.get('engine-local') === 'external') webHandlers.set('engine-local:get', () => ({ state: 'external' }))
  // The install token (main/features/cloud.ts): off in the stage.
  webHandlers.set('cloud:get', () => ({ state: 'off', configured: false, secure: true, hasToken: false }))
  webHandlers.set('cloud:retry', () => ({ state: 'off', configured: false, secure: true, hasToken: false }))

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
