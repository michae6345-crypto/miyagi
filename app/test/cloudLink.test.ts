/** features/cloudLink.ts, offline: POST /v1/link against a fake miyagi-cloud, wired to the real auth.ts and cloud.ts. */
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, afterEach, before, beforeEach, describe, test } from 'node:test'
import auth, { accessToken } from '../src/main/features/auth'
import cloud, { installToken } from '../src/main/features/cloud'
import { setGatePart } from '../src/main/gate'
import cloudSession from '../src/main/features/cloudSession'
import { createLinker, jwtClaims, readRecord, type LinkerDeps } from '../src/main/features/cloudLink'
import { CLOUD, FakeCloud, FakeSupabase, hitCallback, makeHarness, makeJwt, lockSignInPort, startGoogle, stubFetch, until, writeSession, type Harness } from './harness'

const ALICE = { sub: 'user-alice', email: 'alice@example.com', name: 'Alice Test' }
const BOB = { sub: 'user-bob', email: 'bob@example.com', name: 'Bob Test' }
const later = (): number => Math.floor(Date.now() / 1000) + 3600

// cloud.ts mints only after the age step and consent (mintAllowed): this file tests what comes after both.
setGatePart('consent', true)

let supa: FakeSupabase
let fake: FakeCloud
let h: Harness
let restore: () => void
let logs: string[]

// This file signs in on 127.0.0.1:47217; so may other test files and other checkouts' runs, in parallel. Hold the
// machine-wide lock for the whole file (see lockSignInPort).
let unlockPort: () => Promise<void>
before(async () => {
  unlockPort = await lockSignInPort()
})
after(async () => {
  await unlockPort?.()
})

beforeEach(() => {
  supa = new FakeSupabase()
  fake = new FakeCloud()
  restore = stubFetch(supa, fake)
  h = makeHarness()
  logs = []
})
afterEach(() => {
  h.close()
  restore()
})

/** A linker over a fake install token the fake cloud knows. */
function linker(over: Partial<LinkerDeps> = {}): { link: ReturnType<typeof createLinker>['link']; file: string; token: string } {
  const token = 'mi_testinstalltokenFIXED'
  fake.installs.add(token)
  const file = join(h.dir, 'cloud-link.json')
  const l = createLinker({
    fetch: (i, init) => globalThis.fetch(i, init),
    accessToken: async () => makeJwt({ sub: ALICE.sub, exp: later() }),
    install: () => ({ token, tokenId: 'tid-fixed', host: CLOUD }),
    file,
    log: (line) => logs.push(line),
    ...over
  })
  return { link: l.link, file, token }
}
const linkCalls = (): FakeCloud['calls'] => fake.calls.filter((c) => c.url.endsWith('/v1/link'))

describe('createLinker', () => {
  test('200: sends the contract request and saves {userId, linkedAt} (never a token)', async () => {
    const { link, file, token } = linker()
    assert.equal(await link({ force: true }), 'linked')
    const [call] = linkCalls()
    assert.equal(call.method, 'POST')
    assert.equal(call.url, `${CLOUD}/v1/link`)
    assert.equal(call.headers.authorization, `Bearer ${token}`)
    assert.equal(call.headers['content-type'], 'application/json')
    assert.deepEqual(Object.keys(call.body as object), ['access_token'])
    const rec = readRecord(file)
    assert.equal(rec?.userId, ALICE.sub)
    assert.equal(rec?.host, CLOUD)
    assert.ok(!Number.isNaN(Date.parse(rec?.linkedAt ?? '')))
    const raw = readFileSync(file, 'utf8')
    assert.ok(!raw.includes('mi_') && !raw.includes('.good'), 'no install token or JWT on disk')
    assert.deepEqual(logs, [])
  })

  test('launch check: already linked to this learner and install sends nothing; force still re-links (idempotent)', async () => {
    const { link } = linker()
    assert.equal(await link(), 'linked')
    assert.equal(await link(), 'already')
    assert.equal(linkCalls().length, 1)
    assert.equal(await link({ force: true }), 'linked')
    assert.equal(linkCalls().length, 2)
  })

  test('another learner, or a new install token, links again on launch', async () => {
    let who = ALICE
    let tokenId = 'tid-a'
    const { link } = linker({
      accessToken: async () => makeJwt({ sub: who.sub, exp: later() }),
      install: () => ({ token: 'mi_testinstalltokenFIXED', tokenId, host: CLOUD })
    })
    assert.equal(await link(), 'linked')
    who = BOB
    assert.equal(await link(), 'linked')
    tokenId = 'tid-b'
    assert.equal(await link(), 'linked')
    assert.equal(await link(), 'already')
  })

  test('404 (an older cloud): skipped silently, nothing saved, tried again next time', async () => {
    fake.linkStatus = 404
    const { link, file } = linker()
    assert.equal(await link(), 'unsupported')
    assert.equal(existsSync(file), false)
    assert.deepEqual(logs, [])
    fake.linkStatus = undefined
    assert.equal(await link(), 'linked')
  })

  test('403 bad access token: one line, no token in it, nothing saved', async () => {
    const { link, file } = linker({ accessToken: async () => makeJwt({ sub: ALICE.sub, exp: later() }, 'forged') })
    assert.equal(await link(), 'refused')
    assert.equal(existsSync(file), false)
    assert.equal(logs.length, 1)
    assert.match(logs[0], /access token/)
    assert.ok(!logs[0].includes('mi_') && !logs[0].includes('eyJ'))
  })

  test('401 bad install token, 503 and 500: logged once each, nothing saved', async () => {
    const { link, file } = linker()
    for (const s of [401, 503, 500] as const) {
      fake.linkStatus = s
      assert.equal(await link(), s === 401 ? 'refused' : 'failed')
    }
    assert.equal(existsSync(file), false)
    assert.equal(logs.length, 3)
    assert.ok(logs.every((l) => !l.includes('mi_')))
  })

  test('offline and a hung cloud: failed, never thrown', async () => {
    const offline = linker({ fetch: async () => Promise.reject(new TypeError('fetch failed')) })
    assert.equal(await offline.link(), 'failed')
    const hung = linker({
      timeoutMs: 20,
      fetch: (_i, init) => new Promise((_r, reject) => init?.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))))
    })
    assert.equal(await hung.link(), 'failed')
    assert.match(logs.at(-1) ?? '', /timeout/)
  })

  test('a 200 without ok/user_id is not trusted', async () => {
    const { link, file } = linker({ fetch: async () => new Response(JSON.stringify({ ok: true }), { status: 200 }) })
    assert.equal(await link(), 'failed')
    assert.equal(existsSync(file), false)
  })

  test('signed out, no install token, or a still-expired token: nothing is sent', async () => {
    assert.equal(await linker({ accessToken: async () => undefined }).link(), 'signed-out')
    assert.equal(await linker({ install: () => undefined }).link(), 'no-install')
    assert.equal(await linker({ accessToken: async () => makeJwt({ sub: ALICE.sub, exp: 1000 }) }).link(), 'expired')
    assert.equal(linkCalls().length, 0)
  })

  test('calls run one after another (a sign-in during the launch check)', async () => {
    const { link } = linker()
    const [a, b] = await Promise.all([link(), link()])
    assert.deepEqual([a, b], ['linked', 'already'])
  })

  test('jwtClaims reads sub/exp and survives junk', () => {
    assert.deepEqual(jwtClaims(makeJwt({ sub: 's', exp: 5 })), { sub: 's', exp: 5 })
    assert.deepEqual(jwtClaims('nope'), {})
    assert.deepEqual(jwtClaims('a.%%%.c'), {})
  })
})

