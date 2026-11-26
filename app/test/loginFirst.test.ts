/**
 * Login first (Michael, Nov 21: "Right when it opens, it just opens up everything ... It needs to allow me to log in
 * first, like it's just starting from new"). A simulated launch of the main features that decide what opens
 * (auth, launch, onboarding, in index.ts's load order) around index.ts's gate wiring (main/gate.ts gateCore with a fake
 * overlay and the fake globalShortcut), offline.
 */
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, test } from 'node:test'
import { makeConsent } from '../src/common/consent'
import type { MainContext } from '../src/main/context'
import auth from '../src/main/features/auth'
import launch from '../src/main/features/launch'
import onboarding from '../src/main/features/onboarding'
import { gateCore, gateIsOpen, resetGateForTests } from '../src/main/gate'
import { patchPrefs, resetPrefsForTests } from '../src/main/prefs'
import { globalShortcut, promptCalls, shortcuts, trays } from './fakes/electron'
import { FakeCloud, FakeSupabase, stubFetch, writeSession } from './harness'

const LAUNCHER_KEY = 'Control+Space'
const ENV = ['MIYAGI_SKIP_ONBOARDING', 'MIYAGI_SKIP_LOGIN', 'MIYAGI_LOGIN', 'MIYAGI_QUIET_LAUNCH'] as const

type FakeWin = { route: string; shown: number; destroyed: boolean } & Record<string, unknown>

/** One simulated launch over a userData folder. */
type Launch = {
  invoke: (channel: string, ...args: unknown[]) => Promise<unknown>
  /** Every window opened through ctx.openWindow, in order. */
  opened: string[]
  overlayShown: () => number
  broadcasts: [string, unknown][]
  trayLabels: () => string[]
  quit: () => void
}

function fakeWindow(route: string): FakeWin {
  const w: FakeWin = {
    route,
    shown: 0,
    destroyed: false,
    isDestroyed: () => w.destroyed,
    isVisible: () => w.shown > 0,
    isMinimized: () => false,
    restore: () => undefined,
    show: () => void w.shown++,
    focus: () => undefined,
    once: () => undefined,
    on: () => undefined,
    setTitle: () => undefined
  }
  return w
}

function launchOver(dir: string): Launch {
  const handlers = new Map<string, (...a: unknown[]) => unknown>()
  const broadcasts: [string, unknown][] = []
  const quits: (() => void)[] = []
  const loaded: (() => void)[] = []
  const windows = new Map<string, FakeWin>()
  const opened: string[] = []
  let shown = 0
  const overlay = {
    showInactive: () => void shown++,
    hide: () => undefined,
    isDestroyed: () => false,
    getBounds: () => ({ x: 0, y: 0, width: 1440, height: 900 }),
    webContents: {
      isLoading: () => true,
      once: (ev: string, fn: () => void) => ev === 'did-finish-load' && loaded.push(fn),
      send: () => undefined
    }
  }
  const launcher = { isDestroyed: () => false, isVisible: () => false }
  const app = {
    isPackaged: false,
    getPath: () => dir,
    getVersion: () => '0.0.0-test',
    whenReady: () => Promise.resolve(),
    focus: () => undefined,
    quit: () => undefined,
    exit: () => undefined,
    relaunch: () => undefined,
    requestSingleInstanceLock: () => true,
    getLoginItemSettings: () => ({ wasOpenedAtLogin: false }),
    on: (ev: string, fn: () => void) => {
      if (ev === 'before-quit') quits.push(fn)
    }
  }
  const ctx = {
    app,
    platform: { os: 'mac', accelerators: { launcher: LAUNCHER_KEY } },
    engine: { onEvent: () => undefined, onOpen: () => undefined, setCloud: () => undefined, onCloudTokenInvalid: () => undefined },
    overlay,
    launcher,
    broadcast: (c: string, p: unknown) => broadcasts.push([c, p]),
    handle: (c: string, fn: (...a: unknown[]) => unknown) => handlers.set(c, fn),
    openWindow: (route: string) => {
      opened.push(route)
      const w = windows.get(route) ?? fakeWindow(route)
      windows.set(route, w)
      return w
    },
    appWindow: (route: string) => windows.get(route)
  } as unknown as MainContext

  // index.ts, in order: the core windows exist (hidden), gateCore wires them to the gate, then the features load.
  gateCore({
    overlay,
    launcherKey: (on) => {
      if (on) globalShortcut.register(LAUNCHER_KEY)
      else globalShortcut.unregister(LAUNCHER_KEY)
    },
    closed: () => undefined
  })
  for (const f of [auth, launch, onboarding]) f.setup(ctx)
  // The overlay's renderer finishes loading.
  for (const fn of loaded) fn()

  return {
    opened,
    broadcasts,
    overlayShown: () => shown,
    trayLabels: () => (trays.at(-1)?.menu?.items ?? []).map((i) => i.label).filter((l): l is string => !!l),
    invoke: async (c, ...a) => {
      const fn = handlers.get(c)
      if (!fn) throw new Error(`no handler ${c}`)
      return fn(...a)
    },
    quit: () => {
      for (const q of quits) q()
    }
  }
}

