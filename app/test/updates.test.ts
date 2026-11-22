/**
 * R26 step 2 (A13): the update card trusts only the official release assets,
 * https://github.com/adrian-erlikhman/miyagi/releases/download/<tag>/<asset>, with each platform's asset name.
 *
 *   officialInstaller   the pin itself (features/updates/manifest.ts): exact URLs in, every near miss out
 *   readRelease         a GitHub release or a manifest with anything else gives no offer (an official asset beside a
 *                       stray one still wins); assets mid-upload are skipped
 *   main                features/updates.ts against a stubbed fetch: an off-pin release shows nothing and opens
 *                       nothing; an official one opens exactly its URL
 *   packaged            A12 / R33: a packaged build ignores MIYAGI_UPDATE_URL and MIYAGI_RELEASE_REPO and reads only
 *                       the official release source; a dev run still honors them
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, test } from 'node:test'
import updates from '../src/main/features/updates'
import { OFFICIAL_ASSETS, officialInstaller, readRelease, sourceForRun, type UpdateView } from '../src/renderer/src/features/updates/manifest'
import { opened } from './fakes/electron'
import { makeHarness, type Harness } from './harness'

const BASE = 'https://github.com/adrian-erlikhman/miyagi/releases/download'
const MAC = `${BASE}/mac/Miyagi-Mac.dmg`
const WIN = `${BASE}/windows/Miyagi-Windows-Setup.exe`

describe('officialInstaller (the pin)', () => {
  test('the official assets, per platform, on the rolling and versioned tags', () => {
    assert.deepEqual(OFFICIAL_ASSETS, { mac: ['Miyagi-Mac.dmg'], windows: ['Miyagi-Windows-Setup.exe'] })
    assert.deepEqual(officialInstaller(MAC, 'mac'), { tag: 'mac', asset: 'Miyagi-Mac.dmg' })
    assert.deepEqual(officialInstaller(WIN, 'windows'), { tag: 'windows', asset: 'Miyagi-Windows-Setup.exe' })
    assert.deepEqual(officialInstaller(`${BASE}/v0.2.0/Miyagi-Mac.dmg`, 'mac'), { tag: 'v0.2.0', asset: 'Miyagi-Mac.dmg' })
    assert.deepEqual(officialInstaller(`${BASE}/v1.0.0-beta.2/Miyagi-Mac.dmg`, 'mac'), { tag: 'v1.0.0-beta.2', asset: 'Miyagi-Mac.dmg' })
  })

  test('ATTACK everything else is refused', () => {
    const refused: [unknown, 'mac' | 'windows'][] = [
      // another platform's installer, another file, another name
      [WIN, 'mac'],
      [MAC, 'windows'],
      [`${BASE}/mac/Miyagi-Mac.zip`, 'mac'],
      [`${BASE}/mac/Miyagi-Mac.dmg.exe`, 'mac'],
      [`${BASE}/mac/miyagi-mac.dmg`, 'mac'],
      [`${BASE}/windows/Miyagi-Windows.exe`, 'windows'],
      // another repo or owner (a fork, a look-alike, a renamed account)
      ['https://github.com/adrian-erlikhman/miyagi-evil/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://github.com/someone-else/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://github.com/michae6345-crypto/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://github.com/Adrian-Erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      // another host, scheme, port or user
      ['https://objects.githubusercontent.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://github.com.evil.example/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://gist.github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://www.github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://GitHub.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['http://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://github.com:443/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      ['https://user@github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'mac'],
      // another path: latest/, an extra segment, traversal, encoding, a query or fragment, a trailing slash
      ['https://github.com/adrian-erlikhman/miyagi/releases/latest/download/Miyagi-Mac.dmg', 'mac'],
      [`${BASE}/mac/x/Miyagi-Mac.dmg`, 'mac'],
      [`${BASE}/../../evil/miyagi/releases/download/mac/Miyagi-Mac.dmg`, 'mac'],
      [`${BASE}/mac/..%2FMiyagi-Mac.dmg`, 'mac'],
      [`${BASE}/mac%2F..%2Fevil/Miyagi-Mac.dmg`, 'mac'],
      [`${BASE}/mac/Miyagi-Mac%2Edmg`, 'mac'],
      [`${MAC}?x=1`, 'mac'],
      [`${MAC}#x`, 'mac'],
      [`${MAC}/`, 'mac'],
      [`${BASE}//Miyagi-Mac.dmg`, 'mac'],
      [`${BASE}/latest/Miyagi-Mac.dmg`, 'mac'],
      [`${BASE}/v1.2/Miyagi-Mac.dmg`, 'mac'],
      [` ${MAC}`, 'mac'],
      [`${MAC}\n`, 'mac'],
      // not a string
      [undefined, 'mac'],
      [{ toString: () => MAC }, 'mac']
    ]
    for (const [url, os] of refused) assert.equal(officialInstaller(url, os), undefined, `${String(url)} (${os})`)
  })
})

/** The rolling release as api.github.com/repos/adrian-erlikhman/miyagi/releases/tags/<tag> returns it. */
const release = (assets: Record<string, unknown>[], tag = 'mac'): Record<string, unknown> => ({ tag_name: tag, name: 'miyagi 0.2.0', draft: false, prerelease: false, body: 'Version: 0.2.0', assets })
const dmg = (over: Record<string, unknown> = {}): Record<string, unknown> => ({ name: 'Miyagi-Mac.dmg', state: 'uploaded', size: 126_000_000, digest: `sha256:${'a'.repeat(64)}`, browser_download_url: MAC, ...over })

