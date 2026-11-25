/**
 * Lane engine-isolation (app/agents/engine-isolation.md), offline: the installed app and a dev setup never share an
 * engine, a pid file or a settings folder, and the app's engine can't be told to auto-resume or autostart.
 * No engine is started: spawn is a fake, and the "engine" on the port is a bare TCP listener this test owns.
 */
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer, type Server } from 'node:net'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, afterEach, before, beforeEach, describe, test } from 'node:test'

// The shared electron fake (test/fakes/electron.ts) has only what other features touch. localEngine.ts and identity.ts
// also need ipcMain, clipboard and a few app methods: add them to the same module object they import.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const electron = require('electron') as Record<string, unknown> & { app: Record<string, unknown> }
const handlers = new Map<string, unknown>()
if (!electron.ipcMain) Object.defineProperty(electron, 'ipcMain', { value: { handle: (ch: string, fn: unknown) => handlers.set(ch, fn) }, enumerable: true })
if (!electron.clipboard) Object.defineProperty(electron, 'clipboard', { value: { writeText: () => undefined }, enumerable: true })
const fakeApp = electron.app
const paths = new Map<string, string>()
const sandbox = mkdtempSync(join(tmpdir(), 'miyagi-isolation-'))
paths.set('appData', join(sandbox, 'Application Support'))
paths.set('userData', join(sandbox, 'Application Support', 'miyagi'))
Object.assign(fakeApp, {
  getVersion: () => '0.0.0-test',
  getName: () => 'miyagi',
  setName: () => undefined,
  getPath: (k: string) => {
    const p = paths.get(k)
    if (!p) throw new Error(`no fake path for ${k}`)
    return p
  },
  setPath: (k: string, v: string) => void paths.set(k, v),
  runningUnderARM64Translation: false
})

// Imported after the fake is complete (identity.ts calls setName and setPath when it loads).
// eslint-disable-next-line @typescript-eslint/no-require-imports
const le = require('../src/main/localEngine') as typeof import('../src/main/localEngine')
// eslint-disable-next-line @typescript-eslint/no-require-imports
const identity = require('../src/main/identity') as typeof import('../src/main/identity')

after(() => rmSync(sandbox, { recursive: true, force: true }))

describe('adoptExternal: who may use an engine it did not start', () => {
  test('the installed app (packaged, mode unset or bundled) never adopts one', () => {
    assert.equal(le.adoptExternal({ packaged: true, mode: undefined, ours: false }), false)
    assert.equal(le.adoptExternal({ packaged: true, mode: 'bundled', ours: false }), false)
  })
  test('engine mode dev, or npm run dev, adopts it', () => {
    assert.equal(le.adoptExternal({ packaged: true, mode: 'dev', ours: false }), true)
    assert.equal(le.adoptExternal({ packaged: false, mode: undefined, ours: false }), true)
    assert.equal(le.adoptExternal({ packaged: false, mode: 'bundled', ours: false }), true)
  })
  test('its own leftover, now stopped, is never adopted: a fresh one starts', () => {
    assert.equal(le.adoptExternal({ packaged: false, mode: 'dev', ours: true }), false)
  })
})

describe('the engine environment: no auto-resume, no autostart, a fixed save folder', () => {
  const inherited = { PATH: '/usr/bin', ORCH_AUTO_RESUME: '1', ORCH_AUTOSTART: '1', PYTHONHOME: '/x', VIRTUAL_ENV: '/v' }

  test('packaged: the bundled Python gets 0 and 0 even when the env says 1', () => {
    const e = le.pythonEnv(inherited, '/h', '/py/bin/python3', 8787, true)
    assert.equal(e.ORCH_AUTO_RESUME, '0')
    assert.equal(e.ORCH_AUTOSTART, '0')
    assert.equal(e.MIYAGI_STATE_DIR, join(homedir(), 'miyagi', 'state'))
    assert.equal(e.ENGINE_PORT, '8787')
    assert.equal(e.PYTHONHOME, undefined)
    assert.equal(e.VIRTUAL_ENV, undefined)
  })
  test('packaged: the launcher runtime gets the same pins', () => {
    const e = le.launcherEnv(inherited, true)
    assert.equal(e.ORCH_AUTO_RESUME, '0')
    assert.equal(e.ORCH_AUTOSTART, '0')
    assert.equal(e.MIYAGI_STATE_DIR, join(homedir(), 'miyagi', 'state'))
    assert.equal(e.PATH, '/usr/bin')
  })
  test('an explicit MIYAGI_STATE_DIR is kept', () => {
    assert.equal(le.pythonEnv({ MIYAGI_STATE_DIR: '/s' }, '/h', '/p', 8787, true).MIYAGI_STATE_DIR, '/s')
    assert.equal(le.launcherEnv({ MIYAGI_STATE_DIR: '/s' }, true).MIYAGI_STATE_DIR, '/s')
  })
  test('npm run dev: an explicit value is kept, the default is 0, saves go to state-dev', () => {
    assert.equal(le.pythonEnv(inherited, '/h', '/p', 8787, false).ORCH_AUTO_RESUME, '1')
    const bare = le.launcherEnv({}, false)
    assert.equal(bare.ORCH_AUTO_RESUME, '0')
    assert.equal(bare.ORCH_AUTOSTART, '0')
    assert.equal(bare.MIYAGI_STATE_DIR, join(homedir(), 'miyagi', 'state-dev'))
  })
})

