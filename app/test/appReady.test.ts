/**
 * Lane C (michael/app-ready-main, DEPLOY-READINESS 2026-11-25), offline:
 *
 *   delete   a cloud with no delete route (404) still wipes this Mac, and the learner is told to email support to remove
 *            the account; no line says "Nothing was deleted" once this Mac was wiped
 *   cloud    no POST /v1/install before the age step and the consent screen are done; one mint once both are through
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/appReady.test.ts
 */
import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'
import { CONTACT_EMAIL } from '../src/common/consent'
import { runDelete } from '../src/main/features/accountDelete/run'
import { deleteOnServer, type ServerDeps } from '../src/main/features/accountDelete/server'
import agegate from '../src/main/features/agegate'
import cloud, { installToken, mintAllowed, type CloudView } from '../src/main/features/cloud'
import { setGatePart } from '../src/main/gate'
import { deleteAccount, wiped } from '../src/renderer/src/features/settings/privacy/erase'
import { DELETE } from '../src/renderer/src/features/settings/privacy/facts'
import { CLOUD, FakeCloud, FakeSupabase, makeHarness, stubFetch, until, type Harness } from './harness'

const INSTALL = { token: 'mi_installtokeninstalltoken', tokenId: 't1', host: 'https://cloud.test' }

/** A cloud that answers every call with `status` (no network). */
function answering(status: number, body: unknown = { detail: 'Not Found' }): typeof fetch {
  return (async () => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })) as unknown as typeof fetch
}

function serverDeps(f: typeof fetch, o: Partial<ServerDeps> = {}): ServerDeps {
  return { fetch: f, install: () => INSTALL, accessToken: async () => 'jwt-old', refreshedAccessToken: async () => 'jwt-new', log: () => undefined, ...o }
}

describe('Delete account against a cloud that answers 404', () => {
  test('main: this Mac is wiped and the account goes by email', async () => {
    let wipes = 0
    const r = await runDelete({
      server: () => deleteOnServer(serverDeps(answering(404))),
      local: async () => (wipes++, true),
      log: () => undefined
    })
    assert.deepEqual(r, { ok: true, account: 'email', local: true })
    assert.equal(wipes, 1, 'the local wipe ran')
  })

  test('main: offline or refused still touches nothing here', async () => {
    let wipes = 0
    const local = async (): Promise<boolean> => (wipes++, true)
    assert.deepEqual(await runDelete({ server: () => deleteOnServer(serverDeps(answering(503))), local, log: () => undefined }), { ok: false, reason: 'unreachable' })
    assert.deepEqual(await runDelete({ server: () => deleteOnServer(serverDeps(answering(401), { refreshedAccessToken: async () => undefined })), local, log: () => undefined }), {
      ok: false,
      reason: 'account'
    })
    assert.equal(wipes, 0)
  })

  test('main: a wipe that throws part way is a partial delete, never "nothing deleted"', async () => {
    const r = await runDelete({
      server: async () => ({ ok: true, account: 'email', via: 'no-route' }),
      local: async () => {
        throw new Error('disk')
      },
      log: () => undefined
    })
    assert.deepEqual(r, { ok: true, account: 'email', local: false })
  })

  test('renderer: the email step, signed out, and the line names support', async () => {
    const calls: string[] = []
    const invoke = async (c: string): Promise<unknown> => {
      calls.push(c)
      if (c === 'account:delete') return { ok: true, account: 'email', local: true }
      if (c === 'auth:sign-out') return true
      return undefined
    }
    const e = await deleteAccount(invoke, { lessons: false })
    assert.equal(e.step, 'email')
    assert.equal(e.account, 'email')
    assert.equal(e.signedOut, true)
    assert.deepEqual(calls, ['account:delete', 'settings:delete', 'auth:sign-out'])
    assert.equal(wiped(e.step), true, 'the app restarts after the line, like a full delete')
    assert.ok(DELETE.email.includes(CONTACT_EMAIL), DELETE.email)
    assert.ok(DELETE.email.includes('support@miyagi.study'))
    assert.ok(!/nothing was deleted/i.test(DELETE.email))
  })

  test('copy: only the lines shown before any wipe say nothing was deleted', () => {
    const afterWipe = [DELETE.done, DELETE.pending, DELETE.partial, DELETE.email]
    for (const s of afterWipe) assert.ok(!/nothing was deleted/i.test(s), s)
    assert.equal(wiped('offline'), false)
    assert.equal(wiped('refused'), false)
  })
})

describe('the install token waits for the age step and consent', () => {
  let h: Harness | undefined
  let restore: (() => void) | undefined
  afterEach(() => {
    delete process.env.MIYAGI_CLOUD_URL
    h?.close()
    restore?.()
  })

  test('mintAllowed: both, or no mint', () => {
    assert.equal(mintAllowed(true, true), true)
    assert.equal(mintAllowed(false, true), false)
    assert.equal(mintAllowed(true, false), false)
    assert.equal(mintAllowed(false, false), false)
  })

  test('no /v1/install before the gate opens; one mint once the age step and consent are done', async () => {
    const fake = new FakeCloud()
    restore = stubFetch(new FakeSupabase(), fake)
    h = makeHarness()
    const installs = (): number => fake.calls.filter((c) => c.url.endsWith('/v1/install')).length
    const lastView = (): CloudView | undefined => [...h!.broadcasts].reverse().find(([c]) => c === 'cloud')?.[1] as CloudView | undefined
    const settle = (): Promise<void> => new Promise((r) => setTimeout(r, 30))

    setGatePart('consent', false)
    agegate.setup(h.ctx) // no age record on file: the step is not through
    process.env.MIYAGI_CLOUD_URL = CLOUD
    cloud.setup(h.ctx)
    await settle()
    assert.equal(installs(), 0, 'nothing asked at launch')
    assert.equal(lastView()?.state, 'minting', 'on its way, not an error')

    // the learner's own retry can't get around it either
    await h.invoke('cloud:retry')
    assert.equal(installs(), 0)

    // consent alone is not enough (no age record yet)
    setGatePart('consent', true)
    await settle()
    assert.equal(installs(), 0)

    // the age step done: one mint
    await h.invoke('agegate:set', { band: '18+', confirmed: '2026-11-21', birth: '1990-01-01' })
    await until(() => lastView()?.state === 'ok')
    assert.equal(installs(), 1)
    assert.ok(installToken()?.token.startsWith('mi_'))

    // later gate changes don't mint again
    setGatePart('setup', true)
    await settle()
    assert.equal(installs(), 1)
  })
})
