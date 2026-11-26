/**
 * The first-lesson walkthrough ("Show me around"), offline (lane app-onboarding-tour, Nov 25: on a fresh download the
 * Settings button did nothing and the tour never ran on the first launch).
 *
 *   rules     main/features/onboarding/tour.ts: when the tour is owed (a first run, not an upgrade), when it starts by
 *             itself, and that an explicit start is held while the launch gate is closed
 *   main      main/features/onboarding.ts over a temp userData: tourDue written on a first run, 'start' held until the
 *             gate opens then broadcast, 'auto' once per launch after the flow, 'seen' kept across launches,
 *             onboarding:get carries tour {open, seq, due}
 *   overlay   features/tips/tourStore.ts in the overlay window: every start broadcast opens it on the first mark, even
 *             when its state already read open (the dead-button regression), and a start it missed is caught from
 *             onboarding:get when its gate opens
 *   marks     features/tips/tourMarks.ts planMark: a mark whose target isn't on screen is skipped, never stalled on
 *   tips      features/tips/gate.ts setupSettled: "Set up later" frees the floor for tips, as done does
 * Run from app/: node --import tsx --import ./test/setup.mjs --test test/onboardingTour.test.ts
 */
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import type { MainContext } from '../src/main/context'
import onboarding from '../src/main/features/onboarding'
import { AUTO_TOUR_DELAY_MS, onGateOpened, shouldAutoTour, startDecision, tourDueAtLaunch } from '../src/main/features/onboarding/tour'
import { resetGateForTests, setGatePart } from '../src/main/gate'
import { resetPrefsForTests } from '../src/main/prefs'
import { setupSettled } from '../src/renderer/src/features/tips/gate'
import { planMark, TARGET_GRACE_MS, TOUR, type TourTarget } from '../src/renderer/src/features/tips/tourMarks'

// ---- rules ---------------------------------------------------------------------------------------------------------

describe('when the tour is owed and starts (main/features/onboarding/tour.ts)', () => {
  test('a first run makes it due; an upgrade (setup done on an older build) or a seen tour never does', () => {
    assert.equal(tourDueAtLaunch({ done: false }), true, 'fresh download')
    assert.equal(tourDueAtLaunch({ done: true }), false, 'upgrade: setup finished before tours were owed')
    assert.equal(tourDueAtLaunch({ done: false, later: true }), false, 'put off on an older build, no tourDue')
    assert.equal(tourDueAtLaunch({ done: true, tourDue: true }), true, 'owed from the first run, quit mid-tour')
    assert.equal(tourDueAtLaunch({ done: true, later: true, tourDue: true }), true, 'Set up later keeps it owed')
    assert.equal(tourDueAtLaunch({ done: false, tourSeen: true }), false)
    assert.equal(tourDueAtLaunch({ done: true, tourDue: true, tourSeen: true }), false)
  })

  test('the auto tour: due, unseen, gate open, once per launch, never quiet or skipped', () => {
    const ok = { due: true, seen: false, gateOpen: true, tried: false, skip: false, quiet: false }
    assert.equal(shouldAutoTour(ok), true)
    assert.equal(shouldAutoTour({ ...ok, due: false }), false)
    assert.equal(shouldAutoTour({ ...ok, seen: true }), false)
    assert.equal(shouldAutoTour({ ...ok, gateOpen: false }), false, 'never before sign-in, consent and setup (or Set up later)')
    assert.equal(shouldAutoTour({ ...ok, tried: true }), false)
    assert.equal(shouldAutoTour({ ...ok, skip: true }), false)
    assert.equal(shouldAutoTour({ ...ok, quiet: true }), false)
  })

  test('an explicit start runs now with the gate open, else waits for it', () => {
    assert.equal(startDecision({ gateOpen: true }), 'now')
    assert.equal(startDecision({ gateOpen: false }), 'hold')
    assert.equal(onGateOpened({ held: true }), 'start')
    assert.equal(onGateOpened({ held: false }), 'none')
  })
})

// ---- main ----------------------------------------------------------------------------------------------------------

type Run = { invoke: (channel: string, ...a: unknown[]) => Promise<unknown>; tours: unknown[]; raised: number }

