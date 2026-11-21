/**
 * Telemetry core (main/features/telemetry/core.ts): allowlisted props, the endpoint, crashes, lesson counts, batching.
 * No Electron, no network. Run from app/: node --import tsx --import ./test/setup.mjs --test test/telemetryCore.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  Batcher,
  body,
  cleanProps,
  crashEvent,
  EVENT_NAMES,
  EVENT_PROPS,
  makeEvent,
  MAX_BYTES,
  MAX_EVENTS,
  newLines,
  newTrack,
  PROP_KEYS,
  resultFor,
  telemetryUrl,
  usageEvent,
  type SendResult,
  type TelemetryEvent
} from '../src/main/features/telemetry/core'

test('telemetryUrl: the token host plus /v1/events; MIYAGI_TELEMETRY=off turns it off; nothing without a host', () => {
  assert.equal(telemetryUrl(undefined, 'https://cloud.example.com'), 'https://cloud.example.com/v1/events')
  assert.equal(telemetryUrl(undefined, 'https://cloud.example.com/'), 'https://cloud.example.com/v1/events')
  assert.equal(telemetryUrl(undefined, 'https://cloud.example.com/v1'), 'https://cloud.example.com/v1/events')
  assert.equal(telemetryUrl('', 'https://cloud.example.com'), 'https://cloud.example.com/v1/events')
  assert.equal(telemetryUrl('off', 'https://cloud.example.com'), undefined)
  assert.equal(telemetryUrl('0', 'https://cloud.example.com'), undefined)
  assert.equal(telemetryUrl(undefined, undefined), undefined)
  assert.equal(telemetryUrl(undefined, 'http://evil.example.com'), undefined) // plain http only for this Mac
  assert.equal(telemetryUrl(undefined, 'http://127.0.0.1:8000'), 'http://127.0.0.1:8000/v1/events')
  assert.equal(telemetryUrl(undefined, 'https://u:p@t.example.com'), undefined)
})

/**
 * Every prop key the app can send. The cloud keeps a prop only when its EVENT_PROP_KEYS (cloud/app.py) lists it, so a
 * change here needs the same change there (a Cloud request in app/agents/telemetry.md). This pin makes that visible.
 */
const WIRE_PROP_KEYS = ['already', 'app_version', 'arch', 'built_by', 'kind', 'minutes', 'mode', 'os', 'passed', 'reason', 'skipped', 'steps', 'total']

test('prop keys: the full set the app can send is pinned, and every event has its own list', () => {
  assert.deepEqual([...PROP_KEYS], WIRE_PROP_KEYS)
  assert.deepEqual(Object.keys(EVENT_PROPS).sort(), [...EVENT_NAMES].sort())
  assert.deepEqual([...EVENT_PROPS.crash].sort(), ['app_version', 'kind'])
  for (const k of PROP_KEYS) assert.doesNotMatch(k, /message|text|path|file|url|email|token|title|id$/)
})

test('cleanProps: only allowlisted keys with numbers, booleans and enum-like strings', () => {
  const p = cleanProps({
    mode: 'video',
    steps: 7,
    already: true,
    ok: true,
    Bad: 1,
    reason: 'how do I train a neural network on my thesis data',
    kind: 'mi_abcdefghijklmnopqrstu',
    query: 'x',
    path: '/Users/michael/x.py',
    minutes: Number.NaN,
    total: { a: 1 },
    message: 'Error at /Users/michael/a/b/c.js "secret"'
  })
  assert.deepEqual(Object.keys(p).sort(), ['already', 'mode', 'steps'])
  assert.deepEqual(cleanProps({ mode: 'video', steps: 3 }, ['steps']), { steps: 3 })
  assert.deepEqual(cleanProps(null), {})
  assert.deepEqual(cleanProps([1, 2]), {})
  const many = Object.fromEntries(Array.from({ length: 40 }, (_, i) => [`k${i}`, i]))
  assert.deepEqual(cleanProps(many, Object.keys(many)), Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`k${i}`, i])))
})

test('makeEvent: unknown names are dropped; the shape is {name, at, props}', () => {
  assert.equal(makeEvent('screen_text', { a: 1 }), undefined)
  const e = makeEvent('lesson_built', { mode: 'video', reason: 'quit' }, new Date('2026-11-21T10:00:00Z'))
  assert.deepEqual(e, { name: 'lesson_built', at: '2026-11-21T10:00:00.000Z', props: { mode: 'video' } }) // reason is not lesson_built's
  assert.deepEqual(makeEvent('hint_used', { steps: 3 })?.props, {})
})