describe('launch pins (R17, R31, R45)', () => {
  test('packaged: web search off, no run recording, the network check probes our cloud', () => {
    for (const e of [le.pythonEnv({ COACH_WEB: '1', ORCH_RECORD: '1' }, '/h', '/p', 8787, true), le.launcherEnv({ COACH_WEB: '1' }, true)]) {
      assert.equal(e.COACH_WEB, '0')
      assert.equal(e.ORCH_RECORD, '0')
      assert.equal(e.MIYAGI_NET_PROBE, 'miyagi-cloud.onrender.com:443')
    }
  })
  test('packaged: the probe is always our cloud, whatever MIYAGI_CLOUD_URL says (A12)', () => {
    assert.equal(le.netProbe({ MIYAGI_CLOUD_URL: 'https://elsewhere.example/v1' }), 'miyagi-cloud.onrender.com:443')
    assert.equal(le.netProbe({ MIYAGI_CLOUD_URL: 'http://127.0.0.1:9000' }), 'miyagi-cloud.onrender.com:443')
    assert.equal(le.netProbe({}), 'miyagi-cloud.onrender.com:443')
  })
  test('packaged with the cloud off: web search and recording still off, the engine keeps its own probe', () => {
    const e = le.launcherEnv({ MIYAGI_CLOUD_URL: 'off' }, true)
    assert.equal(e.COACH_WEB, '0')
    assert.equal(e.ORCH_RECORD, '0')
    assert.equal(e.MIYAGI_NET_PROBE, undefined)
  })
  test('npm run dev: the engine keeps its own defaults', () => {
    const e = le.pythonEnv({}, '/h', '/p', 8787, false)
    assert.equal(e.COACH_WEB, undefined)
    assert.equal(e.ORCH_RECORD, undefined)
    assert.equal(e.MIYAGI_NET_PROBE, undefined)
  })
})

describe('pid file per build', () => {
  test('app-engine.json when packaged, app-engine-dev.json when not', () => {
    assert.equal(le.pidFileName(true), 'app-engine.json')
    assert.equal(le.pidFileName(false), 'app-engine-dev.json')
  })
})

describe('identity: its own settings folder per build', () => {
  const appData = join(sandbox, 'Application Support')
  const fake = (packaged: boolean): { isPackaged: boolean; getPath: (k: string) => string; setPath: (k: string, v: string) => void; set: Map<string, string> } => {
    const set = new Map<string, string>()
    return { isPackaged: packaged, getPath: (k) => (k === 'appData' ? appData : join(appData, 'miyagi')), setPath: (k, v) => void set.set(k, v), set }
  }

  test('loading identity.ts in a dev run (the fake electron is not packaged) moves userData to miyagi-dev', () => {
    assert.equal(paths.get('userData'), join(appData, 'miyagi-dev'))
  })
  test('not packaged: userData is <appData>/miyagi-dev', () => {
    const a = fake(false)
    assert.equal(identity.isolateUserData(a, {}), join(appData, 'miyagi-dev'))
    assert.equal(a.set.get('userData'), join(appData, 'miyagi-dev'))
  })
  test('packaged: userData is left alone', () => {
    const a = fake(true)
    assert.equal(identity.isolateUserData(a, {}), undefined)
    assert.equal(a.set.size, 0)
  })
  test('MIYAGI_USER_DATA wins', () => {
    for (const packaged of [false, true]) {
      const a = fake(packaged)
      identity.isolateUserData(a, { MIYAGI_USER_DATA: '/tmp/own-miyagi' })
      assert.equal(a.set.get('userData'), '/tmp/own-miyagi')
    }
  })
})

// ---------------------------------------------------------------------------------------------------------------------
// Regression: the installed app found an engine it didn't start on its port and silently used it ('external').

type FakeEngine = { setToken: () => void; onStatus: (fn: (up: boolean) => void) => void; reconnect: () => void; holdFailures: (on: boolean) => void; connected: boolean }
const fakeEngine = (): FakeEngine => ({ setToken: () => undefined, onStatus: () => undefined, reconnect: () => undefined, holdFailures: () => undefined, connected: false })