describe('readRelease keeps only official assets', () => {
  test('the official dmg is offered, with its digest; the zip next to it is ignored', () => {
    const r = readRelease(release([{ name: 'Miyagi-Mac.zip', state: 'uploaded', browser_download_url: `${BASE}/mac/Miyagi-Mac.zip` }, dmg()]), 'mac', 'arm64')
    assert.equal(r?.url, MAC)
    assert.equal(r?.version, '0.2.0')
    assert.equal(r?.sha256, 'a'.repeat(64))
  })

  test('ATTACK a stray installer beside the official one never wins, even when it names this arch', () => {
    const stray = { name: 'Miyagi-Mac-arm64.dmg', state: 'uploaded', browser_download_url: 'https://github.com/someone-else/x/releases/download/mac/Miyagi-Mac-arm64.dmg' }
    assert.equal(readRelease(release([stray, dmg()]), 'mac', 'arm64')?.url, MAC)
  })

  test('ATTACK no offer for: another repo’s URL under the official name, another tag than the release’s, an asset mid-upload, an unknown name', () => {
    assert.equal(readRelease(release([dmg({ browser_download_url: 'https://github.com/someone-else/miyagi/releases/download/mac/Miyagi-Mac.dmg' })]), 'mac', 'arm64'), undefined)
    assert.equal(readRelease(release([dmg({ browser_download_url: `${BASE}/windows/Miyagi-Mac.dmg` })]), 'mac', 'arm64'), undefined)
    assert.equal(readRelease(release([dmg()], 'windows'), 'mac', 'arm64'), undefined)
    assert.equal(readRelease(release([dmg({ state: 'starter' })]), 'mac', 'arm64'), undefined)
    assert.equal(readRelease(release([dmg({ state: 'open' })]), 'mac', 'arm64'), undefined)
    assert.equal(readRelease(release([dmg({ name: 'Miyagi-Mac-2.dmg' })]), 'mac', 'arm64'), undefined)
  })

  test('Windows: Miyagi-Windows-Setup.exe on the windows release', () => {
    const exe = { name: 'Miyagi-Windows-Setup.exe', state: 'uploaded', browser_download_url: WIN }
    assert.equal(readRelease(release([exe], 'windows'), 'windows', 'x64')?.url, WIN)
    assert.equal(readRelease(release([{ ...exe, name: 'Miyagi-Windows.exe', browser_download_url: `${BASE}/windows/Miyagi-Windows.exe` }], 'windows'), 'windows', 'x64'), undefined)
  })

  test('ATTACK a manifest (any host) offers only an official URL', () => {
    assert.equal(readRelease({ version: '0.2.0', url: MAC, sha256: 'b'.repeat(64) }, 'mac', 'arm64')?.url, MAC)
    assert.equal(readRelease({ mac: { version: '0.2.0', dmg: MAC } }, 'mac', 'arm64')?.url, MAC)
    // The install steps name the pinned asset, never free text from the manifest.
    assert.equal(readRelease({ version: '0.2.0', url: MAC, file: 'Terminal, then paste this' }, 'mac', 'arm64')?.file, 'Miyagi-Mac.dmg')
    for (const url of ['https://downloads.miyagi.study/mac/Miyagi-Mac.dmg', 'https://github.com/someone-else/miyagi/releases/download/mac/Miyagi-Mac.dmg', 'https://evil.example/Miyagi-Mac.dmg']) {
      assert.equal(readRelease({ version: '0.2.0', url }, 'mac', 'arm64'), undefined, url)
    }
  })
})

