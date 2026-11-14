/**
 * One bridge API for both runtimes:
 *   - Electron: window.tut from the preload (IPC to main, which owns the engine socket).
 *   - Browser (npm run dev:web): a local bus that mimics main's routing, plus a direct
 *     WebSocket to ENGINE_URL. If nothing answers, the mock engine runs inline.
 *
 * Browser query params: ?os=win · ?engine=inline · ?scenario=happy|offtrack|full · ?engine=ws://host:port
 */
import { parseEngineMessage, type Incoming, type Outgoing } from '../../common/wire'
import { describePlatform } from '../../main/platform'
import type { Layout, TutBridge, UiSignal, Unsub } from '../../preload/api'
import { createMockEngine, type MockEngine } from '../../../mock/engine'
import { scenarios, type ScenarioName } from '../../../mock/scenarios'

export type EngineMode = 'electron' | 'socket' | 'inline'

type Cb = (payload?: unknown) => void

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
    const name = (params.get('scenario') ?? 'full') as ScenarioName
    inline = createMockEngine(scenarios[name] ?? scenarios.full, dispatch, true)
    console.info(`[tut] no engine answered: running the "${name}" mock inline`)
    setStatus(true)
    inline.start()
    for (const m of queue.splice(0)) inline.handle(JSON.parse(m))
  }

  const connect = (): void => {
    const url = params.get('engine')?.startsWith('ws') ? params.get('engine')! : 'ws://localhost:8787'
    const sock = new WebSocket(url)
    ws = sock
    const giveUp = setTimeout(() => !everConnected && (sock.close(), startInline()), 900)
    sock.onopen = () => {
      clearTimeout(giveUp)
      everConnected = true
      mode = 'socket'
      setStatus(true)
      for (const m of queue.splice(0)) sock.send(m)
    }
    sock.onmessage = (m) => {
      const e = parseEngineMessage(String(m.data))
      if (e) dispatch(e)
    }
    sock.onclose = () => {
      clearTimeout(giveUp)
      if (!everConnected) return startInline()
      setStatus(false)
      setTimeout(connect, 1000)
    }
  }

  if (params.get('engine') === 'inline') startInline()
  else connect()

  let launcherOpen = false

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
        case 'launcher:toggle':
          launcherOpen = !launcherOpen
          fire(launcherOpen ? 'ui:launcher:open' : 'ui:launcher:close')
          break
        case 'launcher:hidden':
          launcherOpen = false
          break
        case 'launcher:built':
          launcherOpen = false
          fire('ui:pill:receive')
          break
        case 'shortcut':
          fire('ui:shortcut', payload)
          break
      }
    }
  }
}

const web = window.tut ? undefined : createWebBridge()

export const bridge: TutBridge = window.tut ?? web!

export const engineMode = (): EngineMode => (web ? web.mode() : 'electron')

export const isElectron = !!window.tut
