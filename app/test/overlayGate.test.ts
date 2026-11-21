/**
 * Lane overlay-gate (app/agents/overlay-gate.md): the renderer's sign-in gate backstop, offline, no window.
 *
 *   store       core/gate.ts starts closed; an onboarding:get answer without `gate` (an older main) opens it; one with
 *               gate.open false keeps it closed; feat:onboarding:gate opens and closes it again.
 *   regression  while it is closed the overlay draws nothing (Overlay renders null), the tips loop and its STARTUP_MS
 *               clock never start, errors:crash-pending is never asked, progress never sends progress.get or asks for
 *               caps, and the update and crash cards never activate. Open, each behaves as before.
 *
 * The renderer runs in Node: window.tut is a fake bridge, and the Vite-only modules (core/registry's import.meta.glob,
 * mock/scenarios, asset imports) and core/Island resolve to small stand-ins written to a temp folder.
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'
import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// ---- stand-ins for the Vite-only modules ---------------------------------------------------------------------------
const dir = mkdtempSync(join(tmpdir(), 'overlay-gate-'))
const stub = (name: string, source: string): string => {
  writeFileSync(join(dir, name), source)
  return pathToFileURL(join(dir, name)).href
}
const REGISTRY = stub(
  'registry.mjs',
  [
    'export const defineFeature = (f) => f',
    'export const getOverlayLayers = () => globalThis.__gateLayers ?? []',
    'export const getIslandModes = () => []',
    'export const getFeatures = () => []',
    'export const getFeatureWindows = () => []',
    'export const getAppWindows = () => []'
  ].join('\n')
)
const SCENARIOS = stub('scenarios.mjs', 'export const scenarios = {}')
const ASSET = stub('asset.mjs', 'export default ""')
const ISLAND = stub('island.mjs', 'export const Island = () => "ISLAND"')
registerHooks({
  resolve(specifier, context, next) {
    const parent = context.parentURL ?? ''
    if (parent.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier)) return { url: REGISTRY, shortCircuit: true }
    if (parent.endsWith('/core/Overlay.tsx') && specifier === './Island') return { url: ISLAND, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: ASSET, shortCircuit: true }
    if (/(^|\/)mock\/scenarios$/.test(specifier)) return { url: SCENARIOS, shortCircuit: true }
    return next(specifier, context)
  }
})

// ---- a fake bridge (main) -------------------------------------------------------------------------------------------
type Deferred = { resolve: (v: unknown) => void; reject: (e: unknown) => void }
const invoked: string[] = []
const sent: string[] = []
const feature = new Map<string, Set<(p?: unknown) => void>>()
/** onboarding:get answers wait here until a test settles them. */
const onboardingAsks: Deferred[] = []

const tut = {
  platform: { os: 'darwin', keys: {}, pillTop: 0 },
  onEvent: () => () => {},
  onStatus: () => () => {},
  on: () => () => {},
  emit: () => {},
  ready: () => {},
  send: (c: { type: string }) => {
    sent.push(c.type)
  },
  invoke: (channel: string): Promise<unknown> => {
    invoked.push(channel)
    if (channel === 'onboarding:get') return new Promise((resolve, reject) => onboardingAsks.push({ resolve, reject }))
    if (channel === 'errors:crash-pending') return Promise.resolve({ report: 'miyagi crash report' })
    if (channel === 'progress:caps') return Promise.resolve({ progress: true, review: false, library: false })
    return Promise.resolve(null)
  },
  onFeature: (channel: string, cb: (p?: unknown) => void) => {
    if (!feature.has(channel)) feature.set(channel, new Set())
    feature.get(channel)!.add(cb)
    return () => feature.get(channel)!.delete(cb)
  }
}
const broadcast = (channel: string, payload?: unknown): void => feature.get(channel)?.forEach((cb) => cb(payload))