function launch(dir: string): Run {
  const handlers = new Map<string, (...a: unknown[]) => unknown>()
  const run: Run = { invoke: async () => undefined, tours: [], raised: 0 }
  const win = { isDestroyed: () => false, setTitle: () => undefined, on: () => undefined, once: () => undefined, show: () => undefined, focus: () => undefined }
  const ctx = {
    app: { isPackaged: false, getPath: () => dir, getLoginItemSettings: () => ({ wasOpenedAtLogin: false }), relaunch: () => undefined, quit: () => undefined },
    overlay: { isDestroyed: () => false, webContents: { once: () => undefined }, showInactive: () => undefined, moveTop: () => undefined },
    raise: () => void (run.raised += 1),
    broadcast: (c: string, p: unknown) => {
      if (c === 'onboarding:tour') run.tours.push(p)
    },
    handle: (c: string, fn: (...a: unknown[]) => unknown) => handlers.set(c, fn),
    openWindow: () => win,
    appWindow: () => undefined
  } as unknown as MainContext
  onboarding.setup(ctx)
  run.invoke = async (c, ...a) => {
    const fn = handlers.get(c)
    if (!fn) throw new Error(`no handler ${c}`)
    return fn(...a)
  }
  return run
}

const openGate = (): void => {
  setGatePart('login', true)
  setGatePart('consent', true)
  setGatePart('setup', true)
}
const flagOf = (dir: string): Record<string, unknown> => JSON.parse(readFileSync(join(dir, 'onboarding.json'), 'utf8'))
type Got = { tour: { open: boolean; seq: number; due: boolean } }

let dir: string
let skipBefore: string | undefined
let quietBefore: string | undefined
beforeEach(() => {
  skipBefore = process.env.MIYAGI_SKIP_ONBOARDING
  quietBefore = process.env.MIYAGI_QUIET_LAUNCH
  delete process.env.MIYAGI_SKIP_ONBOARDING
  delete process.env.MIYAGI_QUIET_LAUNCH
  dir = mkdtempSync(join(tmpdir(), 'miyagi-tour-'))
  resetGateForTests()
  resetPrefsForTests()
})
afterEach(() => {
  if (skipBefore === undefined) delete process.env.MIYAGI_SKIP_ONBOARDING
  else process.env.MIYAGI_SKIP_ONBOARDING = skipBefore
  if (quietBefore === undefined) delete process.env.MIYAGI_QUIET_LAUNCH
  else process.env.MIYAGI_QUIET_LAUNCH = quietBefore
  mock.timers.reset()
  resetGateForTests()
  resetPrefsForTests()
  rmSync(dir, { recursive: true, force: true })
})