async function until(cond: () => boolean, ms = 4000): Promise<void> {
  for (const end = Date.now() + ms; Date.now() < end; ) {
    if (cond()) return
    await new Promise((r) => setTimeout(r, 20))
  }
  assert.fail('timed out waiting')
}

describe('packaged app, port held by an engine it did not start', () => {
  let server: Server
  let port = 0
  let home = ''
  let resources = ''
  let stop: () => void = () => undefined
  const saved: Record<string, string | undefined> = {}
  const envKeys = ['MIYAGI_HOME', 'MIYAGI_ENGINE', 'MIYAGI_AUTOSTART', 'DEMO', 'ORCH_AUTO_RESUME', 'ORCH_AUTOSTART', 'MIYAGI_STATE_DIR', 'MIYAGI_CLOUD_URL']
  const savedResources = (process as { resourcesPath?: string }).resourcesPath

  before(() => {
    for (const k of envKeys) saved[k] = process.env[k]
  })
  beforeEach(async () => {
    server = createServer((s) => s.destroy())
    await new Promise<void>((r) => server.listen(0, '127.0.0.1', r))
    port = (server.address() as { port: number }).port
    home = mkdtempSync(join(sandbox, 'engine-home-'))
    resources = mkdtempSync(join(sandbox, 'resources-'))
    for (const k of envKeys) delete process.env[k]
    process.env.MIYAGI_HOME = home
    // The inherited env asks for a resumed, autostarted lesson: the app's engine must not get either.
    process.env.ORCH_AUTO_RESUME = '1'
    process.env.ORCH_AUTOSTART = '1'
    ;(process as { resourcesPath?: string }).resourcesPath = resources
    fakeApp.isPackaged = true
  })
  afterEach(async () => {
    stop()
    stop = () => undefined
    fakeApp.isPackaged = false
    ;(process as { resourcesPath?: string }).resourcesPath = savedResources
    for (const k of envKeys) {
      if (saved[k] === undefined) delete process.env[k]
      else process.env[k] = saved[k]
    }
    await new Promise<void>((r) => (server.listening ? server.close(() => r()) : r()))
  })

  const boot = (deps: Record<string, unknown> = {}): { states: Array<Record<string, unknown>> } => {
    const states: Array<Record<string, unknown>> = []
    const broadcast = (ch: string, payload: unknown): void => {
      if (ch === 'engine-local') states.push(payload as Record<string, unknown>)
    }
    const setup = le.setupLocalEngine as unknown as (...a: unknown[]) => () => void
    // The quit in afterEach signals the fake child: a fake kill and alive, so no real pid is ever signalled.
    stop = setup(fakeEngine(), `ws://127.0.0.1:${port}`, broadcast, () => true, {
      platform: 'darwin',
      holder: async () => 'pid 4242 (Python)',
      kill: () => undefined,
      alive: () => false,
      quitGraceMs: 50,
      quitConfirmMs: 50,
      ...deps
    })
    return { states }
  }

  test('ends in failed with the calm line, never external, and never stops the other engine', async () => {
    const spawned: unknown[] = []
    const { states } = boot({ spawn: (...a: unknown[]) => (spawned.push(a), assert.fail('no engine may start while the port is held')), pollMs: 60_000 })
    await until(() => states.some((s) => s.state === 'failed' || s.state === 'external'))
    await new Promise((r) => setTimeout(r, 100))
    assert.ok(!states.some((s) => s.state === 'external'), `states: ${states.map((s) => s.state).join(' > ')}`)
    const last = states.at(-1) ?? {}
    assert.equal(last.state, 'failed')
    assert.equal(last.line, 'Another miyagi engine is running.')
    assert.equal(last.reason, `port ${port} held by an engine this app did not start`)
    assert.equal(spawned.length, 0)
    assert.ok(server.listening, 'the other engine is still up')
    const log = readFileSync(join(home, 'logs', 'engine.log'), 'utf8')
    assert.match(log, /pid 4242 \(Python\)/)
  })

  test('once the port is free it starts its own engine, launcher env pinned, pid file per build', async () => {
    // A user-installed launcher (no BUNDLED marker, no bundled Python in the fake Resources): the launcher runtime.
    mkdirSync(join(home, 'bin'), { recursive: true })
    writeFileSync(join(home, 'bin', 'miyagi-engine'), '#!/bin/sh\nexit 0\n')
    const spawned: Array<{ cmd: string; env: NodeJS.ProcessEnv }> = []
    const { states } = boot({
      pollMs: 50,
      spawn: (cmd: string, _args: string[], opts: { env: NodeJS.ProcessEnv }) => {
        spawned.push({ cmd, env: opts.env })
        return Object.assign(new EventEmitter(), { pid: 99999, killed: true })
      }
    })
    await until(() => states.some((s) => s.state === 'failed'))
    await new Promise<void>((r) => server.close(() => r()))
    await until(() => spawned.length > 0)
    assert.equal(spawned.length, 1)
    assert.equal(spawned[0].cmd, join(home, 'bin', 'miyagi-engine'))
    assert.equal(spawned[0].env.ORCH_AUTO_RESUME, '0')
    assert.equal(spawned[0].env.ORCH_AUTOSTART, '0')
    assert.equal(spawned[0].env.MIYAGI_STATE_DIR, join(homedir(), 'miyagi', 'state'))
    assert.equal(states.at(-1)?.state, 'starting')
    assert.ok(existsSync(join(home, 'run', 'app-engine.json')))
    assert.ok(!existsSync(join(home, 'run', 'app-engine-dev.json')))
  })

  test('npm run dev (not packaged, MIYAGI_AUTOSTART=1) still adopts the engine on the port', async () => {
    fakeApp.isPackaged = false
    process.env.MIYAGI_AUTOSTART = '1'
    const { states } = boot({ spawn: () => assert.fail('no spawn'), pollMs: 60_000 })
    await until(() => states.some((s) => s.state === 'external' || s.state === 'failed'))
    assert.equal(states.at(-1)?.state, 'external')
  })
})

