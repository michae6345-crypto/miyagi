/**
 * Delete account, the server part, against a mocked miyagi-cloud (nothing leaves this machine).
 *   cd app && node --import tsx --test src/main/features/accountDelete/server.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deleteOnServer, type ServerDeps } from './server'

const INSTALL = { token: 'mi_installtokeninstalltoken', tokenId: 't1', host: 'https://cloud.test' }
type Call = { url: string; auth: string | null; body: unknown }

/** A fake cloud: each call answers with the next [status, body] (or throws for 'offline'). */
function cloud(answers: ([number, unknown?] | 'offline')[]): { fetch: typeof fetch; calls: Call[] } {
  const calls: Call[] = []
  const fake = (async (url: string, init: RequestInit): Promise<Response> => {
    calls.push({ url, auth: new Headers(init.headers).get('authorization'), body: JSON.parse(String(init.body)) })
    const a = answers.shift() ?? 'offline'
    if (a === 'offline') throw new TypeError('fetch failed')
    return new Response(a[1] === undefined ? null : JSON.stringify(a[1]), { status: a[0], headers: { 'Content-Type': 'application/json' } })
  }) as unknown as typeof fetch
  return { fetch: fake, calls }
}

function deps(f: typeof fetch, o: Partial<ServerDeps> = {}): ServerDeps {
  return { fetch: f, install: () => INSTALL, accessToken: async () => 'jwt-old', refreshedAccessToken: async () => 'jwt-new', log: () => undefined, ...o }
}

test('200 deleted: the install token as Bearer, the access token in the body', async () => {
  const c = cloud([[200, { ok: true, install: true, account: 'deleted' }]])
  assert.deepEqual(await deleteOnServer(deps(c.fetch)), { ok: true, account: 'deleted', via: 'deleted' })
  assert.equal(c.calls.length, 1)
  assert.equal(c.calls[0].url, 'https://cloud.test/v1/account/delete')
  assert.equal(c.calls[0].auth, `Bearer ${INSTALL.token}`)
  assert.deepEqual(c.calls[0].body, { access_token: 'jwt-old' })
})

test('200 pending and 200 none come through as they are', async () => {
  assert.equal(((await deleteOnServer(deps(cloud([[200, { ok: true, install: true, account: 'pending' }]]).fetch))) as { account: string }).account, 'pending')
  assert.equal(((await deleteOnServer(deps(cloud([[200, { ok: true, install: true, account: 'none' }]]).fetch))) as { account: string }).account, 'none')
})

test('signed out: the body is {} and the install is deleted', async () => {
  const c = cloud([[200, { ok: true, install: true, account: 'none' }]])
  const r = await deleteOnServer(deps(c.fetch, { accessToken: async () => undefined }))
  assert.deepEqual(r, { ok: true, account: 'none', via: 'deleted' })
  assert.deepEqual(c.calls[0].body, {})
})

test('401 signed out: the install is already gone, which counts as success', async () => {
  const c = cloud([[401, { error: 'bad_install_token' }]])
  assert.deepEqual(await deleteOnServer(deps(c.fetch, { accessToken: async () => undefined })), { ok: true, account: 'none', via: 'install-gone' })
  assert.equal(c.calls.length, 1)
})

test('401 signed in: refresh once and send again; a 200 then is success', async () => {
  const c = cloud([[401], [200, { install: false, account: 'deleted' }]])
  let refreshed = 0
  const r = await deleteOnServer(deps(c.fetch, { refreshedAccessToken: async () => (refreshed++, 'jwt-new') }))
  assert.deepEqual(r, { ok: true, account: 'deleted', via: 'deleted', install: false })
  assert.equal(refreshed, 1)
  assert.deepEqual(c.calls.map((x) => x.body), [{ access_token: 'jwt-old' }, { access_token: 'jwt-new' }])
})

test('401 signed in, still 401 after the refresh: the account could not be deleted (no signed-out fallback)', async () => {
  const c = cloud([[401], [401]])
  assert.deepEqual(await deleteOnServer(deps(c.fetch)), { ok: false, reason: 'account' })
  assert.equal(c.calls.length, 2)
})