describe('main: the tour on a fresh install (main/features/onboarding.ts)', () => {
  test('a first launch (no Application Support/miyagi) owes the tour and says so in onboarding:get', async () => {
    const run = launch(dir)
    assert.equal(existsSync(join(dir, 'onboarding.json')), true)
    assert.equal(flagOf(dir).tourDue, true)
    assert.equal(flagOf(dir).done, false, 'owing the tour never marks setup done')
    const got = (await run.invoke('onboarding:get')) as Got
    assert.deepEqual(got.tour, { open: false, seq: 0, due: true })
  })

  test("an upgrade (setup done before) is not owed one: 'auto' does nothing", async () => {
    writeFileSync(join(dir, 'onboarding.json'), JSON.stringify({ done: true, at: '2026-11-20T00:00:00.000Z' }))
    const run = launch(dir)
    openGate()
    assert.equal(await run.invoke('onboarding:tour', 'auto'), false)
    assert.equal(flagOf(dir).tourDue, undefined)
  })

  test("Settings' Show me around: opens at once with the gate open, every time, and raises the overlay", async () => {
    const run = launch(dir)
    openGate()
    await run.invoke('onboarding:tour', 'start')
    assert.deepEqual(run.tours.at(-1), { open: true, seq: 1 })
    assert.ok(run.raised >= 1)
    assert.equal(((await run.invoke('onboarding:get')) as Got).tour.open, true)
    // A second press while main thinks it is open still broadcasts a start (the overlay restarts at mark 1).
    await run.invoke('onboarding:tour', 'start')
    assert.deepEqual(run.tours.at(-1), { open: true, seq: 2 })
    await run.invoke('onboarding:tour', 'end')
    assert.deepEqual(run.tours.at(-1), { open: false, seq: 2 })
    assert.equal(((await run.invoke('onboarding:get')) as Got).tour.open, false)
  })

  test("You're ready's Show me around before the gate opens: held, then shown the moment setup is done", async () => {
    const run = launch(dir)
    setGatePart('login', true)
    setGatePart('consent', true)
    await run.invoke('onboarding:tour', 'start')
    assert.equal(run.tours.length, 0, 'the overlay is hidden behind the gate: nothing yet')
    await run.invoke('onboarding:done') // finishFlow → markDone opens the setup part
    assert.deepEqual(run.tours.at(-1), { open: true, seq: 1 })
  })

  test("the first run's hand-off to home starts it by itself once, after the delay; a second ask does nothing", async () => {
    mock.timers.enable({ apis: ['setTimeout'] })
    const run = launch(dir)
    openGate()
    assert.equal(await run.invoke('onboarding:tour', 'auto'), true)
    assert.equal(run.tours.length, 0)
    mock.timers.tick(AUTO_TOUR_DELAY_MS)
    assert.deepEqual(run.tours.at(-1), { open: true, seq: 1 })
    assert.equal(await run.invoke('onboarding:tour', 'auto'), false, 'once per launch')
  })

  test("'auto' before the gate opens (setup still ahead) does nothing", async () => {
    const run = launch(dir)
    setGatePart('login', true)
    assert.equal(await run.invoke('onboarding:tour', 'auto'), false)
    assert.equal(run.tours.length, 0)
  })

  test('a sign-out before the auto tour runs drops it', async () => {
    mock.timers.enable({ apis: ['setTimeout'] })
    const run = launch(dir)
    openGate()
    assert.equal(await run.invoke('onboarding:tour', 'auto'), true)
    setGatePart('login', false)
    mock.timers.tick(AUTO_TOUR_DELAY_MS)
    assert.equal(run.tours.length, 0)
  })

  test('seen (done, skipped, or declined on You\'re ready) is kept: the next launch owes nothing', async () => {
    const run = launch(dir)
    openGate()
    await run.invoke('onboarding:tour', 'seen')
    assert.equal(flagOf(dir).tourSeen, true)
    assert.equal(flagOf(dir).tourDue, false)
    assert.equal(await run.invoke('onboarding:tour', 'auto'), false)

    resetGateForTests()
    const again = launch(dir)
    openGate()
    assert.equal(((await again.invoke('onboarding:get')) as Got).tour.due, false)
    assert.equal(await again.invoke('onboarding:tour', 'auto'), false)
  })

  test('quit mid-tour (never seen): the next launch still owes it, even after setup was done', async () => {
    const first = launch(dir)
    openGate()
    await first.invoke('onboarding:done')
    resetGateForTests()
    const second = launch(dir)
    openGate()
    assert.equal(((await second.invoke('onboarding:get')) as Got).tour.due, true)
  })

  test('MIYAGI_SKIP_ONBOARDING=1 never starts it by itself', async () => {
    process.env.MIYAGI_SKIP_ONBOARDING = '1'
    const run = launch(dir)
    assert.equal(await run.invoke('onboarding:tour', 'auto'), false)
  })
})

// ---- marks ---------------------------------------------------------------------------------------------------------

describe('the tour never stalls on a missing target (features/tips/tourMarks.ts planMark)', () => {
  const all = (): boolean => true
  const none = (): boolean => false
  test('a present target shows; the island is always there', () => {
    assert.deepEqual(planMark(0, none, 0), { kind: 'show', index: 0 })
    assert.deepEqual(planMark(1, all, 0), { kind: 'show', index: 1 })
  })
  test('a missing target waits for the panel, then skips to the next mark whose target is there', () => {
    const only = (t: TourTarget): boolean => t === 'help'
    assert.deepEqual(planMark(1, only, 0), { kind: 'wait' })
    assert.deepEqual(planMark(1, only, TARGET_GRACE_MS), { kind: 'skip', to: TOUR.findIndex((m) => m.target === 'help') })
  })
  test('nothing left to point at ends the tour; past the last mark ends it', () => {
    assert.deepEqual(planMark(1, none, TARGET_GRACE_MS), { kind: 'end' })
    assert.deepEqual(planMark(TOUR.length, all, 0), { kind: 'end' })
  })
})

// ---- tips ----------------------------------------------------------------------------------------------------------

describe('tips wait for setup, done or put off (features/tips/gate.ts setupSettled)', () => {
  test('done, or the gate\'s setup part (Set up later), frees the floor', () => {
    assert.equal(setupSettled({ done: true }), true)
    assert.equal(setupSettled({ done: false, gate: { login: true, consent: true, setup: true, open: true } }), true)
    assert.equal(setupSettled({ done: false, gate: { setup: false } }), false)
    assert.equal(setupSettled({ done: false }), false)
    assert.equal(setupSettled(undefined), false)
  })
})

// ---- overlay -------------------------------------------------------------------------------------------------------

