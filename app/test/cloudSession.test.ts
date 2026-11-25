/**
 * MIC-30 (app side), features/cloudSession.ts + cloudSession/client.ts, offline: POST /v1/session against scripted
 * answers, then wired to the real auth.ts and cloud.ts behind the fake miyagi-cloud and Supabase (test/harness.ts).
 *
 *   client   200 saves {plan, caps, signinMode, linked, fetchedAt} (never a token, an email or an account id); 404 falls
 *            back to /v1/link; 401 re-mints the install token and retries once; 403 bad_access_token refreshes the
 *            session and retries once; 503 / offline keep the cache and retry with a backoff; fresh answers skip
 *   viewOf   what session:get hands a renderer: bounded, plan and caps only while signed in
 *   wired    a Google sign-in sends /v1/session and broadcasts feat:session; sign-out drops the account's numbers
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { after, afterEach, before, beforeEach, describe, test } from 'node:test'
import auth from '../src/main/features/auth'
import cloud, { installToken } from '../src/main/features/cloud'
import cloudSession, { viewOf } from '../src/main/features/cloudSession'
import { BACKOFF_MS, createSessionClient, readSession, recordOf, type SessionDeps } from '../src/main/features/cloudSession/client'
import { USER_DATA_FILES } from '../src/main/features/accountDelete/wipe'
import { CLOUD, FakeCloud, FakeSupabase, hitCallback, lockSignInPort, makeHarness, makeJwt, startGoogle, stubFetch, until, writeSession, type Harness } from './harness'

const ALICE = { sub: 'user-alice-7f3a', email: 'alice@example.com', name: 'Alice Test' }
const later = (): number => Math.floor(Date.now() / 1000) + 3600
const OK_BODY = {
  account: { id: ALICE.sub, email_verified: true },
  plan: 'free',
  caps: { daily_usd: 3, used_usd: 0.42, tokens: 20000000, used_tokens: 183000, resets_at: '2026-11-25T00:00:00Z' },
  linked: true,
  signin_mode: 'build'
}

type Sent = { url: string; auth?: string; body: { access_token?: string } }
type Reply = { status: number; body?: unknown } | 'offline'

/** A scripted cloud: each fetch takes the next reply (the last one repeats). */
function scripted(replies: Reply[]): { fetch: typeof fetch; sent: Sent[] } {
  const sent: Sent[] = []
  let i = 0
  const f = (async (input: string | URL | Request, init?: RequestInit) => {
    const headers = new Headers(init?.headers)
    sent.push({ url: String(input), auth: headers.get('authorization') ?? undefined, body: JSON.parse(String(init?.body ?? '{}')) })
    const r = replies[Math.min(i++, replies.length - 1)]
    if (r === 'offline') throw new TypeError('fetch failed')
    return new Response(r.body === undefined ? '' : JSON.stringify(r.body), { status: r.status, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
  return { fetch: f, sent }
}

let h: Harness
let logs: string[]
beforeEach(() => {
  h = makeHarness()
  logs = []
})
afterEach(() => h.close())

const INSTALL_A = { token: 'mi_installtokenAAAAAAAAAAAA', tokenId: 'tidA', host: CLOUD }
const INSTALL_B = { token: 'mi_installtokenBBBBBBBBBBBB', tokenId: 'tidB', host: CLOUD }

function client(replies: Reply[], over: Partial<SessionDeps> = {}) {
  const { fetch, sent } = scripted(replies)
  const scheduled: number[] = []
  const timers: (() => void)[] = []
  const counts = { heal: 0, refresh: 0, legacy: 0, changes: 0 }
  const file = join(h.dir, 'session.json')
  const c = createSessionClient({
    fetch,
    accessToken: async () => makeJwt({ sub: ALICE.sub, exp: later() }),
    refreshAccessToken: async () => {
      counts.refresh++
      return makeJwt({ sub: ALICE.sub, exp: later() + 60 }, 'fresh')
    },
    install: () => INSTALL_A,
    heal: async () => {
      counts.heal++
      return false
    },
    legacyLink: async () => {
      counts.legacy++
      return 'linked'
    },
    file,
    onChange: () => counts.changes++,
    log: (l) => logs.push(l),
    schedule: (fn, ms) => {
      scheduled.push(ms)
      timers.push(fn)
      return () => undefined
    },
    ...over
  })
  return { c, sent, scheduled, timers, counts, file }
}

describe('createSessionClient', () => {
  test('200: the contract request, then {plan, caps, signinMode, linked, fetchedAt} in memory and session.json', async () => {
    const { c, sent, file, counts } = client([{ status: 200, body: OK_BODY }])
    assert.equal(await c.sync({ force: true }), 'ok')
    assert.equal(sent.length, 1)
    assert.equal(sent[0].url, `${CLOUD}/v1/session`)
    assert.equal(sent[0].auth, `Bearer ${INSTALL_A.token}`)
    assert.deepEqual(Object.keys(sent[0].body), ['access_token'])
    const rec = c.current()
    assert.equal(rec?.plan, 'free')
    assert.equal(rec?.signinMode, 'build')
    assert.equal(rec?.linked, true)
    assert.deepEqual(rec?.caps, { dailyUsd: 3, usedUsd: 0.42, tokens: 20000000, usedTokens: 183000, resetsAt: '2026-11-25T00:00:00Z' })
    assert.deepEqual(readSession(file), rec)
    assert.deepEqual(Object.keys(JSON.parse(readFileSync(file, 'utf8'))).sort(), ['caps', 'fetchedAt', 'linked', 'plan', 'signinMode'])
    assert.equal(counts.changes, 1)
    assert.deepEqual(logs, [])
  })

  test('the cache file holds no token, no email and no account id', async () => {
    const body = { ...OK_BODY, account: { id: ALICE.sub, email: ALICE.email, email_verified: true }, email: ALICE.email, access_token: 'eyJ.leak.good', token: INSTALL_A.token }
    const { c, file, sent } = client([{ status: 200, body }])
    assert.equal(await c.sync({ force: true }), 'ok')
    const raw = readFileSync(file, 'utf8')
    for (const secret of [INSTALL_A.token, 'mi_', ALICE.email, '@', ALICE.sub, sent[0].body.access_token ?? 'x', 'eyJ', 'tidA']) assert.ok(!raw.includes(secret), `no ${secret}`)
  })

  test('"0" (an older draft of the contract) and junk read as off; a 200 without linked is not trusted', () => {
    assert.equal(recordOf({ ...OK_BODY, signin_mode: '0' }, 'now')?.signinMode, 'off')
    assert.equal(recordOf({ ...OK_BODY, signin_mode: 'everything' }, 'now')?.signinMode, 'off')
    assert.equal(recordOf({ ...OK_BODY, signin_mode: 'all' }, 'now')?.signinMode, 'all')
    assert.equal(recordOf({ ...OK_BODY, linked: false }, 'now'), undefined)
    assert.equal(recordOf({ ...OK_BODY, caps: { daily_usd: 3, used_usd: Infinity, used_tokens: 1 } }, 'now')?.caps, undefined)
    assert.deepEqual(recordOf({ ...OK_BODY, plan: 'pro', caps: { daily_usd: null, used_usd: 1.5, tokens: null, used_tokens: 9 } }, 'now')?.caps, { dailyUsd: null, usedUsd: 1.5, tokens: null, usedTokens: 9 })
  })

  test('404 (an older cloud): falls back to /v1/link, linked without plan or caps, the last mode kept', async () => {
    writeFileSync(join(h.dir, 'session.json'), JSON.stringify({ signinMode: 'all', linked: false, fetchedAt: '2026-11-20T00:00:00.000Z' }))
    const { c, counts, sent } = client([{ status: 404, body: { detail: 'Not Found' } }])
    assert.equal(await c.sync({ force: true }), 'legacy')
    assert.equal(counts.legacy, 1)
    assert.equal(sent.length, 1, 'no retry of /v1/session')
    assert.equal(c.current()?.linked, true)
    assert.equal(c.current()?.signinMode, 'all')
    assert.equal(c.current()?.caps, undefined)
  })

  test('404 and the old link fails too: the cache is left alone', async () => {
    const { c } = client([{ status: 404 }], { legacyLink: async () => 'failed' })
    assert.equal(await c.sync({ force: true }), 'legacy')
    assert.equal(c.current(), undefined)
    assert.equal(existsSync(join(h.dir, 'session.json')), false)
  })

  test('401: re-mints the install token through the self-heal, then retries once with the new token', async () => {
    let install = INSTALL_A
    const { c, sent, counts } = client([{ status: 401, body: { error: 'bad_install_token' } }, { status: 200, body: OK_BODY }], {
      install: () => install,
      heal: async () => {
        counts.heal++
        install = INSTALL_B
        return true
      }
    })
    assert.equal(await c.sync({ force: true }), 'ok')
    assert.equal(counts.heal, 1)
    assert.deepEqual(sent.map((s) => s.auth), [`Bearer ${INSTALL_A.token}`, `Bearer ${INSTALL_B.token}`])
  })

  test('401 again after the heal, or a heal that brings no token: refused, never a loop', async () => {
    let install = INSTALL_A
    const a = client([{ status: 401, body: { error: 'bad_install_token' } }], {
      install: () => install,
      heal: async () => {
        install = INSTALL_B
        return true
      }
    })
    assert.equal(await a.c.sync({ force: true }), 'refused')
    assert.equal(a.sent.length, 2)
    const b = client([{ status: 401, body: { error: 'bad_install_token' } }])
    assert.equal(await b.c.sync({ force: true }), 'refused')
    assert.equal(b.counts.heal, 1)
    assert.equal(b.sent.length, 1)
    assert.deepEqual(b.scheduled, [BACKOFF_MS[0]], 'tried again later')
    assert.ok(logs.every((l) => !l.includes('mi_') && !l.includes('eyJ')))
  })

  test('403 bad_access_token: refreshes the Supabase session once, then retries with the fresh token', async () => {
    const { c, sent, counts } = client([{ status: 403, body: { error: 'bad_access_token' } }, { status: 200, body: OK_BODY }])
    assert.equal(await c.sync({ force: true }), 'ok')
    assert.equal(counts.refresh, 1)
    assert.equal(sent.length, 2)
    assert.ok(sent[1].body.access_token?.endsWith('.fresh'), 'the retry carried the refreshed token')
  })

  test('403 twice, a refresh that fails, or too_many_installs: refused after at most one retry', async () => {
    const a = client([{ status: 403, body: { error: 'bad_access_token' } }])
    assert.equal(await a.c.sync({ force: true }), 'refused')
    assert.equal(a.sent.length, 2)
    const b = client([{ status: 403, body: { error: 'bad_access_token' } }], { refreshAccessToken: async () => undefined })
    assert.equal(await b.c.sync({ force: true }), 'refused')
    assert.equal(b.sent.length, 1)
    const c = client([{ status: 403, body: { error: 'too_many_installs' } }])
    assert.equal(await c.c.sync({ force: true }), 'refused')
    assert.equal(c.counts.refresh, 0)
    assert.equal(c.sent.length, 1)
  })

  test('503 and offline keep the cached answer and retry with a growing backoff', async () => {
    const { c, file, scheduled, timers } = client([{ status: 200, body: OK_BODY }, { status: 503, body: { error: 'link_unavailable' } }, 'offline', { status: 200, body: { ...OK_BODY, caps: { ...OK_BODY.caps, used_usd: 0.5 } } }])
    assert.equal(await c.sync({ force: true }), 'ok')
    const before = readFileSync(file, 'utf8')
    const cached = c.current()
    assert.equal(await c.sync({ force: true }), 'failed')
    assert.deepEqual(c.current(), cached)
    assert.equal(readFileSync(file, 'utf8'), before)
    assert.equal(await c.sync({ force: true }), 'failed')
    assert.deepEqual(c.current(), cached)
    assert.deepEqual(scheduled, [BACKOFF_MS[0], BACKOFF_MS[1]])
    timers.at(-1)?.() // the backoff fires: the next try lands
    await until(() => c.current()?.caps?.usedUsd === 0.5)
    assert.ok(logs.some((l) => l.includes('503')))
  })

  test('a fresh answer for the same install sends nothing unless forced; signed out or no install sends nothing', async () => {
    const { c, sent } = client([{ status: 200, body: OK_BODY }])
    assert.equal(await c.sync(), 'ok')
    assert.equal(await c.sync(), 'fresh')
    assert.equal(await c.sync({ force: true }), 'ok')
    assert.equal(sent.length, 2)
    assert.equal(await client([], { accessToken: async () => undefined }).c.sync(), 'signed-out')
    assert.equal(await client([], { install: () => undefined }).c.sync(), 'no-install')
    assert.equal(await client([], { accessToken: async () => makeJwt({ sub: 'x', exp: 1 }) }).c.sync(), 'expired')
  })

  test('sign-out drops the plan and caps, keeps the mode and the link; after Delete my data nothing is written back', async () => {
    const { c, file } = client([{ status: 200, body: OK_BODY }])
    await c.sync({ force: true })
    c.signedOut()
    assert.deepEqual(Object.keys(JSON.parse(readFileSync(file, 'utf8'))).sort(), ['fetchedAt', 'linked', 'signinMode'])
    assert.equal(c.current()?.signinMode, 'build')
    const d = client([{ status: 200, body: OK_BODY }])
    await d.c.sync({ force: true })
    rmSync(d.file)
    d.c.signedOut()
    assert.equal(existsSync(d.file), false)
  })

  test('session.json is on the Delete account list', () => {
    assert.ok((USER_DATA_FILES as readonly string[]).includes('session.json'))
  })
})

describe('viewOf (what session:get hands a renderer)', () => {
  const rec = recordOf(OK_BODY, '2026-11-24T10:00:00.000Z')
  test('signed in: plan, caps, mode, link; nothing else', () => {
    const v = viewOf(rec, true)
    assert.deepEqual(Object.keys(v).sort(), ['caps', 'fetchedAt', 'linked', 'plan', 'signedIn', 'signinMode'])
    assert.equal(v.caps?.usedUsd, 0.42)
    assert.ok(!JSON.stringify(v).includes(ALICE.sub))
  })
  test('signed out: no plan, no caps; nothing cached: a calm empty view', () => {
    assert.deepEqual(Object.keys(viewOf(rec, false)).sort(), ['fetchedAt', 'linked', 'signedIn', 'signinMode'])
    assert.deepEqual(viewOf(undefined, false), { signedIn: false, linked: false, signinMode: 'off' })
  })
  test('junk in the record is bounded away', () => {
    const junk = { plan: 'enterprise', caps: { dailyUsd: -1, usedUsd: 1e20, tokens: 1, usedTokens: 2 }, signinMode: 'sure', linked: 'yes', fetchedAt: 'x'.repeat(80), token: 'mi_x' }
    const v = viewOf(junk as never, true)
    assert.deepEqual(v, { signedIn: true, linked: false, signinMode: 'off', plan: 'free' })
  })
})

describe('wired to auth.ts and cloud.ts', () => {
  let supa: FakeSupabase
  let fake: FakeCloud
  let restore: () => void
  let unlockPort: () => Promise<void>
  before(async () => {
    unlockPort = await lockSignInPort()
  })
  after(async () => {
    await unlockPort?.()
  })
  beforeEach(async () => {
    supa = new FakeSupabase()
    fake = new FakeCloud()
    fake.session = { signin_mode: 'build' }
    restore = stubFetch(supa, fake)
    process.env.MIYAGI_CLOUD_URL = CLOUD
    cloud.setup(h.ctx)
    await until(() => fake.installs.has(installToken()?.token ?? ''))
  })
  afterEach(() => {
    delete process.env.MIYAGI_CLOUD_URL
    restore()
  })
  const sessionCalls = (): FakeCloud['calls'] => fake.calls.filter((c) => c.url.endsWith('/v1/session'))

  test('a Google sign-in sends /v1/session (not /v1/link), caches the answer and tells the renderer', async () => {
    auth.setup(h.ctx)
    cloudSession.setup(h.ctx)
    const g = await startGoogle(h)
    supa.codes.set('code-S', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-S' })
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
    await until(() => existsSync(join(h.dir, 'session.json')))
    assert.equal(sessionCalls().length, 1)
    assert.equal(fake.calls.filter((c) => c.url.endsWith('/v1/link')).length, 0)
    assert.equal(fake.links.get(installToken()?.token ?? ''), ALICE.sub)
    const v = (await h.invoke('session:get')) as ReturnType<typeof viewOf>
    assert.equal(v.signedIn, true)
    assert.equal(v.signinMode, 'build')
    assert.equal(v.caps?.dailyUsd, 3)
    assert.ok(h.broadcasts.some(([c]) => c === 'session'))
    const raw = readFileSync(join(h.dir, 'session.json'), 'utf8')
    assert.ok(!raw.includes(ALICE.email) && !raw.includes('mi_') && !raw.includes(ALICE.sub))
  })

  test('launch while signed in: session:get with nothing cached asks the cloud; sign-out drops the numbers', async () => {
    writeSession(h.dir, supa.session(ALICE))
    auth.setup(h.ctx)
    cloudSession.setup(h.ctx)
    const first = (await h.invoke('session:get')) as ReturnType<typeof viewOf>
    assert.equal(first.caps, undefined, 'nothing cached yet')
    await until(() => existsSync(join(h.dir, 'session.json')))
    assert.equal(((await h.invoke('session:get')) as ReturnType<typeof viewOf>).caps?.usedUsd, 0.42)
    assert.equal(await h.invoke('auth:sign-out'), true)
    const out = (await h.invoke('session:get')) as ReturnType<typeof viewOf>
    assert.equal(out.signedIn, false)
    assert.equal(out.caps, undefined)
    assert.equal(out.plan, undefined)
    assert.equal(out.signinMode, 'build')
    const last = h.broadcasts.filter(([c]) => c === 'session').at(-1)?.[1] as ReturnType<typeof viewOf>
    assert.equal(last.caps, undefined)
  })
})
