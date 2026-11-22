/**
 * features/funnel.ts, offline: milestones are recorded once (earliest time), sent only when the switch is on, the gate
 * is open and the install is linked, in the exact contract shape, and nothing else ever leaves.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, test } from 'node:test'
import { createFunnel, type FunnelDeps } from '../src/main/features/funnel'
import { cleanState, funnelUrl, mark, MILESTONES, unsent } from '../src/main/features/funnel/core'

const HOST = 'https://cloud.test'
const TOKEN = 'mi_testinstalltokenFUNNEL'

type Call = { url: string; headers: Record<string, string>; body: { milestones: { name: string; at: string }[] } }

let dir: string
let calls: Call[]
let status: number
let on: boolean
let linked: string | undefined
let granted: boolean
let clock: Date

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'miyagi-funnel-'))
  calls = []
  status = 202
  on = true
  linked = '2026-11-22T10:05:00.000Z'
  granted = false
  clock = new Date('2026-11-22T10:00:00.000Z')
})
afterEach(() => rmSync(dir, { recursive: true, force: true }))

function funnel(over: Partial<FunnelDeps> = {}): ReturnType<typeof createFunnel> {
  return createFunnel({
    fetch: async (url, init) => {
      const headers: Record<string, string> = {}
      new Headers(init.headers).forEach((v, k) => (headers[k] = v))
      calls.push({ url, headers, body: JSON.parse(String(init.body)) })
      return new Response(status === 202 ? '{"ok":true}' : '{}', { status })
    },
    install: () => ({ token: TOKEN, host: HOST }),
    enabled: () => on,
    gateOpen: () => true,
    linkedAt: () => linked,
    permissionsGranted: () => granted,
    stateFile: join(dir, 'funnel', 'state.json'),
    now: () => clock,
    ...over
  })
}

const ready = (id = 'L1') => ({ type: 'lesson.ready', payload: { lesson: { id, outline: { count: 3 } } } })
const passed = (stepId: string, extra: Record<string, unknown> = {}) => ({ type: 'step.passed', payload: { stepId, ...extra } })
const complete = { type: 'card', payload: { kind: 'complete', result: { passed: 3, total: 3 } } }

test('the whole funnel, in order, with the exact request shape', async () => {
  const f = funnel()
  granted = true
  clock = new Date('2026-11-22T10:10:00.000Z')
  f.track(ready())
  clock = new Date('2026-11-22T10:12:00.000Z')
  f.track(passed('s1'))
  f.track(passed('s2'))
  clock = new Date('2026-11-22T10:20:00.000Z')
  f.track(complete)
  await f.tick()
  assert.equal(calls.length, 1)
  const c = calls[0]
  assert.equal(c.url, `${HOST}/v1/funnel`)
  assert.equal(c.headers.authorization, `Bearer ${TOKEN}`)
  assert.deepEqual(Object.keys(c.body), ['milestones'])
  assert.deepEqual(
    c.body.milestones.map((m) => m.name),
    [...MILESTONES]
  )
  const at = Object.fromEntries(c.body.milestones.map((m) => [m.name, m.at]))
  assert.equal(at.first_launch, '2026-11-22T10:00:00.000Z')
  assert.equal(at.signed_in, '2026-11-22T10:05:00.000Z')
  assert.equal(at.lesson_started, '2026-11-22T10:10:00.000Z')
  assert.equal(at.step_passed, '2026-11-22T10:12:00.000Z') // the first pass, not the second
  assert.equal(at.lesson_finished, '2026-11-22T10:20:00.000Z')
  for (const m of c.body.milestones) assert.deepEqual(Object.keys(m).sort(), ['at', 'name'])
})

test('nothing is sent with the switch off, the gate shut or no linked account; it is still recorded', async () => {
  on = false
  let f = funnel()
  await f.tick()
  assert.equal(calls.length, 0)
  on = true
  f = funnel({ gateOpen: () => false })
  await f.tick()
  assert.equal(calls.length, 0)
  linked = undefined
  f = funnel()
  await f.tick()
  assert.equal(calls.length, 0)
  const saved = cleanState(JSON.parse(readFileSync(join(dir, 'funnel', 'state.json'), 'utf8')))
  assert.equal(saved.at.first_launch, '2026-11-22T10:00:00.000Z')
  assert.equal(saved.at.signed_in, '2026-11-22T10:05:00.000Z') // from the earlier ticks that saw the link
})

test('MIYAGI_TELEMETRY=off stops sending for the run', async () => {
  await funnel({ off: 'off' }).tick()
  assert.equal(calls.length, 0)
})

test('a 202 is not sent again; a later milestone goes alone; first_launch keeps its first time across launches', async () => {
  let f = funnel()
  await f.tick()
  assert.equal(calls.length, 1)
  await f.tick()
  assert.equal(calls.length, 1)
  clock = new Date('2026-11-23T09:00:00.000Z')
  f = funnel() // the next launch
  f.track(ready('L2'))
  await f.tick()
  assert.equal(calls.length, 2)
  assert.deepEqual(calls[1].body.milestones, [{ name: 'lesson_started', at: '2026-11-23T09:00:00.000Z' }])
  assert.equal(f.state().at.first_launch, '2026-11-22T10:00:00.000Z')
})

test('a failed send retries next tick; a 404 stops for the run', async () => {
  status = 503
  const f = funnel()
  await f.tick()
  status = 202
  await f.tick()
  assert.equal(calls.length, 2)
  assert.deepEqual(unsent(f.state()), [])
  status = 404
  const g = funnel({ stateFile: join(dir, 'other.json') })
  await g.tick()
  await g.tick()
  assert.equal(calls.length, 3)
})

test('skipped steps and replays do not count', async () => {
  const f = funnel()
  f.track({ type: 'lesson.ready', payload: { replay: true, lesson: { id: 'L1' } } })
  assert.equal(f.state().at.lesson_started, undefined)
  f.track(ready())
  f.track(passed('s1', { skipped: true }))
  assert.equal(f.state().at.step_passed, undefined)
})

test('core: earliest time wins, bad state is dropped, only clean https endpoints', () => {
  const s = cleanState({ at: { first_launch: 'nope', step_passed: '2026-11-22T10:00:00Z', evil: '2026-11-22T10:00:00Z' }, sent: 'x' })
  assert.deepEqual(s, { at: { step_passed: '2026-11-22T10:00:00.000Z' }, sent: {} })
  assert.equal(mark(s, 'step_passed', '2026-11-22T11:00:00Z'), false)
  assert.equal(mark(s, 'step_passed', '2026-11-22T09:00:00Z'), true)
  assert.equal(s.at.step_passed, '2026-11-22T09:00:00.000Z')
  assert.equal(funnelUrl('https://miyagi-cloud.onrender.com/v1'), 'https://miyagi-cloud.onrender.com/v1/funnel')
  assert.equal(funnelUrl('http://evil.test'), undefined)
  assert.equal(funnelUrl('https://u:p@cloud.test'), undefined)
  assert.equal(funnelUrl(undefined), undefined)
})