describe('the overlay applies every start (features/tips/tourStore.ts)', () => {
  // The renderer in Node: a fake bridge (main), the overlay route, Vite-only modules stubbed.
  const stubs = mkdtempSync(join(tmpdir(), 'tour-store-'))
  writeFileSync(join(stubs, 'scenarios.mjs'), 'export const scenarios = {}')
  const SCENARIOS = pathToFileURL(join(stubs, 'scenarios.mjs')).href
  registerHooks({
    resolve(specifier, context, next) {
      if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
      return next(specifier, context)
    }
  })
  const invoked: [string, unknown][] = []
  const listeners = new Map<string, Set<(p?: unknown) => void>>()
  /** onboarding:get's answer: the gate is open and main already broadcast start #3 before this overlay listened. */
  const tut = {
    platform: { os: 'darwin', keys: {}, pillTop: 0 },
    onEvent: () => () => {},
    onStatus: () => () => {},
    on: () => () => {},
    emit: () => {},
    ready: () => {},
    send: () => {},
    invoke: (channel: string, arg?: unknown): Promise<unknown> => {
      invoked.push([channel, arg])
      if (channel === 'onboarding:get') return Promise.resolve({ gate: { login: true, consent: true, setup: true, open: true }, tour: { open: true, seq: 3, due: true } })
      return Promise.resolve(true)
    },
    onFeature: (channel: string, cb: (p?: unknown) => void) => {
      if (!listeners.has(channel)) listeners.set(channel, new Set())
      listeners.get(channel)!.add(cb)
      return () => listeners.get(channel)!.delete(cb)
    }
  }
  const broadcast = (channel: string, p?: unknown): void => listeners.get(channel)?.forEach((cb) => cb(p))
  const g = globalThis as Record<string, unknown>
  const before = { window: g.window, document: g.document, location: g.location }
  g.window = { tut, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
  g.document = { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined } }
  g.location = { hash: '#/overlay', search: '', pathname: '/' }
  const store = require('../src/renderer/src/features/tips/tourStore') as typeof import('../src/renderer/src/features/tips/tourStore')
  const { useTour } = store
  const settle = (): Promise<void> => new Promise((r) => setTimeout(r, 20))

  test('this window draws the tour', () => {
    assert.equal(store.drawsTour, true)
  })

  test('a start main broadcast before the overlay listened is caught from onboarding:get when its gate opens', async () => {
    await settle()
    assert.deepEqual(useTour.getState(), { open: true, index: 0 })
  })

  test('a start while it already reads open (a stuck "open") restarts it on the first mark', () => {
    useTour.setState({ open: true, index: 3 })
    broadcast('onboarding:tour', { open: true, seq: 4 })
    assert.deepEqual(useTour.getState(), { open: true, index: 0 })
  })

  test('end closes it; Skip/Done tell main seen and end; a lesson closes it without seen', () => {
    broadcast('onboarding:tour', { open: false, seq: 4 })
    assert.equal(useTour.getState().open, false)

    useTour.setState({ open: true, index: 2 })
    invoked.length = 0
    store.endTour()
    assert.deepEqual(invoked.map(([c, a]) => `${c}:${a}`), ['onboarding:tour:seen', 'onboarding:tour:end'])

    useTour.setState({ open: true, index: 1 })
    invoked.length = 0
    store.endTour({ seen: false })
    assert.deepEqual(invoked.map(([c, a]) => `${c}:${a}`), ['onboarding:tour:end'])
  })

  test('startTour opens it here at once and asks main (which tells every window)', () => {
    invoked.length = 0
    store.startTour()
    assert.deepEqual(useTour.getState(), { open: true, index: 0 })
    assert.deepEqual(invoked.map(([c, a]) => `${c}:${a}`), ['onboarding:tour:start'])
  })

  test('skipping past the last mark ends it', () => {
    store.goToMark(TOUR.length)
    assert.equal(useTour.getState().open, false)
  })

  test('applyTourSignal: only open === true opens; a close while closed changes nothing', () => {
    assert.deepEqual(store.applyTourSignal({ open: false, index: 0 }, { open: true }), { open: true, index: 0 })
    assert.deepEqual(store.applyTourSignal({ open: true, index: 2 }, { open: 'yes' }), { open: false, index: 0 })
    const cur = { open: false, index: 0 }
    assert.equal(store.applyTourSignal(cur, undefined), cur)
  })

  test('cleanup', () => {
    g.window = before.window
    g.document = before.document
    g.location = before.location
    rmSync(stubs, { recursive: true, force: true })
  })
})