let dir: string
let envBefore: Partial<Record<(typeof ENV)[number], string>>
let launches: Launch[]
let restore: () => void
let supa: FakeSupabase

beforeEach(() => {
  envBefore = {}
  for (const k of ENV) {
    envBefore[k] = process.env[k]
    delete process.env[k]
  }
  dir = mkdtempSync(join(tmpdir(), 'miyagi-login-first-'))
  launches = []
  shortcuts.clear()
  promptCalls.length = 0
  supa = new FakeSupabase()
  restore = stubFetch(supa, new FakeCloud())
  resetGateForTests()
  resetPrefsForTests()
})
afterEach(() => {
  for (const l of launches) l.quit()
  restore()
  resetGateForTests()
  resetPrefsForTests()
  rmSync(dir, { recursive: true, force: true })
  for (const k of ENV) {
    if (envBefore[k] === undefined) delete process.env[k]
    else process.env[k] = envBefore[k]
  }
})

const start = (): Launch => {
  const l = launchOver(dir)
  launches.push(l)
  return l
}
/** A second launch with the same userData: the old run quits, the gate (process memory) starts over. */
const relaunch = (): Launch => {
  for (const l of launches) l.quit()
  launches = []
  resetGateForTests()
  shortcuts.clear()
  return start()
}
const write = (name: string, v: unknown): void => writeFileSync(join(dir, name), JSON.stringify(v))
/** prefs.json already holds this build's consent (main/prefs.ts reads the file only in setupPrefs, which tests skip). */
const agreedBefore = (): void => void patchPrefs({ consent: makeConsent() })
type Get = { login: boolean; flow: boolean; consent: boolean; gate: { login: boolean; consent: boolean; setup: boolean; open: boolean } }