test('crash feed: only lines after the mark, each a crash event with its kind and the app version, never the message', () => {
  const log = [
    { at: '2026-11-21T10:00:00.000Z', text: 'main error: old' },
    { at: '2026-11-21T10:05:00.000Z', text: 'window gone: crashed (exit 5)' },
    { at: '2026-11-21T10:06:00.000Z', text: 'renderer error: TypeError at /Users/michael/a/b/c.js' },
    { at: '2026-11-21T10:07:00.000Z', text: 'GPU process gone: crashed (exit 9)' },
    { bad: true }
  ]
  const fresh = newLines(log, '2026-11-21T10:00:00.000Z')
  assert.equal(fresh.length, 3)
  const [a, b, c] = fresh.map((l) => crashEvent(l, '1.2.3'))
  assert.deepEqual(a?.props, { kind: 'window', app_version: '1.2.3' })
  assert.deepEqual(b?.props, { kind: 'renderer_error', app_version: '1.2.3' })
  assert.deepEqual(c?.props, { kind: 'gpu_process', app_version: '1.2.3' })
  assert.equal(a?.at, '2026-11-21T10:05:00.000Z')
  // Free text that slipped past every scrubber before: none of it can leave now, whatever the line says.
  for (const text of [
    'main error: ENOENT notes/secret_plan.py not found',
    'renderer error: Unexpected token h in JSON at position 0 hello my name is Michael',
    'main error: login failed password=hunter2',
    'hello my name is Michael: and this is my thesis'
  ]) {
    const e = crashEvent({ at: '2026-11-21T10:08:00.000Z', text }, '1.2.3')
    assert.deepEqual(Object.keys(e?.props ?? {}).sort(), ['app_version', 'kind'])
    assert.doesNotMatch(JSON.stringify(e), /secret_plan|notes|hello|Michael|hunter2|password|thesis/)
  }
  assert.equal(crashEvent({ at: 'x', text: 'hello my name is Michael: x' })?.props.kind, 'other')
  assert.equal(newLines('nope', undefined).length, 0)
})

test('usageEvent: lesson milestones become counts, never titles, ids or text', () => {
  const t = newTrack()
  const ready = {
    type: 'lesson.ready',
    payload: { lesson: { id: 'les_1', title: 'My secret thesis', sources: [], builtBy: 'gemini', mode: 'video', outline: { count: 6, steps: [] } }, steps: [] }
  }
  const built = usageEvent(ready, t)
  assert.equal(built?.name, 'lesson_built')
  assert.deepEqual(built?.props, { steps: 6, built_by: 'gemini', mode: 'video' })
  assert.equal(usageEvent(ready, t), undefined) // the same lesson again
  assert.equal(usageEvent({ ...ready, payload: { ...ready.payload, replay: true } }, t), undefined)

  const passed = usageEvent({ type: 'step.passed', payload: { stepId: 's1', summary: 'wrote my_secret()' } }, t)
  assert.deepEqual(passed && { name: passed.name, props: passed.props }, { name: 'step_passed', props: { already: false } })
  assert.equal(usageEvent({ type: 'step.passed', payload: { stepId: 's1' } }, t), undefined) // once a step
  assert.equal(usageEvent({ type: 'step.passed', payload: { stepId: 's2', skipped: true } }, t), undefined) // a skip is not a pass
  assert.equal(usageEvent({ type: 'card', payload: { kind: 'hint', title: 'Try x', body: 'code here' } }, t)?.name, 'hint_used')
  assert.equal(usageEvent({ type: 'card', payload: { kind: 'step', source: 'judge', verdict: 'not_done', title: 'Not yet', body: '' } }, t)?.name, 'step_failed_check')
  assert.equal(usageEvent({ type: 'card', payload: { kind: 'explain', title: 'x', body: 'y' } }, t), undefined)

  const done = usageEvent({ type: 'card', payload: { kind: 'complete', title: 'Done', body: '', result: { passed: 5, skipped: 1, total: 6, minutes: 22, title: 'My secret thesis', lessonId: 'les_1' } } }, t)
  assert.deepEqual(done?.props, { passed: 5, skipped: 1, total: 6, minutes: 22 })
  assert.equal(usageEvent({ type: 'lesson.ended', payload: { reason: 'end_lesson' } }, t), undefined) // completed: not abandoned

  usageEvent({ type: 'lesson.ready', payload: { lesson: { id: 'les_2', title: 't', sources: [] }, steps: [{}, {}] } }, t)
  const quit = usageEvent({ type: 'lesson.ended', payload: { reason: 'Learner closed /Users/me/x' } }, t)
  assert.deepEqual(quit && { name: quit.name, props: quit.props }, { name: 'lesson_abandoned', props: { reason: 'other' } })
  assert.equal(usageEvent({ type: 'step.passed', payload: { stepId: 's9' } }, t), undefined) // no lesson: nothing
  assert.equal(usageEvent({ type: 'status', payload: {} }, t), undefined)
  assert.equal(usageEvent(null, t), undefined)

  for (const e of [built, passed, done, quit]) assert.doesNotMatch(JSON.stringify(e), /secret|les_\d|my_secret|\/Users/)
  // Every key a lesson count carries is on the wire list (and so on the cloud's, per the Cloud request).
  for (const e of [built, passed, done, quit]) for (const k of Object.keys(e?.props ?? {})) assert.ok(PROP_KEYS.includes(k), k)
})