// ---------------------------------------------------------------------------------------------------------------------
// Lane reconnect (app/agents/reconnect.md), ROADMAP 1.4: localEngine's half of the respawn, and a Restart of an engine
// that ignores SIGTERM. The child is a fake (an EventEmitter), and every signal goes through deps.kill, a fake that
// only records it: no real pid is ever signalled.

type FakeChild = EventEmitter & { pid: number; killed: boolean; exitCode: number | null; kill: (sig?: string) => boolean }

describe('localEngine respawn and restart (fake child, fake kill)', () => {
  let home = ''
  let stop: () => void = () => undefined
  const saved: Record<string, string | undefined> = {}
  const envKeys = ['MIYAGI_HOME', 'MIYAGI_ENGINE', 'MIYAGI_AUTOSTART', 'DEMO', 'MIYAGI_CLOUD_URL']
  const savedResources = (process as { resourcesPath?: string }).resourcesPath

  before(() => {
    for (const k of envKeys) saved[k] = process.env[k]
  })
  beforeEach(() => {
    home = mkdtempSync(join(sandbox, 'respawn-home-'))
    for (const k of envKeys) delete process.env[k]
    process.env.MIYAGI_HOME = home
    // A user-installed launcher (no BUNDLED marker, no bundled Python): boot() goes straight to start().
    mkdirSync(join(home, 'bin'), { recursive: true })
    writeFileSync(join(home, 'bin', 'miyagi-engine'), '#!/bin/sh\nexit 0\n')
    ;(process as { resourcesPath?: string }).resourcesPath = mkdtempSync(join(sandbox, 'respawn-resources-'))
    fakeApp.isPackaged = true
  })
  afterEach(() => {
    stop()
    stop = () => undefined
    le.setRespawnPolicy(undefined)
    fakeApp.isPackaged = false
    ;(process as { resourcesPath?: string }).resourcesPath = savedResources
    for (const k of envKeys) {
      if (saved[k] === undefined) delete process.env[k]
      else process.env[k] = saved[k]
    }
  })

  type Booted = {
    states: Array<Record<string, unknown>>
    holds: boolean[]
    children: FakeChild[]
    kills: Array<{ pid: number; sig: string }>
    up: () => void
    down: () => void
    exit: (c: FakeChild, code: number | null, signal?: string | null) => void
    last: () => Record<string, unknown>
  }

  /** Boot with a free port and the launcher. `onKill(child, sig)` decides what a signal does (default: ignored). */
  const boot = (onKill: (c: FakeChild, sig: string) => void = () => undefined): Booted => {
    const states: Array<Record<string, unknown>> = []
    const holds: boolean[] = []
    const children: FakeChild[] = []
    const kills: Array<{ pid: number; sig: string }> = []
    const listeners: Array<(up: boolean) => void> = []
    const link = {
      connected: false,
      setToken: () => undefined,
      reconnect: () => undefined,
      holdFailures: (on: boolean) => void holds.push(on),
      onStatus: (fn: (up: boolean) => void) => void listeners.push(fn)
    }
    const broadcast = (ch: string, payload: unknown): void => {
      if (ch === 'engine-local') states.push(payload as Record<string, unknown>)
    }
    const spawn = (): FakeChild => {
      // Made-up pids, never signalled: deps.kill below only records.
      const c: FakeChild = Object.assign(new EventEmitter(), {
        pid: 990_001 + children.length,
        killed: false,
        exitCode: null as number | null,
        kill: (): boolean => assert.fail('the group kill (deps.kill) must be used')
      })
      children.push(c)
      return c
    }
    const kill = (pid: number, sig: string): void => {
      kills.push({ pid, sig })
      const c = children.find((x) => x.pid === -pid)
      if (c) onKill(c, sig)
    }
    const setup = le.setupLocalEngine as unknown as (...a: unknown[]) => () => void
    stop = setup(link, 'ws://127.0.0.1:18787', broadcast, () => true, {
      platform: 'darwin',
      listening: async () => false,
      holder: async () => 'none',
      spawn,
      kill,
      // No group left behind once a fake child exits; quit's grace kept short.
      alive: () => false,
      quitGraceMs: 60,
      quitConfirmMs: 60,
      killAfterMs: 60,
      startTimeoutMs: 400
    })
    return {
      states,
      holds,
      children,
      kills,
      up: () => {
        link.connected = true
        for (const fn of listeners) fn(true)
      },
      down: () => {
        link.connected = false
        for (const fn of listeners) fn(false)
      },
      exit: (c, code, signal = null) => {
        c.exitCode = code
        c.emit('exit', code, signal)
      },
      last: () => states.at(-1) ?? {}
    }
  }

  /** Booted, spawned, answering: 'running'. */
  const running = async (onKill?: (c: FakeChild, sig: string) => void): Promise<Booted> => {
    const e = boot(onKill)
    await until(() => e.children.length === 1)
    e.up()
    assert.equal(e.last().state, 'running')
    return e
  }
  const pause = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

  test('a crash while running asks the policy, holds failures in starting, then starts again after the delay', async () => {
    const asked: string[] = []
    le.setRespawnPolicy((why) => (asked.push(why), 80))
    const e = await running()
    e.down()
    e.exit(e.children[0], 1)
    assert.deepEqual(asked, ['exited with code 1'])
    assert.equal(e.last().state, 'starting')
    assert.equal(e.holds.at(-1), true, 'refused connects are not counted while it respawns')
    await pause(30)
    assert.equal(e.children.length, 1, 'not before the delay')
    await until(() => e.children.length === 2)
    assert.equal(e.last().state, 'starting')
    e.up()
    assert.equal(e.last().state, 'running')
    assert.equal(e.holds.at(-1), false)
  })

  test('a crash before it ever ran is not respawned (the policy is only for a mid-run crash)', async () => {
    const asked: string[] = []
    le.setRespawnPolicy((why) => (asked.push(why), 10))
    const e = boot()
    await until(() => e.children.length === 1)
    e.exit(e.children[0], 2)
    assert.deepEqual(asked, [])
    assert.equal(e.last().state, 'failed')
  })

  test('a spent budget (undefined delay) ends in failed with Retry, and Retry starts it', async () => {
    le.setRespawnPolicy(() => undefined)
    const e = await running()
    e.down()
    e.exit(e.children[0], null, 'SIGKILL')
    assert.equal(e.last().state, 'failed')
    assert.equal(e.last().line, 'The engine stopped.')
    assert.equal(e.holds.at(-1), false, 'failures count again, so the surfaces reach Retry')
    await pause(100)
    assert.equal(e.children.length, 1, 'nothing starts on its own')
    assert.deepEqual(le.restartLocalEngine(), { ok: true, state: 'checking' })
    await until(() => e.children.length === 2)
    assert.equal(e.last().state, 'starting')
  })

  test('Retry while a respawn waits starts it at once', async () => {
    le.setRespawnPolicy(() => 60_000)
    const e = await running()
    e.down()
    e.exit(e.children[0], 1)
    assert.equal(e.children.length, 1)
    assert.deepEqual(le.restartLocalEngine(), { ok: true, state: 'starting' })
    assert.equal(e.children.length, 2, 'started now, not after 60 s')
    assert.equal(e.last().state, 'starting')
  })

  test('quitting cancels a waiting respawn and ends in off', async () => {
    le.setRespawnPolicy(() => 60)
    const e = await running()
    e.down()
    e.exit(e.children[0], 1)
    assert.equal(e.last().state, 'starting')
    stop()
    stop = () => undefined
    assert.equal(e.last().state, 'off')
    await pause(150)
    assert.equal(e.children.length, 1, 'the respawn never starts')
    assert.equal(e.last().state, 'off')
  })

  test('Restart of an engine that ignores SIGTERM: SIGKILL after killAfterMs, then a fresh start that runs', async () => {
    // A hung uvicorn: SIGTERM only sets should_exit, which a blocked loop never acts on. SIGKILL ends it.
    const e = await running((c, sig) => {
      if (sig === 'SIGKILL') setImmediate(() => c.emit('exit', null, 'SIGKILL'))
    })
    e.down()
    assert.deepEqual(le.restartLocalEngine(), { ok: true, state: 'starting' })
    assert.deepEqual(e.kills, [{ pid: -990_001, sig: 'SIGTERM' }])
    assert.equal(e.last().state, 'starting')
    await until(() => e.children.length === 2)
    assert.deepEqual(e.kills, [
      { pid: -990_001, sig: 'SIGTERM' },
      { pid: -990_001, sig: 'SIGKILL' }
    ])
    assert.equal(e.last().state, 'starting')
    e.up()
    assert.equal(e.last().state, 'running')
    // The new engine answered: no late failure from the restart's own timeout.
    await pause(500)
    assert.equal(e.last().state, 'running')
    assert.equal(e.kills.length, 2)
  })

  test('an engine that obeys SIGTERM gets no SIGKILL', async () => {
    const e = await running((c, sig) => {
      if (sig === 'SIGTERM') setImmediate(() => c.emit('exit', null, 'SIGTERM'))
    })
    e.down()
    le.restartLocalEngine()
    await until(() => e.children.length === 2)
    await pause(150)
    assert.deepEqual(e.kills, [{ pid: -990_001, sig: 'SIGTERM' }])
  })

  test('a restart that never completes ends in failed with Retry, never starting forever; Retry kills it again', async () => {
    let unkillable = true
    const e = await running((c, sig) => {
      if (!unkillable && sig === 'SIGKILL') setImmediate(() => c.emit('exit', null, 'SIGKILL'))
    })
    e.down()
    le.restartLocalEngine()
    assert.equal(e.last().state, 'starting')
    await until(() => e.last().state === 'failed', 2000)
    assert.equal(e.last().line, "miyagi couldn't start its engine.")
    assert.equal(e.holds.at(-1), false, 'failures count again')
    assert.deepEqual(
      e.kills.map((k) => k.sig),
      ['SIGTERM', 'SIGKILL']
    )
    // Retry: this time the kill works, and a new engine starts.
    unkillable = false
    assert.deepEqual(le.restartLocalEngine(), { ok: true, state: 'starting' })
    assert.equal(e.kills.at(-1)?.sig, 'SIGKILL')
    await until(() => e.children.length === 2)
    assert.equal(e.last().state, 'starting')
  })

  test('quitting during a Restart cancels the pending SIGKILL timer and kills the stuck engine once', async () => {
    const e = await running((c, sig) => {
      if (sig === 'SIGKILL') setImmediate(() => c.emit('exit', null, 'SIGKILL'))
    })
    e.down()
    le.restartLocalEngine()
    stop()
    stop = () => undefined
    assert.deepEqual(
      e.kills.map((k) => k.sig),
      ['SIGTERM', 'SIGKILL']
    )
    await until(() => e.last().state === 'off')
    await pause(150)
    assert.equal(e.kills.length, 2, 'the timer never fires after quit')
    assert.equal(e.children.length, 1, 'nothing starts after quit')
  })
})

