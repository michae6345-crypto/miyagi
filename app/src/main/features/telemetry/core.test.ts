/**
 * Telemetry core: scrubbing, props, the endpoint and batching. No Electron, no network.
 *   cd app && node --import tsx --test src/main/features/telemetry/core.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { Batcher, cleanProps, crashEvent, makeEvent, newLines, scrubCrash, telemetryUrl, type TelemetryEvent } from './core'

test('telemetryUrl: env wins, off turns it off, cloud host is the fallback, nothing without either', () => {
  assert.equal(telemetryUrl('https://t.example.com/v1/events/', 'https://cloud.example.com'), 'https://t.example.com/v1/events')
  assert.equal(telemetryUrl('off', 'https://cloud.example.com'), undefined)
  assert.equal(telemetryUrl('0', 'https://cloud.example.com'), undefined)
  assert.equal(telemetryUrl(undefined, 'https://cloud.example.com'), 'https://cloud.example.com/v1/events')
  assert.equal(telemetryUrl('', undefined), undefined)
  assert.equal(telemetryUrl('http://evil.example.com/e', undefined), undefined) // plain http only for this Mac
  assert.equal(telemetryUrl('http://127.0.0.1:8000/v1/events', undefined), 'http://127.0.0.1:8000/v1/events')
  assert.equal(telemetryUrl('https://u:p@t.example.com/e', undefined), undefined)
  assert.equal(telemetryUrl('https://t.example.com/e?key=1', undefined), undefined)
})

test('scrubCrash: no usernames in paths, no screen text, no keys, one capped line', () => {
  const s = scrubCrash("TypeError: Cannot read 'x' of undefined at /Users/michael/code/miyagi/app/out/main/index.js:12:5")
  assert.doesNotMatch(s, /michael/)
  assert.doesNotMatch(s, /'x'/)
  assert.match(s, /main\/index\.js:12:5/)
  const win = scrubCrash('Error at C:\\Users\\adrian\\AppData\\miyagi\\main.js:1')
  assert.doesNotMatch(win, /adrian/)
  const screen = scrubCrash('OCR failed on "import secret_project as sp" in “my notes”')
  assert.doesNotMatch(screen, /secret_project|my notes/)
  assert.match(screen, /\[text\]/)
  const keys = scrubCrash('auth sk-ant-api03-abcdefghijklmnop failed for me@example.com token mi_abcdefghijklmnopqrstu')
  assert.doesNotMatch(keys, /sk-ant-api03|example\.com|mi_abcdef/)
  assert.doesNotMatch(scrubCrash('a\nb\tc'), /\n|\t/)
  assert.ok(scrubCrash('x'.repeat(5000)).length <= 300)
  const tmp = scrubCrash('ENOENT /private/var/folders/ab/T/miyagi/file.json')
  assert.equal(tmp, 'ENOENT …/miyagi/file.json')
})

test('cleanProps: only short keys with numbers, booleans and enum-like strings', () => {
  const p = cleanProps({
    mode: 'video',
    steps: 7,
    ok: true,
    Bad: 1,
    query: 'how do I train a neural network on my thesis data',
    path: '/Users/michael/x.py',
    nan: Number.NaN,
    obj: { a: 1 },
    message: 'Error at /Users/michael/a/b/c.js "secret"'
  })
  assert.deepEqual(Object.keys(p).sort(), ['message', 'mode', 'ok', 'steps'])
  assert.doesNotMatch(String(p.message), /michael|secret/)
  assert.deepEqual(cleanProps(null), {})
  assert.deepEqual(cleanProps([1, 2]), {})
  const many = Object.fromEntries(Array.from({ length: 40 }, (_, i) => [`k${i}`, i]))
  assert.equal(Object.keys(cleanProps(many)).length, 12)
})

test('makeEvent: unknown names are dropped', () => {
  assert.equal(makeEvent('screen_text', { a: 1 }), undefined)
  const e = makeEvent('lesson_search', { mode: 'video' }, new Date('2026-11-21T10:00:00Z'))
  assert.deepEqual(e, { name: 'lesson_search', at: '2026-11-21T10:00:00.000Z', props: { mode: 'video' } })
})

test('crash feed: only lines after the cursor, each scrubbed into a crash event', () => {
  const log = [
    { at: '2026-11-21T10:00:00.000Z', text: 'main error: old' },
    { at: '2026-11-21T10:05:00.000Z', text: 'window gone: crashed (exit 5)' },
    { at: '2026-11-21T10:06:00.000Z', text: 'renderer error: TypeError at /Users/michael/a/b/c.js' },
    { bad: true }
  ]
  const fresh = newLines(log, '2026-11-21T10:00:00.000Z')
  assert.equal(fresh.length, 2)
  const [a, b] = fresh.map(crashEvent)
  assert.equal(a?.props.kind, 'window')
  assert.equal(a?.props.message, 'crashed (exit 5)')
  assert.equal(b?.props.kind, 'renderer_error')
  assert.doesNotMatch(String(b?.props.message), /michael/)
  assert.equal(newLines('nope', undefined).length, 0)
})

const ev = (i: number): TelemetryEvent => ({ name: 'step_passed', at: new Date(i).toISOString(), props: { i } })

test('Batcher: sends in batches, oldest first', async () => {
  const sent: number[][] = []
  const b = new Batcher({ batch: 3, send: async (es) => (sent.push(es.map((e) => Number(e.props.i))), true) })
  for (let i = 0; i < 7; i++) b.push(ev(i))
  assert.equal(b.full, true)
  assert.equal(await b.flush(), 7)
  assert.deepEqual(sent, [[0, 1, 2], [3, 4, 5], [6]])
  assert.equal(b.size, 0)
  assert.equal(await b.flush(), 0)
})

test('Batcher: a failed send keeps the batch and backs off, then retries', async () => {
  let now = 0
  let up = false
  let calls = 0
  const b = new Batcher({ batch: 2, backoffMs: 1000, maxBackoffMs: 4000, now: () => now, send: async () => (calls++, up) })
  b.push(ev(1))
  b.push(ev(2))
  assert.equal(await b.flush(), 0)
  assert.equal(b.size, 2)
  assert.equal(await b.flush(), 0) // still backing off: no request
  assert.equal(calls, 1)
  now = 1000
  assert.equal(await b.flush(), 0) // second failure: backoff doubles
  now = 2500
  assert.equal(await b.flush(), 0)
  assert.equal(calls, 2)
  now = 3000
  up = true
  assert.equal(await b.flush(), 2)
  assert.equal(b.size, 0)
})

test('Batcher: a throwing send counts as a failure; the cap drops the oldest; clear empties it', async () => {
  const b = new Batcher({ batch: 5, cap: 3, send: async () => { throw new Error('offline') } })
  for (let i = 0; i < 5; i++) b.push(ev(i))
  assert.equal(b.size, 3)
  assert.equal(await b.flush(), 0)
  assert.equal(b.size, 3)
  b.clear()
  assert.equal(b.size, 0)
  b.push(undefined)
  assert.equal(b.size, 0)
})
