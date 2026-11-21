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

type FakeEngine = { setToken: () => void; onStatus: (fn: (up: boolean) => void) => void; reconnect: () => void; connected: boolean }
const fakeEngine = (): FakeEngine => ({ setToken: () => undefined, onStatus: () => undefined, reconnect: () => undefined, connected: false })

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
    stop = setup(fakeEngine(), `ws://127.0.0.1:${port}`, broadcast, () => true, { platform: 'darwin', holder: async () => 'pid 4242 (Python)', ...deps })
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
