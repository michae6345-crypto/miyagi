/**
 * features/buddy wire.ts end to end with a fake Electron bridge, offline: engine.hello sends bon.import once per Mac and
 * bon.get (only what the hello lists, through bridge.send), `bon` moves the count, and a ui-v4 step.passed grows bon only
 * when `counted` (with the level-up moment once); an engine without bon keeps the local count.
 * Run: node --import tsx --import ./test/setup.mjs --test test/bonWire.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { registerHooks } from 'node:module'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { beforeEach, describe, test } from 'node:test'
import { pathToFileURL } from 'node:url'

// Vite-only modules (import.meta.glob scenarios, the feature registry, assets) resolve to small stand-ins.
const dir = mkdtempSync(join(tmpdir(), 'bon-wire-'))
const stub = (name: string, source: string): string => (writeFileSync(join(dir, name), source), pathToFileURL(join(dir, name)).href)
const EMPTY = stub('empty.mjs', 'export const scenarios = {}\nexport const defineFeature = (f) => f\nexport default ""')
registerHooks({
  resolve(specifier, context, next) {
    if (/(^|\/)mock\/scenarios$/.test(specifier) || (context.parentURL?.includes('/src/renderer/') && /(^|\/)registry$/.test(specifier))) return { url: EMPTY, shortCircuit: true }
    if (/\.(svg|png|jpe?g|webp|css|mp3|wav|woff2?)(\?.*)?$|\?(raw|url|inline)$/.test(specifier)) return { url: EMPTY, shortCircuit: true }
    return next(specifier, context)
  }
})

const sends: { type: string; payload: Record<string, unknown> }[] = []
const data: Record<string, string> = {}
const storage = { getItem: (k: string) => (k in data ? data[k] : null), setItem: (k: string, v: string) => void (data[k] = v), removeItem: (k: string) => void delete data[k] }
// The count growth.ts kept before the engine kept one: two passes on this Mac.
data['miyagi.buddy.growth'] = JSON.stringify({ steps: 2, seen: ['old:s1', 'old:s2'] })
const g = globalThis as unknown as Record<string, unknown>
const noop = (): (() => void) => () => {}
const tut = {
  platform: { os: 'darwin', keys: { ptt: 'fn ⌃' }, pillTop: 0 },
  onEvent: noop,
  onStatus: noop,
  on: noop,
  onFeature: () => () => {},
  emit: () => {},
  ready: () => {},
  send: (m: { type: string; payload: Record<string, unknown> }) => void sends.push(m),
  invoke: (): Promise<unknown> => Promise.resolve(null)
}
g.window = { tut, localStorage: storage, location: { search: '' }, devicePixelRatio: 2, innerWidth: 1440, innerHeight: 900, addEventListener: () => {}, removeEventListener: () => {}, matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }) }
g.document = { documentElement: { dataset: { route: 'overlay' } }, getElementById: () => ({}), createElement: () => ({}), head: { prepend: () => undefined }, addEventListener: () => {}, hidden: false }
g.location = { search: '' }

const { dispatch } = require('../src/renderer/src/core/bus') as typeof import('../src/renderer/src/core/bus')
const { useLesson } = require('../src/renderer/src/core/lesson') as typeof import('../src/renderer/src/core/lesson')
require('../src/renderer/src/features/buddy/wire')
const { useGrowth } = require('../src/renderer/src/features/buddy/growth') as typeof import('../src/renderer/src/features/buddy/growth')
const { useTalk } = require('../src/renderer/src/features/buddy/talk') as typeof import('../src/renderer/src/features/buddy/talk')

const send = (type: string, payload: unknown): void => dispatch({ type, payload } as never)
const hello = (capabilities: string[]): void => send('engine.hello', { version: 't', contract: '2026-11-20', capabilities })
const bonSends = (): { type: string; payload: Record<string, unknown> }[] => sends.filter((m) => m.type.startsWith('bon.'))
const V4 = ['progress.get', 'bon.get', 'bon.import']

beforeEach(() => {
  sends.length = 0
})

describe('bon wire (engine.hello, bon, step.passed)', () => {
  test('an engine without bon: nothing sent, every pass counts locally', () => {
    hello(['progress.get'])
    assert.deepEqual(bonSends(), [])
    useLesson.setState({ lesson: { id: 'L1' } as never })
    send('step.passed', { stepId: 's1' })
    send('step.passed', { stepId: 's2', skipped: true })
    assert.equal(useGrowth.getState().steps, 3)
    assert.equal(data['miyagi.buddy.imported'], undefined)
  })

  test('a ui-v4 engine: bon.import once with the local count, then bon.get', () => {
    hello(V4)
    assert.deepEqual(bonSends(), [
      { type: 'bon.import', payload: { steps: 3, seen: ['old:s1', 'old:s2', 'L1:s1'] } },
      { type: 'bon.get', payload: {} }
    ])
    sends.length = 0
    hello(V4)
    assert.deepEqual(bonSends(), [{ type: 'bon.get', payload: {} }], 'a reconnect asks again but never imports twice')
  })

  test('bon moves the count quietly', () => {
    const grew = useGrowth.getState().grew
    send('bon', { steps: 24, level: 4, name: 'Sapling', next: { level: 5, name: 'Budding', at: 25, left: 1 }, fraction: 0.8889 })
    assert.equal(useGrowth.getState().steps, 24)
    assert.equal(useGrowth.getState().level, 4)
    assert.equal(useGrowth.getState().grew, grew)
  })

  test('only a counted pass grows bon, and it plays the level-up once', () => {
    const grew = useGrowth.getState().grew
    send('step.passed', { stepId: 's2', key: 'L1:s2' })
    send('step.passed', { stepId: 's3', key: 'L1:s3', counted: false })
    assert.equal(useGrowth.getState().steps, 24, 'passes the engine did not count')
    send('step.passed', { stepId: 's4', key: 'L1:s4', counted: true })
    assert.equal(useGrowth.getState().steps, 25)
    assert.equal(useGrowth.getState().level, 5)
    assert.equal(useGrowth.getState().grew, grew + 1)
    assert.match(String(useTalk.getState().say), /Budding/, 'bon says its new level')
    send('bon', { steps: 25, level: 5, name: 'Budding', grew: true, lastKey: 'L1:s4' })
    assert.equal(useGrowth.getState().steps, 25)
    assert.equal(useGrowth.getState().grew, grew + 1, 'the push after it is quiet')
  })
})
