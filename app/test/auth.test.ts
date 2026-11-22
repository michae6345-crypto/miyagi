/**
 * features/auth.ts, offline: the PKCE round trip against a fake Supabase, refresh, sign-out, and the callback attacks
 * (app-harden): forged or junk callbacks, the 5-callback cap, request shape, a taken port, the 5-minute expiry.
 */
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { request } from 'node:http'
import { createServer as createNetServer } from 'node:net'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, mock, test } from 'node:test'
import auth, {
  accessToken,
  assertPkce,
  authorizeUrl,
  CANCELLED_MESSAGE,
  explainCallbackError,
  FLOW_TYPE,
  listenRetry,
  MAX_CALLBACKS,
  needsLogin,
  onSignedIn,
  REDIRECT,
  redirectTo,
  TIMEOUT_MESSAGE,
  WAIT_MS
} from '../src/main/features/auth'
import { opened, safeStorage } from './fakes/electron'
import { FakeCloud, FakeSupabase, challengeOf, hitCallback, makeHarness, makeJwt, startGoogle, stubFetch, until, writeSession, type Harness } from './harness'

const ALICE = { sub: 'user-alice', email: 'alice@example.com', name: 'Alice Test' }

let supa: FakeSupabase
let h: Harness
let restore: () => void
let hooked = 0

beforeEach(() => {
  supa = new FakeSupabase()
  restore = stubFetch(supa, new FakeCloud())
  h = makeHarness()
  hooked = 0
  onSignedIn(() => hooked++)
})
afterEach(() => {
  h.close()
  restore()
})

const savedSession = (): Record<string, unknown> => JSON.parse(safeStorage.decryptString(readFileSync(join(h.dir, 'auth.bin'))))
const lastAuthBroadcast = (): unknown => h.broadcasts.filter(([c]) => c === 'auth:changed').at(-1)?.[1]
/** The last failed attempt main told the renderer about (auth:attempt), while the flow keeps listening. */
const lastAttempt = (): { reason: string; message: string } | undefined =>
  h.broadcasts.filter(([c]) => c === 'auth:attempt').at(-1)?.[1] as { reason: string; message: string } | undefined

/** Still waiting? (the flow has not answered auth:google yet) */
async function isPending(p: Promise<unknown>): Promise<boolean> {
  let done = false
  void p.then(() => (done = true))
  await new Promise((r) => setImmediate(r))
  await new Promise((r) => setImmediate(r))
  return !done
}

/** A raw request to the loopback: any method, path and headers (fetch can't forge Host). */
function raw(path: string, opts: { method?: string; headers?: Record<string, string> } = {}): Promise<{ status: number; text: string }> {
  return new Promise((resolve, reject) => {
    const req = request({ host: '127.0.0.1', port: 47217, path, method: opts.method ?? 'GET', headers: { Connection: 'close', ...opts.headers } }, (res) => {
      let text = ''
      res.setEncoding('utf8')
      res.on('data', (c: string) => (text += c))
      res.on('end', () => resolve({ status: res.statusCode ?? 0, text }))
    })
    req.on('error', reject)
    req.end()
  })
}