test('401 signed in and the refresh fails: account, nothing else sent', async () => {
  const c = cloud([[401]])
  assert.deepEqual(await deleteOnServer(deps(c.fetch, { refreshedAccessToken: async () => undefined })), { ok: false, reason: 'account' })
  assert.equal(c.calls.length, 1)
})

test('200 without ok (the new contract): install false means only the account went; still success', async () => {
  const c = cloud([[200, { install: false, account: 'pending' }]])
  assert.deepEqual(await deleteOnServer(deps(c.fetch)), { ok: true, account: 'pending', via: 'deleted', install: false })
})

test('403 bad_access_token: refresh once and send again', async () => {
  const c = cloud([
    [403, { error: 'bad_access_token' }],
    [200, { ok: true, install: true, account: 'deleted' }]
  ])
  let refreshed = 0
  const r = await deleteOnServer(deps(c.fetch, { refreshedAccessToken: async () => (refreshed++, 'jwt-new') }))
  assert.deepEqual(r, { ok: true, account: 'deleted', via: 'deleted' })
  assert.equal(refreshed, 1)
  assert.deepEqual(
    c.calls.map((x) => x.body),
    [{ access_token: 'jwt-old' }, { access_token: 'jwt-new' }]
  )
})

test('403 again after the refresh: a signed-out delete ({}) of the install', async () => {
  const c = cloud([
    [403, { error: 'bad_access_token' }],
    [403, { error: 'bad_access_token' }],
    [200, { ok: true, install: true, account: 'none' }]
  ])
  const r = await deleteOnServer(deps(c.fetch))
  assert.deepEqual(r, { ok: true, account: 'none', via: 'deleted', signedOutRetry: true })
  assert.deepEqual(c.calls.map((x) => x.body), [{ access_token: 'jwt-old' }, { access_token: 'jwt-new' }, {}])
})

test('403 and the refresh fails (signed out by now): straight to the signed-out delete', async () => {
  const c = cloud([
    [403, { error: 'bad_access_token' }],
    [200, { ok: true, install: true, account: 'none' }]
  ])
  const r = await deleteOnServer(deps(c.fetch, { refreshedAccessToken: async () => undefined }))
  assert.deepEqual(r, { ok: true, account: 'none', via: 'deleted', signedOutRetry: true })
  assert.deepEqual(c.calls.map((x) => x.body), [{ access_token: 'jwt-old' }, {}])
})

test('offline, a timeout, 5xx, 404 or a malformed 200: unreachable (the caller deletes nothing)', async () => {
  for (const a of ['offline', [503, { error: 'unavailable' }], [500], [404], [200, { ok: false }], [200, { ok: true, account: 'gone' }], [403, { error: 'other' }]] as const) {
    const r = await deleteOnServer(deps(cloud([a as never]).fetch))
    assert.deepEqual(r, { ok: false, reason: 'unreachable' }, JSON.stringify(a))
  }
  // A cloud that never answers: the timeout aborts it.
  const hang = (async (_u: string, init: RequestInit) =>
    new Promise((_r, reject) => init.signal?.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' }))))) as unknown as typeof fetch
  assert.deepEqual(await deleteOnServer(deps(hang, { timeoutMs: 20 })), { ok: false, reason: 'unreachable' })
})

test('a refresh that goes offline mid-way is unreachable too', async () => {
  const c = cloud([[403, { error: 'bad_access_token' }], 'offline'])
  assert.deepEqual(await deleteOnServer(deps(c.fetch)), { ok: false, reason: 'unreachable' })
})

test('no install token: signed out is fine (nothing there), signed in can not delete the account', async () => {
  const c = cloud([])
  assert.deepEqual(await deleteOnServer(deps(c.fetch, { install: () => undefined, accessToken: async () => undefined })), { ok: true, account: 'none', via: 'no-install' })
  assert.deepEqual(await deleteOnServer(deps(c.fetch, { install: () => undefined })), { ok: false, reason: 'account' })
  assert.equal(c.calls.length, 0)
})

test('logs never carry a token', async () => {
  const lines: string[] = []
  await deleteOnServer(deps(cloud([[403, { error: 'bad_access_token' }], [403, { error: 'bad_access_token' }], [500]]).fetch, { log: (l) => lines.push(l) }))
  assert.ok(lines.length > 0)
  for (const l of lines) assert.ok(!/mi_|jwt-/.test(l), l)
})