describe('a launch starts from new: login first, nothing else', () => {
  test("Michael's Mac: stale prefs onboarded, setup not done, no session, an old login.json", async () => {
    write('prefs.json', { onboarded: true })
    write('onboarding.json', { done: false })
    write('login.json', { decided: true })
    const l = start()

    assert.equal(gateIsOpen(), false)
    const got = (await l.invoke('onboarding:get')) as Get
    assert.equal(got.login, true, 'onboarding:get says the login is needed')
    assert.equal(got.consent, false, 'and consent')
    assert.deepEqual(got.gate, { login: false, consent: false, setup: false, open: false })
    assert.deepEqual(l.opened, ['library'], 'only the home window opens (its flow starts at the login)')
    assert.equal(l.overlayShown(), 0, 'the overlay is never shown')
    assert.equal(shortcuts.has(LAUNCHER_KEY), false, 'the launcher key is never registered')
    assert.deepEqual(l.trayLabels(), ['Open miyagi', 'Quit miyagi'])
    assert.deepEqual(promptCalls, [], 'no Screen Recording or Accessibility prompt at launch')
    assert.deepEqual(JSON.parse(readFileSync(join(dir, 'login.json'), 'utf8')), { decided: true }, 'the old login.json is left alone')
  })

  test('the guest path: Continue without an account, consent, then Set up later, opens the gate; the next launch asks again', async () => {
    write('onboarding.json', { done: false })
    const l = start()
    assert.equal(gateIsOpen(), false)

    await l.invoke('auth:continue')
    assert.equal(gateIsOpen(), false, 'consent and setup are still ahead')
    assert.equal(l.overlayShown(), 0)
    await l.invoke('onboarding:later')
    assert.equal(gateIsOpen(), false, '"Set up later" never skips consent')
    assert.equal(l.overlayShown(), 0)
    await l.invoke('onboarding:agree')
    assert.equal(gateIsOpen(), true)
    assert.equal(l.overlayShown(), 1, 'the overlay shows once the gate opens')
    assert.equal(shortcuts.has(LAUNCHER_KEY), true, 'the launcher key registers')
    assert.deepEqual(l.trayLabels(), ['Open miyagi', 'Start a lesson', 'Show me around', 'Settings…', 'Hide miyagi overlays', 'Quit miyagi'])
    const gates = l.broadcasts.filter(([c]) => c === 'onboarding:gate').map(([, v]) => v)
    assert.deepEqual(gates.at(-1), { login: true, consent: true, setup: true, open: true }, 'feat:onboarding:gate carries the clean view')

    const again = relaunch()
    assert.equal(gateIsOpen(), false, 'the guest choice lasts one run')
    const got = (await again.invoke('onboarding:get')) as Get
    assert.equal(got.login, true)
    assert.equal(got.consent, true, 'consent is kept (prefs.consent), so it is not asked again')
    assert.deepEqual(got.gate, { login: false, consent: true, setup: true, open: false })
    assert.equal(again.overlayShown(), 0)
    assert.equal(shortcuts.has(LAUNCHER_KEY), false)
    assert.deepEqual(again.opened, ['library'], 'home opens at the login, setup already put off')
    assert.ok(!existsSync(join(dir, 'login.json')), 'no login.json is written')
    assert.deepEqual(readdirSync(dir).sort(), ['onboarding.json'])
  })

  test('a stored session, consent and setup done: the gate opens without any login screen', async () => {
    write('onboarding.json', { done: true, introSeen: true })
    writeSession(dir, supa.session({ sub: 'user-alice', email: 'alice@example.com', name: 'Alice Test' }))
    agreedBefore()
    const l = start()

    assert.equal(gateIsOpen(), true)
    const got = (await l.invoke('onboarding:get')) as Get
    assert.equal(got.login, false)
    assert.equal(got.flow, false)
    assert.deepEqual(got.gate, { login: true, consent: true, setup: true, open: true })
    assert.equal(l.overlayShown(), 1)
    assert.equal(shortcuts.has(LAUNCHER_KEY), true)
    assert.deepEqual(promptCalls, [])
  })

  test('a sign-out closes the gate: the overlay hides, the key goes, the tray shrinks', async () => {
    write('onboarding.json', { done: true, introSeen: true })
    writeSession(dir, supa.session({ sub: 'user-alice', email: 'alice@example.com', name: 'Alice Test' }))
    agreedBefore()
    const l = start()
    assert.equal(gateIsOpen(), true)
    await l.invoke('auth:sign-out')
    assert.equal(gateIsOpen(), false)
    assert.equal(shortcuts.has(LAUNCHER_KEY), false)
    assert.deepEqual(l.trayLabels(), ['Open miyagi', 'Quit miyagi'])
    assert.equal(((await l.invoke('onboarding:get')) as Get).login, true)
  })

  test('MIYAGI_SKIP_ONBOARDING=1 still opens everything at once (dev)', async () => {
    process.env.MIYAGI_SKIP_ONBOARDING = '1'
    const l = start()
    assert.equal(gateIsOpen(), true)
    assert.equal(l.overlayShown(), 1)
    assert.equal(shortcuts.has(LAUNCHER_KEY), true)
  })
})

describe('prompts come only from a setup click', () => {
  test('onboarding:prompt is invoked only from the renderer runAction click handlers', () => {
    const src = join(__dirname, '../src/renderer/src')
    const hits: string[] = []
    const walk = (d: string): void => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const p = join(d, e.name)
        if (e.isDirectory()) walk(p)
        else if (/\.tsx?$/.test(e.name) && !/web\.ts$/.test(e.name) && readFileSync(p, 'utf8').includes("'onboarding:prompt'")) hits.push(p.slice(src.length + 1).replaceAll('\\', '/'))
      }
    }
    walk(src)
    assert.deepEqual(hits, ['features/onboarding/store.ts'])
    const store = readFileSync(join(src, 'features/onboarding/store.ts'), 'utf8')
    const runAction = store.slice(store.indexOf('export async function runAction'), store.indexOf('// ---- the guided walk'))
    assert.equal(store.split("'onboarding:prompt'").length - 1, runAction.split("'onboarding:prompt'").length - 1, 'every prompt call sits in runAction')
  })
})