describe('Google sign-in (PKCE, loopback)', () => {
  test('success: exchanges the code, stores the session, tells the renderer only name/email/initial', async () => {
    auth.setup(h.ctx)
    assert.equal(await h.invoke('auth:get'), null)
    const g = await startGoogle(h)
    assert.equal(g.authorize.origin, 'https://fake-project.supabase.test')
    assert.equal(g.authorize.pathname, '/auth/v1/authorize')
    assert.equal(g.authorize.searchParams.get('provider'), 'google')
    assert.equal(g.authorize.searchParams.get('code_challenge_method'), 's256')
    assert.equal(g.callback.origin + g.callback.pathname, 'http://127.0.0.1:47217/auth/callback')
    assert.ok(g.state.length >= 24)

    supa.codes.set('code-1', { challenge: g.challenge, user: ALICE })
    const page = await hitCallback(g.callback, { code: 'code-1' })
    assert.equal(page.status, 200)
    assert.match(page.text, /Back to miyagi/)

    const r = (await g.result) as { ok: boolean; user: Record<string, unknown> }
    assert.deepEqual(r, { ok: true, user: { name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' } })
    assert.equal(hooked, 1, 'onSignedIn ran once')

    // The verifier sent matches the challenge in the authorize URL.
    const ex = supa.calls.find((c) => c.url.includes('grant_type=pkce'))
    assert.ok(ex)
    assert.equal(challengeOf((ex.body as { code_verifier: string }).code_verifier), g.challenge)

    const saved = savedSession()
    assert.equal(saved.project, 'https://fake-project.supabase.test')
    assert.equal(typeof saved.access_token, 'string')
    assert.ok(!existsSync(join(h.dir, 'login.json')), 'the login choice is never saved (login-first lane)')
    assert.equal(needsLogin(), false)

    // The renderer never sees a token.
    assert.deepEqual(lastAuthBroadcast(), { name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' })
    assert.ok(!JSON.stringify(h.broadcasts).includes(String(saved.access_token)))
    assert.deepEqual(await h.invoke('auth:get'), { signedIn: true, name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' })
    assert.equal(await accessToken(), saved.access_token)
  })

  test('state mismatch and wrong path are ignored (404); the real callback still finishes', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.codes.set('code-2', { challenge: g.challenge, user: ALICE })
    assert.equal((await hitCallback(g.callback, { code: 'code-2' }, { state: 'not-the-state' })).status, 404)
    assert.equal((await hitCallback(g.callback, { code: 'code-2' }, { state: '' })).status, 404)
    assert.equal((await hitCallback(g.callback, { code: 'code-2' }, { path: '/elsewhere' })).status, 404)
    assert.equal(supa.calls.length, 0, 'nothing exchanged for a forged callback')
    assert.equal((await hitCallback(g.callback, { code: 'code-2' })).status, 200)
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('a refused code (expired flow) says so in the tab, stores nothing, and the flow keeps listening', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.refuseExchange = { status: 400, body: { error_code: 'flow_state_expired', msg: 'flow state has expired' } }
    const page = await hitCallback(g.callback, { code: 'code-3' })
    assert.equal(page.status, 200)
    assert.match(page.text, /Sign-in did not finish/)
    assert.match(page.text, /That sign-in expired or was already used\. Try again\./)
    assert.match(page.text, />Try again<\/a>/)
    assert.deepEqual(lastAttempt(), { reason: 'failed', message: 'That sign-in expired or was already used. Try again.' })
    assert.equal(await isPending(g.result), true, 'a refused code does not end the flow')
    assert.equal(existsSync(join(h.dir, 'auth.bin')), false)
    assert.equal(hooked, 0)
    assert.equal(await accessToken(), undefined)
    // Ending it now (Cancel) answers cancelled; the timeout would answer the last reason (see the fake-timer test).
    await h.invoke('auth:cancel')
    assert.deepEqual(await g.result, { ok: false, reason: 'cancelled' })
  })

  test('a refused code with another reason shows Supabase’s msg in the tab and to the app', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.refuseExchange = { status: 422, body: { msg: 'Email not confirmed.' } }
    const page = await hitCallback(g.callback, { code: 'code-4' })
    const want = 'The sign-in server refused the sign-in: Email not confirmed. Try again, or continue without an account.'
    assert.ok(page.text.includes(want))
    assert.deepEqual(lastAttempt(), { reason: 'failed', message: want })
    assert.equal(await isPending(g.result), true)
  })

  test('ATTACK junk code with the correct state: the flow stays alive and the real callback still signs in', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    // A code issued for another challenge (bad_code_verifier), then one Supabase never issued (flow_state_not_found).
    supa.codes.set('stolen', { challenge: 'someone-elses-challenge', user: ALICE })
    assert.match((await hitCallback(g.callback, { code: 'stolen' })).text, /expired or was already used/)
    supa.refuseExchange = { status: 404, body: { error_code: 'flow_state_not_found', msg: 'invalid flow state, no valid flow state found' } }
    assert.equal((await hitCallback(g.callback, { code: 'junk' })).status, 200)
    assert.equal(await isPending(g.result), true)
    supa.codes.set('real', { challenge: g.challenge, user: ALICE })
    const page = await hitCallback(g.callback, { code: 'real' })
    assert.match(page.text, /Back to miyagi/)
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
    assert.equal(hooked, 1)
  })

  test('ATTACK error callback with the correct state does not end the flow; the code in the description is never shown', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    let page = await hitCallback(g.callback, { error: 'access_denied' })
    assert.match(page.text, /Sign-in cancelled/)
    // R20: a bare access_denied is Google's Cancel, told to the app (which ends its wait), never "ask to be a tester".
    assert.deepEqual(lastAttempt(), { reason: 'cancelled', message: CANCELLED_MESSAGE })
    assert.equal(await isPending(g.result), true)

    page = await hitCallback(g.callback, { error: 'access_denied', error_description: 'This app can only be accessed by developer-approved testers.' })
    assert.match(page.text, /Sign-in did not finish/)
    assert.equal(lastAttempt()?.reason, 'denied')
    assert.equal(await isPending(g.result), true)

    page = await hitCallback(g.callback, { error: 'server_error', error_description: 'Unable to exchange external code: 4/0AsecretCode' })
    assert.equal(lastAttempt()?.reason, 'provider')
    assert.ok(!page.text.includes('4/0A') && !JSON.stringify(h.broadcasts).includes('4/0A'))
    assert.equal(await isPending(g.result), true)

    supa.codes.set('code-7', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-7' })
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('ATTACK more than 5 callbacks with the right state: the 6th gets 404, even with a good code', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    // Five matching-state callbacks whose codes Supabase refuses: each one is a turn.
    for (let i = 0; i < MAX_CALLBACKS; i++) assert.equal((await hitCallback(g.callback, { code: `junk-${i}` })).status, 200)
    const exchanged = supa.calls.length
    assert.equal(exchanged, MAX_CALLBACKS)
    supa.codes.set('late', { challenge: g.challenge, user: ALICE })
    assert.equal((await hitCallback(g.callback, { code: 'late' })).status, 404, 'the 6th callback')
    assert.equal(supa.calls.length, exchanged, 'the 6th was not exchanged')
    assert.equal(await isPending(g.result), true)
    await h.invoke('auth:cancel')
  })

  test('ATTACK requests without the state (wrong state, none, another Host, POST) never use up the 5 turns', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    // What a local process, an <img src=http://127.0.0.1:47217/auth/callback> on a web page, or a DNS-rebinding page
    // (Host evil.example:47217) can send. Each is a 404 and none counts.
    for (let i = 0; i < MAX_CALLBACKS; i++) {
      assert.equal((await raw('/auth/callback')).status, 404)
      assert.equal((await raw(`/auth/callback?state=guess-${i}&code=x`)).status, 404)
      assert.equal((await raw(`/auth/callback?state=${g.state}&code=x`, { headers: { Host: 'evil.example:47217' } })).status, 404)
      assert.equal((await raw(`/auth/callback?state=${g.state}&code=x`, { method: 'POST' })).status, 404)
    }
    assert.equal(supa.calls.length, 0)
    // The real Google callback still signs in.
    supa.codes.set('real-after-probes', { challenge: g.challenge, user: ALICE })
    const page = await hitCallback(g.callback, { code: 'real-after-probes' })
    assert.equal(page.status, 200)
    assert.match(page.text, /Back to miyagi/)
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('ATTACK request shape: only GET, the exact path, Host 127.0.0.1:47217 and the five known params', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.codes.set('code-8', { challenge: g.challenge, user: ALICE })
    const q = `state=${g.state}&code=code-8`
    assert.equal((await raw(`/auth/callback?${q}`, { method: 'POST' })).status, 404)
    assert.equal((await raw(`/auth/callback?${q}`, { headers: { Host: 'evil.example' } })).status, 404, 'DNS rebinding Host')
    assert.equal((await raw(`/auth/callback/?${q}`)).status, 404)
    assert.equal((await raw(`/auth/./callback?${q}`)).status, 404)
    assert.equal((await raw(`//evil.example/auth/callback?${q}`)).status, 404)
    assert.equal((await raw(`/auth/callback?${q}&access_token=implicit`)).status, 404, 'implicit-flow tokens are never accepted')
    assert.equal((await raw(`/auth/callback?${q}&redirect_to=https://evil.example`)).status, 404)
    assert.equal((await raw(`/auth/callback?${q}&state=${g.state}`)).status, 404, 'a param twice')
    assert.equal(supa.calls.length, 0)
    // Those 8 refused requests used none of the 5 turns: the plain request still signs in (and proves the checks above
    // were what refused them, not something else).
    assert.equal((await raw(`/auth/callback?${q}`)).status, 200)
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('redirect_to is the constant plus this flow’s state, whatever the request headers', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    assert.equal(g.authorize.searchParams.get('redirect_to'), `http://127.0.0.1:47217/auth/callback?state=${g.state}`)
    assert.equal(redirectTo(g.state), `${REDIRECT}?state=${g.state}`)
    assert.match(g.state, /^[A-Za-z0-9_-]{32}$/, '24 random bytes (192 bits), base64url')
    // A forged request with hostile headers: refused (Host), and the next page's Try again link still points at the
    // constant redirect, never at a header's host.
    const evil = { 'X-Forwarded-Host': 'evil.example', 'X-Forwarded-Proto': 'https', Origin: 'https://evil.example', Referer: 'https://evil.example/' }
    assert.equal((await raw(`/auth/callback?state=${g.state}&error=access_denied`, { headers: { ...evil, Host: 'evil.example:47217' } })).status, 404)
    const page = await raw(`/auth/callback?state=${g.state}&error=access_denied`, { headers: evil })
    assert.equal(page.status, 200)
    const href = /href="([^"]+)"/.exec(page.text)?.[1]?.replace(/&#(\d+);/g, (_m, n) => String.fromCharCode(Number(n)))
    assert.ok(href)
    const retry = new URL(href)
    assert.equal(retry.origin, 'https://fake-project.supabase.test')
    assert.equal(retry.searchParams.get('redirect_to'), `http://127.0.0.1:47217/auth/callback?state=${g.state}`)
    assert.equal(retry.searchParams.get('code_challenge'), g.challenge)
    assert.ok(!page.text.includes('evil.example'))
    await h.invoke('auth:cancel')
  })

  test('PKCE only: the authorize URL carries an S256 challenge, the exchange is grant_type=pkce, no implicit flow', async () => {
    assert.equal(FLOW_TYPE, 'pkce')
    const ok = authorizeUrl('https://fake-project.supabase.test', 'st', 'c'.repeat(43))
    assert.doesNotThrow(() => assertPkce(ok))
    const u = new URL(ok)
    assert.equal(u.searchParams.get('code_challenge_method'), 's256')
    assert.equal(u.searchParams.has('response_type'), false)
    for (const bad of [
      ok.replace('code_challenge_method=s256', 'code_challenge_method=plain'),
      `${ok}&response_type=token`,
      `${ok}&flow_type=implicit`,
      ok.replace(/code_challenge=[^&]+/, 'code_challenge='),
      ok.replace(encodeURIComponent('http://127.0.0.1:47217/auth/callback'), encodeURIComponent('http://127.0.0.1:9999/auth/callback'))
    ]) {
      assert.throws(() => assertPkce(bad), /non-PKCE/, bad)
    }
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.codes.set('code-10', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-10' })
    await g.result
    assert.ok(supa.calls.every((c) => !c.url.includes('/token') || /grant_type=(pkce|refresh_token)$/.test(c.url)))
    assert.ok(supa.calls.some((c) => c.url.endsWith('/auth/v1/token?grant_type=pkce')))
  })

  test('R20 Cancel on Google’s page: told at once as a calm cancel (tab and app), no tester line, and a retry signs in', async () => {
    auth.setup(h.ctx)
    const first = await startGoogle(h)
    // What Supabase sends back after Google's Cancel: access_denied, an empty description, no error_code.
    const page = await hitCallback(first.callback, { error: 'access_denied', error_description: '' })
    assert.equal(page.status, 200)
    assert.match(page.text, /<title>Sign-in cancelled<\/title>/)
    assert.ok(page.text.includes('Sign-in was cancelled in the browser.'))
    assert.match(page.text, />Try again<\/a>/)
    assert.deepEqual(lastAttempt(), { reason: 'cancelled', message: CANCELLED_MESSAGE })
    assert.ok(!/tester/i.test(page.text + JSON.stringify(h.broadcasts)), 'no tester talk on a plain Cancel')
    assert.equal(supa.calls.length, 0, 'nothing exchanged')
    // The app's Try again (a new auth:google) replaces the old flow at once; the new one signs in.
    const g = await startGoogle(h)
    assert.deepEqual(await first.result, { ok: false, reason: 'cancelled' })
    supa.codes.set('after-cancel', { challenge: g.challenge, user: ALICE })
    assert.match((await hitCallback(g.callback, { code: 'after-cancel' })).text, /Back to miyagi/)
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('R20 explainCallbackError: the tester line only for Google’s own not-a-tester error', () => {
    const tester = /Ask to be added as a tester/
    const cases: [string | null, string | null, string | null, string, RegExp | string][] = [
      ['access_denied', null, null, 'cancelled', CANCELLED_MESSAGE],
      ['access_denied', null, '', 'cancelled', CANCELLED_MESSAGE],
      ['access_denied', 'access_denied', 'The user denied the request', 'cancelled', CANCELLED_MESSAGE],
      ['access_denied', null, 'Access blocked: this app can only be accessed by developer-approved testers', 'denied', tester],
      ['access_denied', null, "The developer hasn't given you access to this app.", 'denied', tester],
      ['access_denied', null, 'miyagi has not completed the Google verification process', 'denied', tester],
      // Supabase's own access_denied refusals carry an error_code: its words, never the tester line, never "cancelled".
      ['access_denied', 'signup_disabled', 'Signups not allowed for this instance', 'failed', /Signups not allowed for this instance/],
      ['access_denied', 'user_banned', 'User is banned', 'failed', /User is banned/],
      ['admin_policy_enforced', null, null, 'denied', /school or work account/],
      ['server_error', null, 'Unable to exchange external code: 4/0Asecret', 'provider', /not set up correctly/],
      [null, null, null, 'failed', /did not send a sign-in code/]
    ]
    for (const [error, code, desc, reason, message] of cases) {
      const r = explainCallbackError(error, code, desc)
      const label = `${error} / ${code} / ${desc}`
      assert.equal(r.reason, reason, label)
      if (typeof message === 'string') assert.equal(r.message, message, label)
      else assert.match(r.message, message, label)
      if (message !== tester) assert.doesNotMatch(r.message, tester, label)
      assert.ok(!r.message.includes('4/0A'), label)
    }
  })

  test('cancel while the browser is open, then a second try works', async () => {
    auth.setup(h.ctx)
    let g = await startGoogle(h)
    assert.equal(await h.invoke('auth:cancel'), true)
    assert.deepEqual(await g.result, { ok: false, reason: 'cancelled' })
    g = await startGoogle(h)
    supa.codes.set('code-6', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-6' })
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })
})

describe('session on launch', () => {
  const expired = (): Record<string, unknown> => {
    const s = supa.session(ALICE, -120) // expired two minutes ago; its refresh token is still good
    return s
  }

  test('an expired access token is refreshed before accessToken() hands it out (rotation saved)', async () => {
    const old = expired()
    writeSession(h.dir, old)
    auth.setup(h.ctx)
    const fresh = await accessToken()
    assert.ok(fresh && fresh !== old.access_token)
    assert.equal(supa.calls.filter((c) => c.url.includes('grant_type=refresh_token')).length, 1, 'one refresh, never two in flight')
    const saved = savedSession()
    assert.equal(saved.access_token, fresh)
    assert.notEqual(saved.refresh_token, old.refresh_token)
  })

  test('a refresh token Supabase refuses signs out calmly', async () => {
    writeSession(h.dir, { ...expired(), refresh_token: 'revoked' })
    auth.setup(h.ctx)
    assert.equal(await accessToken(), undefined)
    assert.equal(existsSync(join(h.dir, 'auth.bin')), false)
    assert.equal(lastAuthBroadcast(), null)
  })

  test('offline: the session is kept and retried later', async () => {
    const old = expired()
    writeSession(h.dir, old)
    supa.refreshMode = 'network'
    auth.setup(h.ctx)
    assert.equal(await accessToken(), old.access_token) // the stale one; cloudLink skips it as expired
    assert.ok(existsSync(join(h.dir, 'auth.bin')))
    assert.deepEqual(await h.invoke('auth:get'), { signedIn: true, name: 'Alice Test', email: 'alice@example.com', avatarInitial: 'A' })
  })

  test('a session saved for another project is dropped, unsent', async () => {
    writeSession(h.dir, supa.session(ALICE), 'https://other-project.supabase.co')
    auth.setup(h.ctx)
    assert.equal(await accessToken(), undefined)
    assert.equal(existsSync(join(h.dir, 'auth.bin')), false)
    assert.equal(supa.calls.length, 0)
  })

  test('a corrupt auth.bin means signed out, not a crash', async () => {
    const { writeFileSync } = await import('node:fs')
    writeFileSync(join(h.dir, 'auth.bin'), 'garbage')
    auth.setup(h.ctx)
    assert.equal(await h.invoke('auth:get'), null)
  })
})

describe('sign-out', () => {
  test('forgets the session at once and revokes it best effort', async () => {
    const s = supa.session(ALICE)
    writeSession(h.dir, s)
    auth.setup(h.ctx)
    assert.equal(await accessToken(), s.access_token)
    assert.equal(await h.invoke('auth:sign-out'), true)
    assert.equal(await accessToken(), undefined)
    assert.equal(await h.invoke('auth:get'), null)
    assert.equal(existsSync(join(h.dir, 'auth.bin')), false)
    assert.equal(lastAuthBroadcast(), null)
    await until(() => supa.calls.some((c) => c.url.endsWith('/auth/v1/logout?scope=local')))
    const out = supa.calls.find((c) => c.url.includes('/logout'))
    assert.equal(out?.headers.authorization, `Bearer ${s.access_token}`)
  })

  test('an expired session is refreshed before the revoke', async () => {
    writeSession(h.dir, supa.session(ALICE, -120))
    supa.refreshMode = 'network' // keep it expired through setup's own refresh
    auth.setup(h.ctx)
    await accessToken()
    supa.refreshMode = 'ok'
    await h.invoke('auth:sign-out')
    await until(() => supa.calls.some((c) => c.url.includes('/logout')))
    const out = supa.calls.find((c) => c.url.includes('/logout'))
    assert.notEqual(out?.headers.authorization, undefined)
    assert.ok(supa.calls.some((c) => c.url.includes('grant_type=refresh_token')))
  })
})

test('makeJwt is not a real token (sanity for the fakes)', () => {
  assert.equal(makeJwt({ sub: 'x', exp: 1 }).split('.').length, 3)
})

// Last in the file: these hold the port longest (cloudLink.test.ts, run in parallel, also signs in on 47217; auth.ts
// retries a taken port for ~3 s, so a short overlap is fine).
describe('the sign-in port and the flow’s lifetime', () => {
  test('a second click right after the first restarts the flow without a port error', async () => {
    auth.setup(h.ctx)
    const first = await startGoogle(h) // listening on 47217, browser open
    const g = await startGoogle(h) // the second click: the first listener is still letting go of the port
    assert.deepEqual(await first.result, { ok: false, reason: 'cancelled' })
    assert.notEqual(g.state, first.state)
    supa.codes.set('code-11', { challenge: g.challenge, user: ALICE })
    await hitCallback(g.callback, { code: 'code-11' })
    assert.equal(((await g.result) as { ok: boolean }).ok, true)
  })

  test('the browser drops the tab during a slow exchange: the listener still lets go, and the next sign-in gets the port', async () => {
    // Hold the pkce exchange until the browser's request is gone (the learner closed the slow tab).
    const real = supa.handle.bind(supa)
    let entered = false
    let letGo!: () => void
    const gate = new Promise<void>((r) => (letGo = r))
    supa.handle = async (url, call) => {
      if (url.searchParams.get('grant_type') === 'pkce') {
        entered = true
        await gate
      }
      return real(url, call)
    }
    // Two quick tries: before the fix the old listener kept 47217 for the rest of the run, and the second sign-in
    // failed with reason 'port'; it must not hang the test meanwhile.
    const saved = { ...listenRetry }
    Object.assign(listenRetry, { tries: 2, ms: 20 })
    try {
      auth.setup(h.ctx)
      const g = await startGoogle(h)
      supa.codes.set('slow', { challenge: g.challenge, user: ALICE })
      const req = request({ host: '127.0.0.1', port: 47217, path: `/auth/callback?state=${g.state}&code=slow`, headers: { Connection: 'close' } })
      req.on('error', () => undefined) // the abort below
      req.end()
      await until(() => entered)
      req.destroy()
      await new Promise((r) => setTimeout(r, 50)) // the server sees the socket close
      letGo()
      assert.equal(((await g.result) as { ok: boolean }).ok, true, 'signed in anyway')

      // Sign out, then sign in again in the same run: the browser opens (the port was free).
      await h.invoke('auth:sign-out')
      const before = opened.length
      let second: unknown
      const p = h.invoke('auth:google').then((r) => (second = r))
      await until(() => opened.length > before || second !== undefined, 5000)
      assert.equal(second, undefined, `the second sign-in did not fail: ${JSON.stringify(second)}`)
      assert.ok(opened.length > before, 'the browser opened for the second sign-in')
      await h.invoke('auth:cancel')
      await p
      assert.deepEqual(second, { ok: false, reason: 'cancelled' })
    } finally {
      Object.assign(listenRetry, saved)
      letGo()
    }
  })

  test('ATTACK port 47217 already taken (EADDRINUSE): sign-in stops with a clear reason and the browser never opens', async () => {
    const blocker = createNetServer()
    // Another process squatting the port (it would receive Google's code if the browser opened).
    const end = Date.now() + 5000
    for (;;) {
      const ok = await new Promise<boolean>((r) => {
        blocker.once('error', () => r(false))
        blocker.listen(47217, '127.0.0.1', () => r(true))
      })
      if (ok) break
      if (Date.now() > end) throw new Error('could not take the port for the test')
      await new Promise((r) => setTimeout(r, 50))
    }
    // The real window is ~3 s of retries; two quick tries here, so the port isn't held long while cloudLink.test.ts
    // (run in parallel) may want it.
    assert.ok(listenRetry.tries * listenRetry.ms >= 2000, 'a port that frees up within ~2 s is waited for')
    const saved = { ...listenRetry }
    Object.assign(listenRetry, { tries: 2, ms: 20 })
    try {
      auth.setup(h.ctx)
      const before = opened.length
      const r = (await h.invoke('auth:google')) as { ok: boolean; reason: string; message: string }
      assert.equal(r.ok, false)
      assert.equal(r.reason, 'port')
      assert.match(r.message, /port 47217/)
      assert.match(r.message, /Quit it/)
      assert.equal(opened.length, before, 'openExternal was never called')
      assert.equal(await h.invoke('auth:get'), null)
    } finally {
      Object.assign(listenRetry, saved)
      await new Promise<void>((r) => blocker.close(() => r()))
    }
  })

  test('the flow expires after 5 minutes (fake timers): timeout, and the listener lets go of the port', async () => {
    mock.timers.enable({ apis: ['setTimeout'] })
    let g: Awaited<ReturnType<typeof startGoogle>>
    try {
      auth.setup(h.ctx)
      g = await startGoogle(h)
      mock.timers.tick(WAIT_MS - 1000)
      assert.equal(await isPending(g.result), true, 'still waiting at 4:59')
      mock.timers.tick(1000)
      // R20: says plainly what happened (nothing came back in 5 minutes), never the tester line.
      assert.deepEqual(await g.result, { ok: false, reason: 'timeout', message: TIMEOUT_MESSAGE })
      assert.match(TIMEOUT_MESSAGE, /^No answer from Google after 5 minutes, so miyagi stopped waiting\./)
    } finally {
      mock.timers.reset()
    }
    await new Promise((r) => setImmediate(r))
    await assert.rejects(raw(`/auth/callback?state=${g.state}&code=late`), /ECONNREFUSED|ECONNRESET|socket hang up/)
  })

  test('a timeout after a failed attempt answers with that attempt’s reason (fake timers)', async () => {
    mock.timers.enable({ apis: ['setTimeout'] })
    try {
      auth.setup(h.ctx)
      const g = await startGoogle(h)
      // Google's real not-a-tester error (its description says so): that, and only that, is the tester line.
      const desc = encodeURIComponent("The developer hasn't given you access to this app.")
      const page = await raw(`/auth/callback?state=${g.state}&error=access_denied&error_description=${desc}`)
      assert.equal(page.status, 200)
      assert.equal(await isPending(g.result), true)
      mock.timers.tick(WAIT_MS)
      const r = (await g.result) as { ok: boolean; reason: string; message: string }
      assert.equal(r.reason, 'denied')
      assert.match(r.message, /isn't allowed yet/)
    } finally {
      mock.timers.reset()
    }
  })
})