test('resultFor: 2xx sent, 404 stops, bad batches drop, everything else retries', () => {
  assert.equal(resultFor(202), 'sent')
  assert.equal(resultFor(200), 'sent')
  assert.equal(resultFor(404), 'stop')
  assert.equal(resultFor(413), 'drop')
  assert.equal(resultFor(400), 'drop')
  assert.equal(resultFor(401), 'retry')
  assert.equal(resultFor(429), 'retry')
  assert.equal(resultFor(503), 'retry')
})

const ev = (i: number): TelemetryEvent => ({ name: 'step_passed', at: new Date(i).toISOString(), props: { i } })

test('Batcher: sends in batches, oldest first', async () => {
  const sent: number[][] = []
  const b = new Batcher({ batch: 3, send: async (es) => (sent.push(es.map((e) => Number(e.props.i))), 'sent') })
  for (let i = 0; i < 7; i++) b.push(ev(i))
  assert.equal(await b.flush(), 7)
  assert.deepEqual(sent, [[0, 1, 2], [3, 4, 5], [6]])
  assert.equal(b.size, 0)
  assert.equal(await b.flush(), 0)
})

test('Batcher: never more than 50 events or 32 KB in one request', async () => {
  const sizes: number[] = []
  const counts: number[] = []
  const b = new Batcher({ batch: 500, cap: 1000, send: async (es) => (counts.push(es.length), sizes.push(Buffer.byteLength(body(es))), 'sent') })
  for (let i = 0; i < 120; i++) b.push(ev(i))
  const big = (i: number): TelemetryEvent => ({ name: 'crash', at: new Date(i).toISOString(), props: Object.fromEntries(Array.from({ length: 12 }, (_, k) => [`k${k}`, 'x'.repeat(290)])) })
  for (let i = 0; i < 40; i++) b.push(big(i))
  assert.equal(await b.flush(), 160)
  assert.ok(counts.every((n) => n <= MAX_EVENTS), `counts ${counts}`)
  assert.ok(sizes.every((n) => n <= MAX_BYTES), `sizes ${sizes}`)
})

test('Batcher: a retry keeps the batch and backs off; drop drops it; stop ends the run', async () => {
  let now = 0
  let answer: SendResult = 'retry'
  let calls = 0
  const b = new Batcher({ batch: 2, backoffMs: 1000, maxBackoffMs: 4000, now: () => now, send: async () => (calls++, answer) })
  b.push(ev(1))
  b.push(ev(2))
  b.push(ev(3))
  assert.equal(await b.flush(), 0)
  assert.equal(b.size, 3)
  assert.equal(await b.flush(), 0) // still backing off: no request
  assert.equal(calls, 1)
  now = 1000
  assert.equal(await b.flush(), 0) // second failure: backoff doubles
  now = 2500
  assert.equal(await b.flush(), 0)
  assert.equal(calls, 2)
  now = 3000
  answer = 'drop'
  assert.equal(await b.flush(), 0)
  assert.equal(b.size, 0) // both batches dropped, nothing counted as sent
  answer = 'stop'
  b.push(ev(4))
  assert.equal(await b.flush(), 0)
  assert.equal(b.stopped, true)
  b.push(ev(5))
  assert.equal(b.size, 0)
})

test('Batcher: onSent sees only batches the endpoint took', async () => {
  const seen: number[] = []
  const answers: SendResult[] = ['drop', 'sent']
  const b = new Batcher({ batch: 1, send: async () => answers.shift() ?? 'sent', onSent: (es) => seen.push(...es.map((e) => Date.parse(e.at))) })
  b.push(ev(1))
  b.push(ev(2))
  assert.equal(await b.flush(), 1)
  assert.deepEqual(seen, [2])
})

test('Batcher: a throwing send counts as a retry; the cap drops the oldest; clear empties it', async () => {
  const b = new Batcher({
    batch: 5,
    cap: 3,
    send: async () => {
      throw new Error('offline')
    }
  })
  for (let i = 0; i < 5; i++) b.push(ev(i))
  assert.equal(b.size, 3)
  assert.equal(await b.flush(), 0)
  assert.equal(b.size, 3)
  b.clear()
  assert.equal(b.size, 0)
  b.push(undefined)
  assert.equal(b.size, 0)
})