describe('wired to auth.ts and cloud.ts', () => {
  const setupAll = async (): Promise<void> => {
    process.env.MIYAGI_CLOUD_URL = CLOUD
    cloud.setup(h.ctx)
    // cloud.ts keeps the token module-wide: wait for THIS test's mint (the fake cloud is new per test).
    await until(() => fake.installs.has(installToken()?.token ?? ''))
    auth.setup(h.ctx)
    cloudSession.setup(h.ctx) // owns the triggers since MIC-30; this fake cloud has no /v1/session (404) → /v1/link
  }
  afterEach(() => {
    delete process.env.MIYAGI_CLOUD_URL
  })

  test('a Google sign-in links this install to the learner', async () => {
    await setupAll()
    const g = await startGoogle(h)
    supa.codes.set('code-L', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-L' })
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
    await until(() => existsSync(join(h.dir, 'cloud-link.json')))
    assert.equal(readRecord(join(h.dir, 'cloud-link.json'))?.userId, ALICE.sub)
    assert.equal(fake.links.get(installToken()?.token ?? ''), ALICE.sub)
  })

  test('launch with an expired session: refresh first, then link with the fresh token', async () => {
    writeSession(h.dir, supa.session(ALICE, -120))
    await setupAll()
    const l = createLinker({ fetch: (i, init) => globalThis.fetch(i, init), accessToken, install: installToken, file: join(h.dir, 'cloud-link.json') })
    assert.equal(await l.link(), 'linked')
    const order = [...supa.calls, ...fake.calls].map((c) => c.url)
    assert.ok(supa.calls.some((c) => c.url.includes('grant_type=refresh_token')), 'refreshed')
    const sent = (linkCalls()[0].body as { access_token: string }).access_token
    assert.ok((jwtClaims(sent).exp ?? 0) * 1000 > Date.now(), 'the link carried the fresh token')
    assert.ok(order.length > 0)
  })

  test('sign-out keeps working anonymously: install token kept, no unlink, nothing more sent', async () => {
    writeSession(h.dir, supa.session(ALICE))
    await setupAll()
    const file = join(h.dir, 'cloud-link.json')
    const l = createLinker({ fetch: (i, init) => globalThis.fetch(i, init), accessToken, install: installToken, file })
    assert.equal(await l.link(), 'linked')
    const before = fake.calls.length
    assert.equal(await h.invoke('auth:sign-out'), true)
    assert.equal(await l.link(), 'signed-out')
    assert.ok(installToken(), 'the anonymous install token stays')
    assert.equal(fake.calls.length, before, 'no call to the cloud on sign-out')
    assert.ok(existsSync(file), 'the record stays: sign-out never unlinks')
    assert.deepEqual(await h.invoke('cloud:get'), { state: 'ok', configured: true, secure: true, hasToken: true })
  })
})
