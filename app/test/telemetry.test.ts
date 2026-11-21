/**
 * features/telemetry.ts, offline: the reporter against a fake POST /v1/events (the miyagi-cloud contract). Off by
 * default, nothing before the login gate opens, the exact request shape, 404 drops silently, nothing private leaves.
 */
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, test } from 'node:test'
import { DEFAULT_PREFS } from '../src/common/prefs'
import { createReporter, type ReporterDeps } from '../src/main/features/telemetry'

const HOST = 'https://cloud.test'
const TOKEN = 'mi_testinstalltokenTELEMETRY'

type Call = { url: string; headers: Record<string, string>; body: { events: { name: string; at: string; props: Record<string, unknown> }[] } }

let dir: string
let calls: Call[]
let status: number
let on: boolean
let gate: boolean
let log: { at: string; text: string }[]

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'miyagi-telemetry-'))
  calls = []
  status = 202
  on = false
  gate = true
  log = []
})
afterEach(() => rmSync(dir, { recursive: true, force: true }))

function reporter(over: Partial<ReporterDeps> = {}): ReturnType<typeof createReporter> {
  return createReporter({
    fetch: async (url, init) => {
      const headers: Record<string, string> = {}
      new Headers(init.headers).forEach((v, k) => (headers[k] = v))
      calls.push({ url, headers, body: JSON.parse(String(init.body)) })
      return new Response(status === 202 ? JSON.stringify({ ok: true }) : '{}', { status })
    },
    install: () => ({ token: TOKEN, tokenId: 'tid', host: HOST }),
    enabled: () => on,
    gateOpen: () => gate,
    errorLog: () => log,
    onboarded: () => true,
    stateFile: join(dir, 'telemetry', 'state.json'),
    appVersion: '1.2.3',
    os: 'darwin',
    arch: 'arm64',
    batcher: { backoffMs: 0 },
    ...over
  })
}

const lessonReady = { type: 'lesson.ready', payload: { lesson: { id: 'les_1', title: 'Secret thesis', sources: [], builtBy: 'claude', mode: 'lesson' }, steps: [{}, {}, {}] } }

test('the switch is off by default', () => {
  assert.equal(DEFAULT_PREFS.shareTelemetry, false)
})

test('off: nothing is queued or sent, whatever happens', async () => {
  const r = reporter()
  log.push({ at: new Date().toISOString(), text: 'main error: boom' })
  r.track(lessonReady)
  await r.tick()
  await r.tick()
  assert.equal(calls.length, 0)
  assert.equal(r.queued, 0)
})

test('on but the login gate is closed: nothing is sent until it opens', async () => {
  on = true
  gate = false
  const r = reporter()
  r.track(lessonReady)
  await r.tick()
  assert.equal(calls.length, 0)
  assert.equal(r.queued, 0)
  gate = true
  await r.tick()
  assert.equal(calls.length, 1)
})

test('MIYAGI_TELEMETRY=off wins over the switch', async () => {
  on = true
  const r = reporter({ off: 'off' })
  r.track(lessonReady)
  await r.tick()
  assert.equal(calls.length, 0)
})

test('no install token: events wait, nothing is sent without one', async () => {
  on = true
  let token: string | undefined
  const r = reporter({ install: () => (token ? { token, host: HOST } : undefined) })
  await r.tick()
  assert.equal(calls.length, 0)
  assert.ok(r.queued > 0)
  token = TOKEN
  await r.tick()
  assert.equal(calls.length, 1)
  assert.equal(r.queued, 0)
})

test('on: the exact contract request, to the token host, with only {events}', async () => {
  on = true
  const r = reporter()
  r.track(lessonReady)
  r.track({ type: 'step.passed', payload: { stepId: 's1', summary: 'wrote secret()' } })
  await r.tick()
  assert.equal(calls.length, 1)
  const [c] = calls
  assert.equal(c.url, `${HOST}/v1/events`)
  assert.equal(c.headers.authorization, `Bearer ${TOKEN}`)
  assert.equal(c.headers['content-type'], 'application/json')
  assert.deepEqual(Object.keys(c.body), ['events'])
  assert.ok(c.body.events.length <= 50)
  const names = c.body.events.map((e) => e.name)
  assert.deepEqual(names.sort(), ['app_installed', 'lesson_built', 'onboarding_done', 'step_passed'])
  for (const e of c.body.events) {
    assert.deepEqual(Object.keys(e).sort(), ['at', 'name', 'props'])
    assert.ok(!Number.isNaN(Date.parse(e.at)))
    for (const v of Object.values(e.props)) assert.ok(['string', 'number', 'boolean'].includes(typeof v))
  }
  assert.doesNotMatch(JSON.stringify(c.body), /Secret thesis|secret\(\)|les_1|mi_test/)
  // Sent once: the flags are saved, so the next launch does not send them again.
  await r.tick()
  const again = reporter()
  await again.tick()
  assert.equal(calls.length, 1)
})

test('crashes: only those logged after sharing was turned on, scrubbed', async () => {
  const r = reporter()
  log.push({ at: new Date(Date.now() - 60_000).toISOString(), text: 'main error: before opt-in at /Users/michael/x.js' })
  await r.tick() // off: the mark moves past it
  on = true
  await r.tick() // the switch went on: the feed starts here
  log.push({ at: new Date(Date.now() + 1000).toISOString(), text: 'renderer error: TypeError for me@example.com at /Users/michael/thesis/a.py "my screen" sk-ant-api03-abcdefghijklmnop' })
  await r.tick()
  const crashes = calls.flatMap((c) => c.body.events).filter((e) => e.name === 'crash')
  assert.equal(crashes.length, 1)
  const text = JSON.stringify(crashes[0])
  assert.doesNotMatch(text, /before opt-in|michael|example\.com|thesis|my screen|sk-ant/)
  assert.equal(crashes[0].props.kind, 'renderer_error')
  assert.equal(crashes[0].props.app_version, '1.2.3')
})

test('404 from an older cloud: dropped silently and nothing more is sent this run', async () => {
  on = true
  status = 404
  const r = reporter()
  r.track(lessonReady)
  await r.tick()
  assert.equal(calls.length, 1)
  assert.equal(r.stopped, true)
  assert.equal(r.queued, 0)
  r.track({ type: 'card', payload: { kind: 'hint', title: 'x', body: 'y' } })
  log.push({ at: new Date(Date.now() + 1000).toISOString(), text: 'main error: later' })
  await r.tick()
  assert.equal(calls.length, 1)
  assert.equal(r.queued, 0)
})

test('5xx: kept and retried on a later tick', async () => {
  on = true
  status = 503
  const r = reporter()
  await r.tick()
  assert.equal(calls.length, 1)
  const kept = r.queued
  assert.ok(kept > 0)
  status = 202
  await r.tick()
  assert.equal(calls.length, 2)
  assert.equal(r.queued, 0)
  assert.equal(calls[1].body.events.length, kept)
})

test('turning it off drops what waits', async () => {
  on = true
  status = 503
  const r = reporter()
  await r.tick()
  assert.ok(r.queued > 0)
  on = false
  await r.tick()
  assert.equal(r.queued, 0)
})

test('first time on: the error log from before is not sent', async () => {
  on = true
  log.push({ at: new Date(Date.now() - 3_600_000).toISOString(), text: 'main error: an old one' })
  const r = reporter()
  await r.tick()
  assert.ok(calls.length > 0)
  assert.equal(calls.flatMap((c) => c.body.events).filter((e) => e.name === 'crash').length, 0)
})
