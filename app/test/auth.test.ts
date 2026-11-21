/** features/auth.ts, offline: the PKCE round trip against a fake Supabase, refresh, sign-out. */
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, test } from 'node:test'
import auth, { accessToken, needsLogin, onSignedIn } from '../src/main/features/auth'
import { safeStorage } from './fakes/electron'
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

  test('a refused code (expired flow) says so in plain words and stores nothing', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.refuseExchange = { status: 400, body: { error_code: 'flow_state_expired', msg: 'flow state has expired' } }
    await hitCallback(g.callback, { code: 'code-3' })
    assert.deepEqual(await g.result, { ok: false, reason: 'failed', message: 'That sign-in expired or was already used. Try again.' })
    assert.equal(existsSync(join(h.dir, 'auth.bin')), false)
    assert.equal(hooked, 0)
    assert.equal(await accessToken(), undefined)
  })

  test('a refused code with another reason shows Supabase’s msg', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.refuseExchange = { status: 422, body: { msg: 'Email not confirmed.' } }
    await hitCallback(g.callback, { code: 'code-4' })
    const r = (await g.result) as { ok: boolean; message: string }
    assert.equal(r.ok, false)
    assert.equal(r.message, 'The sign-in server refused the sign-in: Email not confirmed. Try again, or continue without an account.')
  })

  test('a wrong verifier (code issued for another challenge) is refused', async () => {
    auth.setup(h.ctx)
    const g = await startGoogle(h)
    supa.codes.set('code-5', { challenge: 'someone-elses-challenge', user: ALICE })
    await hitCallback(g.callback, { code: 'code-5' })
    assert.deepEqual(await g.result, { ok: false, reason: 'failed', message: 'That sign-in expired or was already used. Try again.' })
  })

  test('Google says no: access_denied and the provider misconfig are explained, the code is never shown', async () => {
    auth.setup(h.ctx)
    let g = await startGoogle(h)
    let page = await hitCallback(g.callback, { error: 'access_denied' })
    assert.match(page.text, /Sign-in did not finish/)
    assert.equal(((await g.result) as { reason: string }).reason, 'denied')

    g = await startGoogle(h)
    page = await hitCallback(g.callback, { error: 'server_error', error_description: 'Unable to exchange external code: 4/0AsecretCode' })
    const r = (await g.result) as { reason: string; message: string }
    assert.equal(r.reason, 'provider')
    assert.ok(!r.message.includes('4/0A') && !page.text.includes('4/0A'))
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
