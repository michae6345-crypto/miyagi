/**
 * main/safeOpen.ts, offline (app-harden): what a setup card's Download button, the overview's Stats link and the
 * open:external IPC may open. Nothing really opens: the fake shell.openExternal only records the URL.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import overview, { enginePort, statsUrl } from '../src/main/features/overview'
import { isAllowedUrl, isBrowserLink, isEngineStatsUrl, isSetupDownloadUrl, openEngineStats, openSetupDownload, safeOpenExternal } from '../src/main/safeOpen'
import { opened, shell } from './fakes/electron'

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
    assert.deepEqual(r, { opened: false, refused: true, copy: 'https://fastcli-download.example/mac.pkg' })
    // The same through the renderer's channel (open:external with {setup}): the whole answer comes back.
    assert.deepEqual(await opens(() => safeOpenExternal({ setup: 'https://fastcli-download.example/mac.pkg' })), [])
    assert.deepEqual(await safeOpenExternal({ setup: 'https://fastcli-download.example/mac.pkg' }), { opened: false, refused: true, copy: 'https://fastcli-download.example/mac.pkg' })
  })

  test('the engine CATALOG download pages open', async () => {
    assert.deepEqual(await opens(() => openSetupDownload('https://www.python.org/downloads/')), ['https://www.python.org/downloads/'])
    assert.deepEqual(await safeOpenExternal({ setup: 'https://www.python.org/downloads/' }), { opened: true })
    for (const u of [
      'https://www.python.org/downloads/macos/',
      'https://python.org/downloads',
      'https://nodejs.org/en/download',
      'https://code.visualstudio.com/download',
      'https://brew.sh/',
      'https://git-scm.com/download/mac',
      'https://go.dev/dl/',
      'https://rustup.rs',
      'https://adoptium.net',
      'https://www.docker.com/products/docker-desktop/',
      'https://www.blender.org/download/',
      'https://www.figma.com/downloads/',
      'https://unity.com/download',
      'https://jupyter.org/install',
      'https://pypi.org/project/ipykernel/',
      'https://github.com/python/cpython/releases',
      'https://github.com/python/cpython/releases/tag/v3.12.0',
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
    assert.deepEqual(await openSetupDownload('https://youtube.com@evil.example/'), { opened: false, refused: true })
    assert.deepEqual(await openSetupDownload('javascript:alert(1)'), { opened: false, refused: true })
    assert.deepEqual(await openSetupDownload(42), { opened: false, refused: true })
  })

  test('ATTACK third-party pages on official hosts: subdomains, other paths, any package or repo page are refused', async () => {
    for (const u of [
      'https://pkg.go.dev/github.com/evil/fastcli', // anyone's Go module
      'https://go.dev/github.com/evil/fastcli',
      'https://discuss.python.org/t/fastcli', // a forum post
      'https://www.python.org/community/', // the official host, not a download page
      'https://www.python.org/downloads-evil/', // a lookalike segment
      'https://hub.docker.com/r/evil/fastcli', // anyone's image
      'https://evil.figma.com/downloads/',
      'https://pypi.org/project/fastcli/', // anyone's package
      'https://pypi.org/project/ipykernel-evil/',
      'https://github.com/microsoft/vscode/issues/1', // anyone can write an issue
      'https://github.com/microsoft/vscode/blob/main/x.sh',
      'https://github.com/microsoft', // an org page, not a repo
      'https://github.com/python/cpython/wiki/Download',
      'https://brew.sh/evil', // brew.sh: the home page only
      'https://rustup.rs/x'
    ]) {
      assert.equal(isSetupDownloadUrl(u), false, u)
      assert.deepEqual(await opens(() => openSetupDownload(u)), [], u)
    }
  })

  test('a link on the list the system fails to open says failed, not refused', async () => {
    const real = shell.openExternal
    shell.openExternal = async () => {
      throw new Error('no browser')
    }
    try {
      assert.deepEqual(await openSetupDownload('https://www.python.org/downloads/'), { opened: false, refused: false })
      assert.deepEqual(await safeOpenExternal({ setup: 'https://www.python.org/downloads/' }), { opened: false, refused: false })
    } finally {
      shell.openExternal = real
    }
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
  test('ATTACK open:external (safeOpenExternal) never opens a loopback page, the engine’s /stats included', async () => {
    for (const u of ['http://localhost:8787/stats', 'http://127.0.0.1:6379/stats', 'http://[::1]:9200/stats', 'http://localhost:8787/']) {
      assert.equal(await safeOpenExternal(u), false, u)
      assert.deepEqual(await opens(() => safeOpenExternal(u)), [], u)
    }
  })

  test('only the local engine’s /stats on the engine’s own port', async () => {
    assert.equal(statsUrl('ws://localhost:8787'), 'http://localhost:8787/stats')
    assert.equal(enginePort('ws://localhost:8787'), 8787)
    assert.equal(enginePort('ws://127.0.0.1:9000'), 9000)
    assert.equal(isEngineStatsUrl('http://localhost:8787/stats', 8787), true)
    assert.equal(isEngineStatsUrl('http://127.0.0.1:8787/stats', 8787), true)
    assert.equal(isEngineStatsUrl('http://[::1]:8787/stats', 8787), true)
    for (const u of [
      'http://localhost:6379/stats', // another local service
      'http://127.0.0.1/stats',
      'http://evil.example:8787/stats',
      'http://localhost:8787/stats?x=1',
      'http://localhost:8787/admin',
      'http://user@localhost:8787/stats',
      'file:///stats'
    ]) {
      assert.equal(isEngineStatsUrl(u, 8787), false, u)
      assert.deepEqual(await opens(() => openEngineStats(u, 8787)), [], u)
    }
  })

  test('the footer link opens the local engine’s /stats; an engine on another host does not', async () => {
    const handlers = new Map<string, () => unknown>()
    overview.setup({ handle: (c: string, fn: () => unknown) => handlers.set(c, fn) } as never)
    const before = process.env.ENGINE_URL
    try {
      process.env.ENGINE_URL = 'ws://localhost:8787'
      assert.deepEqual(await opens(async () => assert.equal(await handlers.get('overview:open-stats')?.(), true)), ['http://localhost:8787/stats'])
      process.env.ENGINE_URL = 'ws://127.0.0.1:9100'
      assert.deepEqual(await opens(async () => assert.equal(await handlers.get('overview:open-stats')?.(), true)), ['http://127.0.0.1:9100/stats'])
      process.env.ENGINE_URL = 'ws://evil.example:8787'
      assert.deepEqual(await opens(async () => assert.equal(await handlers.get('overview:open-stats')?.(), false)), [])
    } finally {
      if (before === undefined) delete process.env.ENGINE_URL
      else process.env.ENGINE_URL = before
    }
  })
})