describe('main: the card shows nothing off the pin, and opens only the official URL', () => {
  let h: Harness
  let answer: unknown
  const before = globalThis.fetch
  const env = process.env.MIYAGI_UPDATE_URL
  const fetched: string[] = []

  beforeEach(() => {
    process.env.MIYAGI_UPDATE_URL = 'https://updates.test/latest.json'
    globalThis.fetch = (async (input: string | URL | Request) => {
      fetched.push(String(input))
      return new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch
    h = makeHarness()
    updates.setup(h.ctx)
  })
  afterEach(() => {
    h.close()
    globalThis.fetch = before
    if (env === undefined) delete process.env.MIYAGI_UPDATE_URL
    else process.env.MIYAGI_UPDATE_URL = env
  })

  const os = process.platform === 'win32' ? 'windows' : 'mac'
  const official = os === 'windows' ? WIN : MAC

  test('ATTACK an off-pin github.com installer: no offer, no card, Download opens nothing', async () => {
    answer = { version: '9.9.9', url: 'https://github.com/someone-else/miyagi/releases/download/mac/Miyagi-Mac.dmg' }
    const v = (await h.invoke('updates:check')) as UpdateView
    assert.equal(fetched.at(-1), 'https://updates.test/latest.json')
    assert.equal(v.phase, 'current')
    assert.equal(v.latest, undefined)
    const n = opened.length
    const d = (await h.invoke('updates:download')) as UpdateView
    assert.equal(d.latest, undefined)
    assert.equal(opened.length, n, 'nothing opened')
  })

  test('a dev run honors MIYAGI_UPDATE_URL (it is what this test reads from)', async () => {
    answer = { version: '9.9.9', url: official }
    await h.invoke('updates:check')
    assert.equal(fetched.at(-1), 'https://updates.test/latest.json')
  })

  test('the official asset: offered, and Download opens exactly that URL', async () => {
    answer = { version: '9.9.9', url: official, sha256: 'c'.repeat(64) }
    const v = (await h.invoke('updates:check')) as UpdateView
    assert.equal(v.phase, 'available')
    assert.equal(v.latest?.version, '9.9.9')
    assert.equal(v.latest?.host, 'github.com')
    const n = opened.length
    const d = (await h.invoke('updates:download')) as UpdateView
    assert.equal(d.opened, true)
    assert.deepEqual(opened.slice(n), [official])
  })
})

describe('A12 / R33: a packaged build ignores the environment and reads only the official release source', () => {
  const OFFICIAL_SOURCE = (os: 'mac' | 'windows'): string => `https://api.github.com/repos/adrian-erlikhman/miyagi/releases/tags/${os}`
  const hostile = { MIYAGI_UPDATE_URL: 'https://evil.example/latest.json', MIYAGI_RELEASE_REPO: 'someone-else/miyagi' }

  test('sourceForRun: packaged → the official source whatever the env says (even "off"); dev → the env, only when set', () => {
    for (const os of ['mac', 'windows'] as const) {
      const want = { url: OFFICIAL_SOURCE(os), kind: 'github' }
      assert.deepEqual(sourceForRun(true, hostile, os), want)
      assert.deepEqual(sourceForRun(true, { MIYAGI_UPDATE_URL: 'http://127.0.0.1:9999/latest.json' }, os), want)
      assert.deepEqual(sourceForRun(true, { MIYAGI_UPDATE_URL: 'off' }, os), want)
      assert.deepEqual(sourceForRun(true, { MIYAGI_RELEASE_REPO: 'someone-else/miyagi' }, os), want)
      assert.deepEqual(sourceForRun(true, {}, os), want)
    }
    assert.equal(sourceForRun(false, {}, 'mac'), undefined, 'dev without MIYAGI_UPDATE_URL: never looks')
    assert.equal(sourceForRun(false, { MIYAGI_UPDATE_URL: 'off' }, 'mac'), undefined)
    assert.deepEqual(sourceForRun(false, { MIYAGI_UPDATE_URL: 'https://updates.test/latest.json' }, 'mac'), { url: 'https://updates.test/latest.json', kind: 'manifest' })
    assert.deepEqual(sourceForRun(false, { MIYAGI_UPDATE_URL: 'http://localhost:8080/m.json' }, 'mac'), { url: 'http://localhost:8080/m.json', kind: 'manifest' })
  })

  test('main, packaged, with a hostile MIYAGI_UPDATE_URL and MIYAGI_RELEASE_REPO set: the check goes to the official release', async () => {
    const os = process.platform === 'win32' ? 'windows' : 'mac'
    const saved = { url: process.env.MIYAGI_UPDATE_URL, repo: process.env.MIYAGI_RELEASE_REPO }
    const before = globalThis.fetch
    const fetched: string[] = []
    process.env.MIYAGI_UPDATE_URL = hostile.MIYAGI_UPDATE_URL
    process.env.MIYAGI_RELEASE_REPO = hostile.MIYAGI_RELEASE_REPO
    globalThis.fetch = (async (input: string | URL | Request) => {
      fetched.push(String(input))
      const asset = os === 'mac' ? { name: 'Miyagi-Mac.dmg', state: 'uploaded', browser_download_url: MAC } : { name: 'Miyagi-Windows-Setup.exe', state: 'uploaded', browser_download_url: WIN }
      return new Response(JSON.stringify(release([asset], os)), { status: 200 })
    }) as typeof fetch
    const h = makeHarness()
    try {
      ;(h.ctx.app as unknown as { isPackaged: boolean }).isPackaged = true
      updates.setup(h.ctx)
      assert.equal(((await h.invoke('updates:get')) as UpdateView).phase, 'idle', 'packaged: checks are on')
      const v = (await h.invoke('updates:check')) as UpdateView
      assert.deepEqual(fetched, [OFFICIAL_SOURCE(os)], 'never the env URL or repo')
      assert.equal(v.phase, 'available')
      assert.equal(v.latest?.version, '0.2.0')
    } finally {
      h.close()
      globalThis.fetch = before
      for (const [k, val] of [['MIYAGI_UPDATE_URL', saved.url], ['MIYAGI_RELEASE_REPO', saved.repo]] as const) {
        if (val === undefined) delete process.env[k]
        else process.env[k] = val
      }
    }
  })
})