// ---------------------------------------------------------------------------------------------------------------------
// R44 (research/launch/SOLUTIONS.md): quitting stops a hung engine (SIGTERM, then SIGKILL to its group), the pid file
// goes only once the engine and its group are gone, and the next launch stops a stray engine of this app before it
// starts its own. Fake child, fake kill, fake alive and fake ps: no real pid is ever signalled
// (test/engineProcess.test.ts has the one real-process check).

describe('R44: quit stops a hung engine; the next launch reclaims a stray one', () => {
  let home = ''
  let stop: () => Promise<void> | void = () => undefined
  const saved: Record<string, string | undefined> = {}
  const envKeys = ['MIYAGI_HOME', 'MIYAGI_ENGINE', 'MIYAGI_AUTOSTART', 'DEMO', 'MIYAGI_CLOUD_URL']
  const savedResources = (process as { resourcesPath?: string }).resourcesPath
  const GRACE = 150
  const AT = new Date(Date.now() - 3_600_000).toISOString()

  before(() => {
    for (const k of envKeys) saved[k] = process.env[k]
  })
  beforeEach(() => {
    home = mkdtempSync(join(sandbox, 'r44-home-'))
    for (const k of envKeys) delete process.env[k]
    process.env.MIYAGI_HOME = home
    // A user-installed launcher (no BUNDLED marker, no bundled Python): boot() goes straight to start().
    mkdirSync(join(home, 'bin'), { recursive: true })
    writeFileSync(join(home, 'bin', 'miyagi-engine'), '#!/bin/sh\nexit 0\n')
    ;(process as { resourcesPath?: string }).resourcesPath = mkdtempSync(join(sandbox, 'r44-resources-'))
    fakeApp.isPackaged = true
  })
  afterEach(() => {
    void stop()
    stop = () => undefined
    fakeApp.isPackaged = false
    ;(process as { resourcesPath?: string }).resourcesPath = savedResources
    for (const k of envKeys) {
      if (saved[k] === undefined) delete process.env[k]
      else process.env[k] = saved[k]
    }
  })

  const pidFile = (): string => join(home, 'run', 'app-engine.json')
  const pidInFile = (): number | undefined => {
    try {
      return (JSON.parse(readFileSync(pidFile(), 'utf8')) as { pid: number }).pid
    } catch {
      return undefined
    }
  }
  const pause = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

  type World = {
    states: Array<Record<string, unknown>>
    children: FakeChild[]
    kills: Array<{ pid: number; sig: string }>
    /** What the fake `alive` answers for: pids (leaders) and -pids (their groups). */
    live: Set<number>
    events: string[]
    up: () => void
    last: () => Record<string, unknown>
  }
  /** A signal reached group `pgid`: what it does is up to the test (default: nothing, a hung engine). */
  type OnKill = (w: World, pgid: number, sig: string) => void
  /** The leader exits (Node reaps it: 'exit'); its group may or may not go with it. */
  const leaderExits = (w: World, pgid: number, sig: string, groupToo = true): void => {
    w.live.delete(pgid)
    if (groupToo) w.live.delete(-pgid)
    const c = w.children.find((x) => x.pid === pgid)
    if (c) setImmediate(() => c.emit('exit', null, sig))
  }

  const boot = (o: { onKill?: OnKill; procs?: Map<number, { command: string; startedAt: number }>; live?: number[] } = {}): World => {
    const listeners: Array<(up: boolean) => void> = []
    const link = { connected: false, setToken: () => undefined, reconnect: () => undefined, holdFailures: () => undefined, onStatus: (fn: (up: boolean) => void) => void listeners.push(fn) }
    const w: World = {
      states: [],
      children: [],
      kills: [],
      live: new Set(o.live ?? []),
      events: [],
      up: () => {
        link.connected = true
        for (const fn of listeners) fn(true)
      },
      last: () => w.states.at(-1) ?? {}
    }
    const spawn = (): FakeChild => {
      // Made-up pids, never signalled: deps.kill below only records.
      const c: FakeChild = Object.assign(new EventEmitter(), {
        pid: 991_001 + w.children.length,
        killed: false,
        exitCode: null as number | null,
        kill: (): boolean => assert.fail('the group kill (deps.kill) must be used')
      })
      w.children.push(c)
      w.live.add(c.pid)
      w.live.add(-c.pid)
      w.events.push(`spawn ${c.pid}`)
      return c
    }
    const broadcast = (ch: string, payload: unknown): void => {
      if (ch === 'engine-local') w.states.push(payload as Record<string, unknown>)
    }
    const setup = le.setupLocalEngine as unknown as (...a: unknown[]) => () => Promise<void> | void
    stop = setup(link, 'ws://127.0.0.1:18787', broadcast, () => true, {
      platform: 'darwin',
      listening: async () => false,
      holder: async () => 'none',
      spawn,
      kill: (pid: number, sig: string) => {
        w.kills.push({ pid, sig })
        w.events.push(`${sig} ${pid}`)
        if (!w.live.has(pid)) throw Object.assign(new Error('ESRCH'), { code: 'ESRCH' })
        o.onKill?.(w, Math.abs(pid), sig)
      },
      alive: (pid: number) => w.live.has(pid),
      procInfo: async (pid: number) => o.procs?.get(pid),
      groupMembers: async () => [],
      quitGraceMs: GRACE,
      quitConfirmMs: 100,
      killAfterMs: 100,
      startTimeoutMs: 60_000
    })
    return w
  }
  const running = async (onKill?: OnKill): Promise<World> => {
    const w = boot({ onKill })
    await until(() => w.children.length === 1)
    w.up()
    assert.equal(w.last().state, 'running')
    assert.equal(pidInFile(), 991_001)
    return w
  }
  const quit = (): Promise<void> => {
    const p = stop()
    stop = () => undefined
    assert.ok(p instanceof Promise, 'a running engine makes the quit wait')
    return p
  }

  test('quit, engine obeys SIGTERM: one SIGTERM to its group, then the pid file goes', async () => {
    const w = await running((w, pgid, sig) => sig === 'SIGTERM' && leaderExits(w, pgid, sig))
    const p = quit()
    assert.deepEqual(w.kills, [{ pid: -991_001, sig: 'SIGTERM' }])
    await p
    assert.deepEqual(w.kills, [{ pid: -991_001, sig: 'SIGTERM' }])
    assert.equal(existsSync(pidFile()), false)
    assert.equal(w.last().state, 'off')
  })

  test('quit, hung engine (kill -STOP) ignores SIGTERM: SIGKILL to the group after the grace; the pid file stays until it is gone', async () => {
    const w = await running((w, pgid, sig) => sig === 'SIGKILL' && leaderExits(w, pgid, sig))
    const t = Date.now()
    const p = quit()
    await pause(GRACE / 3)
    assert.deepEqual(w.kills, [{ pid: -991_001, sig: 'SIGTERM' }], 'no SIGKILL before the grace')
    assert.equal(pidInFile(), 991_001, 'still running: the pid file stays')
    await p
    assert.ok(Date.now() - t >= GRACE - 5, `waited ${Date.now() - t} ms`)
    assert.deepEqual(w.kills, [
      { pid: -991_001, sig: 'SIGTERM' },
      { pid: -991_001, sig: 'SIGKILL' }
    ])
    assert.equal(existsSync(pidFile()), false)
    assert.equal(w.last().state, 'off')
    assert.match(readFileSync(join(home, 'logs', 'engine.log'), 'utf8'), /ignored SIGTERM .*sending SIGKILL to its group/)
  })

  test('quit, the engine exits on SIGTERM but something it started does not: SIGKILL the group, then the pid file goes', async () => {
    const w = await running((w, pgid, sig) => {
      if (sig === 'SIGTERM') leaderExits(w, pgid, sig, false)
      if (sig === 'SIGKILL') w.live.delete(-pgid)
    })
    const p = quit()
    await pause(GRACE / 3)
    assert.equal(w.live.has(991_001), false, 'the leader exited')
    assert.equal(pidInFile(), 991_001, 'its group still runs: the pid file stays')
    await p
    assert.deepEqual(
      w.kills.map((k) => `${k.sig} ${k.pid}`),
      ['SIGTERM -991001', 'SIGKILL -991001']
    )
    assert.equal(existsSync(pidFile()), false)
  })

  test('quit, an engine that survives SIGKILL keeps its pid file for the next launch', async () => {
    const w = await running()
    await quit()
    assert.deepEqual(
      w.kills.map((k) => k.sig),
      ['SIGTERM', 'SIGKILL']
    )
    assert.equal(pidInFile(), 991_001)
    assert.match(readFileSync(join(home, 'logs', 'engine.log'), 'utf8'), /still running after SIGKILL; keeping/)
  })

  test('quit with no engine running: nothing to wait for', async () => {
    le.setRespawnPolicy(() => undefined)
    try {
      const w = await running()
      w.children[0].emit('exit', 1, null)
      assert.equal(existsSync(pidFile()), false, 'a crash forgets the pid at once')
      assert.equal(stop(), undefined)
      stop = () => undefined
      assert.deepEqual(w.kills, [])
    } finally {
      le.setRespawnPolicy(undefined)
    }
  })

  test('launch: a stray engine of this app (its command line and start time) is stopped before a new one starts, port or not', async () => {
    const stray = 990_900
    mkdirSync(join(home, 'run'), { recursive: true })
    writeFileSync(pidFile(), JSON.stringify({ pid: stray, port: 18787, runtime: 'launcher', at: AT }))
    const procs = new Map([[stray, { command: join(home, 'bin', 'miyagi-engine'), startedAt: Date.parse(AT) + 400 }]])
    // Hung: only SIGKILL ends it. The port is free (it never got that far, or only its children are left).
    const w = boot({ procs, live: [stray, -stray], onKill: (w, pgid, sig) => sig === 'SIGKILL' && leaderExits(w, pgid, sig) })
    await until(() => w.children.length === 1)
    assert.deepEqual(w.events, [`SIGTERM -${stray}`, `SIGKILL -${stray}`, 'spawn 991001'])
    assert.equal(pidInFile(), 991_001, 'the pid file names the new engine')
    assert.match(readFileSync(join(home, 'logs', 'engine.log'), 'utf8'), new RegExp(`earlier launch is still running \\(pid ${stray}`))
  })

  test('launch: a pid file whose pid now runs something else is never signalled', async () => {
    const reused = 990_901
    mkdirSync(join(home, 'run'), { recursive: true })
    writeFileSync(pidFile(), JSON.stringify({ pid: reused, port: 18787, runtime: 'launcher', at: AT }))
    const procs = new Map([[reused, { command: '/Users/learner/code/miyagi/run-live/.venv/bin/python -m server.orchestrator.main', startedAt: Date.parse(AT) }]])
    const w = boot({ procs, live: [reused, -reused] })
    await until(() => w.children.length === 1)
    assert.deepEqual(w.kills, [])
    assert.ok(w.live.has(reused))
    assert.equal(pidInFile(), 991_001)
  })

  test('launch: a pid file naming a process that is gone is cleared without a signal', async () => {
    mkdirSync(join(home, 'run'), { recursive: true })
    writeFileSync(pidFile(), JSON.stringify({ pid: 990_902, port: 18787, runtime: 'bundled', at: AT }))
    const w = boot()
    await until(() => w.children.length === 1)
    assert.deepEqual(w.kills, [])
    assert.equal(pidInFile(), 991_001)
  })
})
