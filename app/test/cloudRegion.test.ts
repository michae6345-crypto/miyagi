/**
 * 451 region_unavailable (the cloud's region block, eng-proxy-next PR #267), app side, offline against the fake cloud:
 *
 *   cloud.ts       POST /v1/install answers 451: CloudView.region, state failed; no mint on an engine connect, no
 *                  self-heal re-mint on cloud.token_invalid; only the learner's own cloud:retry asks again
 *   cloudSession   POST /v1/session answers 451: 'region', no heal, no backoff retry
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, test } from 'node:test'
import cloud, { isRegionBlock, type CloudView } from '../src/main/features/cloud'
import { createSessionClient } from '../src/main/features/cloudSession/client'
import { CLOUD, FakeCloud, FakeSupabase, makeHarness, makeJwt, stubFetch, until, type Harness } from './harness'

let fake: FakeCloud
let h: Harness
let restore: () => void
beforeEach(() => {
  fake = new FakeCloud()
  fake.region = true
  restore = stubFetch(new FakeSupabase(), fake)
  h = makeHarness()
})
afterEach(() => {
  delete process.env.MIYAGI_CLOUD_URL
  h.close()
  restore()
})

const installs = (): number => fake.calls.filter((c) => c.url.endsWith('/v1/install')).length
const lastView = (): CloudView | undefined => [...h.broadcasts].reverse().find(([c]) => c === 'cloud')?.[1] as CloudView | undefined

describe('isRegionBlock', () => {
  test('451, or the body says region_unavailable; nothing else', () => {
    assert.equal(isRegionBlock(451), true)
    assert.equal(isRegionBlock(403, { error: 'region_unavailable' }), true)
    assert.equal(isRegionBlock(401, { error: 'signin_required' }), false)
    assert.equal(isRegionBlock(503), false)
  })
})

describe('cloud.ts install mint', () => {
  test('a 451 is final for the launch: region set, no re-mint on connect or token_invalid, retry only when asked', async () => {
    const opens: (() => void)[] = []
    const invalid: (() => void)[] = []
    const engine = h.ctx.engine as unknown as Record<string, unknown>
    engine.onOpen = (fn: () => void) => opens.push(fn)
    engine.onCloudTokenInvalid = (fn: () => void) => invalid.push(fn)
    process.env.MIYAGI_CLOUD_URL = CLOUD
    cloud.setup(h.ctx)
    await until(() => lastView()?.state === 'failed')
    assert.deepEqual(lastView(), { state: 'failed', configured: true, secure: true, hasToken: false, region: true })
    assert.equal(installs(), 1)

    // an engine (re)connect, much later, and the engine's token_invalid: nothing asks the cloud again
    const realNow = Date.now
    Date.now = () => realNow() + 60 * 60_000
    try {
      for (const fn of opens) fn()
      for (const fn of invalid) fn()
      await new Promise((r) => setTimeout(r, 20))
    } finally {
      Date.now = realNow
    }
    assert.equal(installs(), 1)

    // the learner's own Try again: one more ask, still the region answer
    const v = (await h.invoke('cloud:retry')) as CloudView
    assert.equal(installs(), 2)
    assert.equal(v.region, true)

    // the block lifts: the next retry mints, and region goes away
    fake.region = false
    const ok = (await h.invoke('cloud:retry')) as CloudView
    assert.equal(ok.state, 'ok')
    assert.equal(ok.region, undefined)
  })
})

describe('cloudSession client', () => {
  test('a 451 is final: region, no heal, no backoff retry', async () => {
    let heals = 0
    const scheduled: number[] = []
    const logs: string[] = []
    const c = createSessionClient({
      fetch: (i, init) => globalThis.fetch(i, init),
      accessToken: async () => makeJwt({ sub: 'user-r', exp: Math.floor(Date.now() / 1000) + 3600 }),
      refreshAccessToken: async () => undefined,
      install: () => ({ token: 'mi_installtokenRRRRRRRRRRRR', tokenId: 'tidR', host: CLOUD }),
      heal: async () => {
        heals++
        return true
      },
      legacyLink: async () => 'linked',
      file: join(h.dir, 'session.json'),
      log: (l) => logs.push(l),
      schedule: (_fn, ms) => {
        scheduled.push(ms)
        return () => undefined
      }
    })
    assert.equal(await c.sync({ force: true }), 'region')
    assert.equal(heals, 0)
    assert.deepEqual(scheduled, [])
    assert.equal(fake.calls.filter((x) => x.url.endsWith('/v1/session')).length, 1)
    assert.ok(logs.some((l) => /region/.test(l)) && !logs.some((l) => /mi_/.test(l)))
  })
})
