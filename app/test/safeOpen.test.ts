/**
 * main/safeOpen.ts, offline (app-harden): what a setup card's Download button, the overview's Stats link and the
 * open:external IPC may open. Nothing really opens: the fake shell.openExternal only records the URL.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import overview, { statsUrl } from '../src/main/features/overview'
import { isAllowedUrl, isBrowserLink, isEngineStatsUrl, isSetupDownloadUrl, openSetupDownload, safeOpenExternal } from '../src/main/safeOpen'
import { opened } from './fakes/electron'

/** Run fn and return the URLs it asked the system browser to open. */
async function opens(fn: () => Promise<unknown>): Promise<string[]> {
  const before = opened.length
  await fn()
  return opened.slice(before)
}

describe('setup downloads (a setup card from the engine)', () => {
  test('ATTACK an injected download host is never opened: handed back as copy-only text', async () => {
    let r: unknown
    const got = await opens(async () => (r = await openSetupDownload('https://fastcli-download.example/mac.pkg')))
    assert.deepEqual(got, [])
    assert.deepEqual(r, { opened: false, copy: 'https://fastcli-download.example/mac.pkg' })
    // The same through the renderer's channel (open:external with {setup}).
    assert.deepEqual(await opens(() => safeOpenExternal({ setup: 'https://fastcli-download.example/mac.pkg' })), [])
    assert.equal(await safeOpenExternal({ setup: 'https://fastcli-download.example/mac.pkg' }), false)
  })

  test('the official download pages open', async () => {
    assert.deepEqual(await opens(() => openSetupDownload('https://www.python.org/downloads/')), ['https://www.python.org/downloads/'])
    assert.equal(await safeOpenExternal({ setup: 'https://www.python.org/downloads/' }), true)
    for (const u of [
      'https://nodejs.org/en/download',
      'https://code.visualstudio.com/download',
      'https://brew.sh/',
      'https://git-scm.com/download/mac',
      'https://go.dev/dl/',
      'https://rustup.rs',
      'https://jupyter.org/install',
      'https://github.com/python/cpython/releases',
      'https://github.com/nvm-sh/nvm'
    ]) {
      assert.equal(isSetupDownloadUrl(u), true, u)
    }
  })

  test('ATTACK lookalikes, userinfo, other ports and schemes, any GitHub org are refused', async () => {
    for (const u of [
      'https://youtube.com@evil.example/', // userinfo: the browser goes to evil.example
      'https://www.python.org@evil.example/python.pkg',
      'https://user:pw@www.python.org/downloads/',
      'https://python.org.evil.example/downloads/',
      'https://evilpython.org/downloads/',
      'https://www.python.org:8443/downloads/',
      'http://www.python.org/downloads/',
      'javascript:alert(1)',
      'file:///Applications/Calculator.app',
      'https://github.com/evil-org/fastcli/releases/download/v1/mac.pkg',
      'https://gist.github.com/python/abc',
      'https://raw.githubusercontent.com/python/cpython/main/x.sh',
      'https://cursor.com/downloads', // in the engine's CATALOG, never offered (No Cursor)
      'https://x'.padEnd(3000, 'x')
    ]) {
      assert.equal(isSetupDownloadUrl(u), false, u)
      assert.deepEqual(await opens(() => openSetupDownload(u)), [], u)
    }
    // A userinfo URL is not even offered as text to copy.
    assert.deepEqual(await openSetupDownload('https://youtube.com@evil.example/'), { opened: false })
    assert.deepEqual(await openSetupDownload('javascript:alert(1)'), { opened: false })
    assert.deepEqual(await openSetupDownload(42), { opened: false })
  })

  test('ATTACK userinfo is refused by every opener, not just setup', async () => {
    const u = 'https://youtube.com@evil.example/'
    assert.equal(isAllowedUrl(u), false)
    assert.equal(isBrowserLink(u), false)
    assert.deepEqual(await opens(() => safeOpenExternal(u)), [])
  })

  test('the general allowlist did not grow: setup hosts open only through {setup}', async () => {
    assert.equal(isAllowedUrl('https://www.python.org/downloads/'), false)
    assert.deepEqual(await opens(() => safeOpenExternal('https://www.python.org/downloads/')), [])
    assert.equal(isAllowedUrl('https://www.youtube.com/watch?v=abc'), true)
  })
})

describe('overview Stats link', () => {
  test('goes through safeOpenExternal: the local engine’s /stats opens, another host does not', async () => {
    assert.equal(statsUrl('ws://localhost:8787'), 'http://localhost:8787/stats')
    assert.equal(isEngineStatsUrl('http://localhost:8787/stats'), true)
    assert.equal(isEngineStatsUrl('http://127.0.0.1:8787/stats'), true)
    for (const u of ['http://evil.example:8787/stats', 'http://localhost:8787/stats?x=1', 'http://localhost:8787/admin', 'http://user@localhost:8787/stats', 'file:///stats']) {
      assert.equal(isEngineStatsUrl(u), false, u)
    }

    const handlers = new Map<string, () => unknown>()
    overview.setup({ handle: (c: string, fn: () => unknown) => handlers.set(c, fn) } as never)
    const before = process.env.ENGINE_URL
    try {
      process.env.ENGINE_URL = 'ws://localhost:8787'
      assert.deepEqual(await opens(async () => assert.equal(await handlers.get('overview:open-stats')?.(), true)), ['http://localhost:8787/stats'])
      process.env.ENGINE_URL = 'ws://evil.example:8787'
      assert.deepEqual(await opens(async () => assert.equal(await handlers.get('overview:open-stats')?.(), false)), [])
    } finally {
      if (before === undefined) delete process.env.ENGINE_URL
      else process.env.ENGINE_URL = before
    }
  })
})