const g = globalThis as Record<string, unknown>
g.window = { tut, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
// The overlay window: progress/store.ts looks for a due review only in the window that draws the island.
g.document = { documentElement: { dataset: { route: 'overlay' } } }
g.location = { hash: '#/overlay', search: '', pathname: '/' }
// tsx compiles the renderer's JSX in classic mode here (app/tsconfig.json only lists references): React.createElement.
g.React = require('react')

const tick = (ms = 0): Promise<void> => new Promise((r) => setTimeout(r, ms))
/** progress/store.ts REVIEW_CHECK_MS (1500) and a margin. */
const REVIEW_WAIT = 1700

// ---- the modules under test (required after the fakes are in place) -----------------------------------------------
const GATE = require.resolve('../src/renderer/src/core/gate')
const gate = require(GATE) as typeof import('../src/renderer/src/core/gate')
const { Overlay } = require('../src/renderer/src/core/Overlay') as typeof import('../src/renderer/src/core/Overlay')
const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const tips = require('../src/renderer/src/features/tips/gate') as typeof import('../src/renderer/src/features/tips/gate')
const updates = require('../src/renderer/src/features/updates/index') as typeof import('../src/renderer/src/features/updates/index')
const { useUpdates } = require('../src/renderer/src/features/updates/store') as typeof import('../src/renderer/src/features/updates/store')
const errors = require('../src/renderer/src/features/errors/index') as typeof import('../src/renderer/src/features/errors/index')
const { useErrors } = require('../src/renderer/src/features/errors/store') as typeof import('../src/renderer/src/features/errors/store')
const progress = require('../src/renderer/src/features/progress/index') as typeof import('../src/renderer/src/features/progress/index')
const { useProgress } = require('../src/renderer/src/features/progress/store') as typeof import('../src/renderer/src/features/progress/store')

const LAYOUT = { origin: { x: 0, y: 0 }, width: 1440, height: 900, workArea: { x: 0, y: 32, width: 1440, height: 868 } }
g.__gateLayers = [{ id: 'probe', z: 10, Component: () => 'LAYER' }]
const overlayHtml = (): string => renderToStaticMarkup(createElement(Overlay, { layout: LAYOUT }))

type Mode = { id: string; useActive: () => boolean }
const modeOf = (f: { islandModes?: Mode[] }, id: string): Mode => f.islandModes!.find((m) => m.id === id)!
function Probe({ use }: { use: () => boolean }): ReactNode {
  return String(use())
}
/** A mode's useActive, rendered once (a Node render reads each zustand store's initial state). */
const active = (m: Mode): boolean => renderToStaticMarkup(createElement(Probe, { use: m.useActive })) === 'true'

// Everything else wants each card: an update with its install steps asked for, a kept crash report, no lesson.
Object.assign(useUpdates.getInitialState(), { view: { phase: 'ready', current: '0.1.0', latest: { version: '9.9.9', notes: [], host: 'example.test' } }, steps: true })
Object.assign(useErrors.getInitialState(), { crash: { report: 'kept' } })
Object.assign(useProgress.getInitialState(), { review: { item: { label: 'Loops' }, due: 1 } })
const updCard = modeOf(updates.default as never, 'upd-card')
const crashCard = modeOf(errors.default as never, 'err-crash')
const reviewCard = modeOf(progress.default as never, 'review')
const tipsOn = (gateOpen: boolean): boolean => tips.tipsRunning({ enabled: true, off: false, allSeen: false, gateOpen })

describe('overlay gate: the launch surfaces (regression)', () => {
  test('closed before main answers: nothing draws, asks or schedules', async () => {
    await tick()
    assert.deepEqual(gate.useGate.getState(), { open: false, known: false })
    assert.ok(onboardingAsks.length >= 1, 'main was asked (other features ask onboarding:get too)')
    assert.equal(overlayHtml(), '', 'Overlay renders null')
    assert.equal(tipsOn(false), false, 'no tips loop, so no STARTUP_MS clock')
    assert.equal(tips.floorFree(true, false), false)
    assert.equal(active(updCard), false, 'no update card')
    assert.equal(active(crashCard), false, 'no crash card')
    assert.equal(active(reviewCard), false, 'no review reminder')

    // The engine says hello before the gate opens (it connects before whenReady).
    dispatch({ type: 'engine.hello', payload: { version: 't', contract: 't', capabilities: ['progress.get'] } } as never)
    await tick(REVIEW_WAIT)
    assert.ok(!invoked.includes('errors:crash-pending'), 'no crash ask')
    assert.ok(!invoked.includes('progress:caps'), 'no caps ask')
    assert.ok(!sent.includes('progress.get'), 'no progress.get')
  })

  test('main answers with a closed gate: still nothing', async () => {
    for (const a of onboardingAsks.splice(0)) a.resolve({ done: false, introSeen: true, gate: { login: false, setup: false, open: false } })
    await tick()
    assert.deepEqual(gate.useGate.getState(), { open: false, known: true })
    assert.equal(overlayHtml(), '')
    await tick(REVIEW_WAIT)
    assert.ok(!invoked.includes('errors:crash-pending'))
    assert.ok(!sent.includes('progress.get'))
  })

  test('open: everything behaves as before', async () => {
    broadcast('onboarding:gate', { login: true, setup: true, open: true })
    assert.equal(gate.useGate.getState().open, true)
    const html = overlayHtml()
    assert.match(html, /LAYER/, 'layers draw')
    assert.match(html, /ISLAND/, 'the island draws')
    assert.equal(tipsOn(true), true)
    assert.equal(tips.floorFree(true, true), true)
    assert.equal(tips.floorFree(false, true), false, 'first-run setup still has the floor')
    assert.equal(active(updCard), true)
    assert.equal(active(crashCard), true)
    assert.equal(active(reviewCard), true)
    await tick()
    assert.equal(invoked.filter((c) => c === 'errors:crash-pending').length, 1, 'crash asked once the gate opened')
    assert.equal(useErrors.getState().crash?.report, 'miyagi crash report')
    assert.ok(invoked.includes('progress:caps'), 'the early hello is answered now')
    await tick(REVIEW_WAIT)
    assert.equal(sent.filter((t) => t === 'progress.get').length, 1, 'the launch review check ran')
  })

  test('closed again (sign-out): nothing draws; opening again never re-asks', () => {
    broadcast('onboarding:gate', { login: false, setup: true, open: false })
    assert.equal(overlayHtml(), '')
    assert.equal(active(updCard), false)
    assert.equal(active(crashCard), false)
    assert.equal(active(reviewCard), false)
    broadcast('onboarding:gate', { login: true, setup: true, open: true })
    assert.equal(invoked.filter((c) => c === 'errors:crash-pending').length, 1)
  })
})

describe('updates: updCardActive', () => {
  test('gate closed: never, whatever else is true', () => {
    assert.equal(updates.updCardActive({ gateOpen: false, want: true, idle: true, steps: true, settled: true }), false)
    assert.equal(updates.updCardActive({ gateOpen: false, want: true, idle: true, steps: false, settled: true }), false)
  })
  test('gate open: as before', () => {
    assert.equal(updates.updCardActive({ gateOpen: true, want: true, idle: true, steps: true, settled: false }), true)
    assert.equal(updates.updCardActive({ gateOpen: true, want: true, idle: false, steps: true, settled: false }), false)
    assert.equal(updates.updCardActive({ gateOpen: true, want: true, idle: true, steps: false, settled: true }), true)
    assert.equal(updates.updCardActive({ gateOpen: true, want: true, idle: true, steps: false, settled: false }), false)
  })
})

describe('core/gate store', () => {
  /** A second copy of core/gate.ts with its own store and its own ask (CommonJS: drop it from the cache). */
  const fresh = async (): Promise<typeof gate> => {
    delete require.cache[GATE]
    const m = require(GATE) as typeof gate
    await tick()
    return m
  }

  test('parsing: only open === true opens; no gate field is an older main (open)', () => {
    assert.equal(gate.gateFromAnswer({ done: true, introSeen: true }), true)
    assert.equal(gate.gateFromAnswer({ done: true, gate: { open: true } }), true)
    assert.equal(gate.gateFromAnswer({ done: true, gate: { open: false } }), false)
    assert.equal(gate.gateFromAnswer({ done: true, gate: { open: 'true' } }), false)
    assert.equal(gate.gateFromAnswer({ done: true, gate: null }), false)
    assert.equal(gate.gateFromAnswer(null), false)
    assert.equal(gate.gateFromBroadcast({ open: true }), true)
    assert.equal(gate.gateFromBroadcast({ open: 1 }), false)
    assert.equal(gate.gateFromBroadcast('open'), false)
    assert.equal(gate.gateFromBroadcast(undefined), false)
  })

  test('starts closed; an answer without gate opens it (compat)', async () => {
    const m = await fresh()
    assert.deepEqual(m.useGate.getState(), { open: false, known: false })
    onboardingAsks.at(-1)!.resolve({ done: true, introSeen: true })
    await tick()
    assert.deepEqual(m.useGate.getState(), { open: true, known: true })
  })

  test('{gate:{open:false}} keeps it closed; broadcasts open and close it', async () => {
    const m = await fresh()
    onboardingAsks.at(-1)!.resolve({ done: false, gate: { login: false, setup: false, open: false } })
    await tick()
    assert.deepEqual(m.useGate.getState(), { open: false, known: true })
    broadcast('onboarding:gate', { login: true, setup: true, open: true })
    assert.equal(m.useGate.getState().open, true)
    broadcast('onboarding:gate', { login: false, setup: true, open: false })
    assert.equal(m.useGate.getState().open, false)
    broadcast('onboarding:gate', { open: 'yes' })
    assert.equal(m.useGate.getState().open, false, 'malformed reads closed')
  })

  test('a broadcast outranks an answer that lands after it', async () => {
    const m = await fresh()
    broadcast('onboarding:gate', { login: false, setup: false, open: false })
    onboardingAsks.at(-1)!.resolve({ done: true }) // late, and shaped like an older main: would read open
    await tick()
    assert.deepEqual(m.useGate.getState(), { open: false, known: true })
  })

  test('onGateOpen runs on each opening, onGateClose on each closing', async () => {
    const m = await fresh()
    let opened = 0
    let closed = 0
    m.onGateOpen(() => opened++)
    m.onGateClose(() => closed++)
    assert.equal(opened, 0)
    broadcast('onboarding:gate', { open: true })
    broadcast('onboarding:gate', { open: true })
    broadcast('onboarding:gate', { open: false })
    broadcast('onboarding:gate', { open: true })
    assert.deepEqual([opened, closed], [2, 1])
  })
})
