/**
 * Auto-update (agents/auto-update.md), behind AUTO_UPDATE_ENABLED = false:
 *   locks      autoUpdateRequested (env ignored when packaged) and canAutoInstall (ad-hoc builds refused)
 *   codesign   parseCodesign reads Developer ID vs ad hoc
 *   channel    stable | beta, and a prerelease stays on beta
 *   feed       pinned when packaged; a dev override must be https (or http on localhost)
 *   configure  allowDowngrade stays false after the channel is set (electron-updater's setter flips it to true)
 *   policy     miyagi-cloud's minimum version and pulled builds → "required"
 *   main       with the flag off all four handles exist and are inert: no timer, no codesign, no network, no broadcast
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/autoUpdate.test.ts
 */
import assert from 'node:assert/strict'
import childProcess from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import autoUpdate from '../src/main/features/autoUpdate'
import {
  appBundleOf,
  AUTO_UPDATE_ENABLED,
  autoUpdateRequested,
  canAutoInstall,
  channelFor,
  configureUpdater,
  feedFor,
  parseChannel,
  parseCodesign,
  policyVerdict,
  readVersionPolicy,
  updaterChannel,
  type AutoView,
  type Feed,
  type UpdaterSettings
} from '../src/renderer/src/features/updates/auto'
import { makeHarness } from './harness'

const ADHOC = `Executable=/Applications/miyagi.app/Contents/MacOS/miyagi
Identifier=dev.sandhacks.miyagi
Format=app bundle with Mach-O universal (x86_64 arm64)
CodeDirectory v=20400 size=500 flags=0x2(adhoc) hashes=4+7 location=embedded
Signature=adhoc
Info.plist entries=30
TeamIdentifier=not set`

const DEVID = `Executable=/Applications/miyagi.app/Contents/MacOS/miyagi
Identifier=dev.sandhacks.miyagi
Authority=Developer ID Application: Example Name (ABCDE12345)
Authority=Developer ID Certification Authority
Authority=Apple Root CA
Timestamp=Nov 22, 2026 at 10:00:00
TeamIdentifier=ABCDE12345`

describe('locks', () => {
  test('off by default, everywhere', () => {
    assert.equal(AUTO_UPDATE_ENABLED, false)
    assert.equal(autoUpdateRequested(true, {}), false)
    assert.equal(autoUpdateRequested(false, {}), false)
  })
  test('a packaged build ignores MIYAGI_AUTO_UPDATE (A12)', () => {
    assert.equal(autoUpdateRequested(true, { MIYAGI_AUTO_UPDATE: '1' }), false)
    assert.equal(autoUpdateRequested(true, { MIYAGI_AUTO_UPDATE: '0' }, true), true)
  })
  test('a dev run honors MIYAGI_AUTO_UPDATE', () => {
    assert.equal(autoUpdateRequested(false, { MIYAGI_AUTO_UPDATE: '1' }), true)
    assert.equal(autoUpdateRequested(false, { MIYAGI_AUTO_UPDATE: 'on' }), true)
    assert.equal(autoUpdateRequested(false, { MIYAGI_AUTO_UPDATE: '0' }, true), false)
    assert.equal(autoUpdateRequested(false, { MIYAGI_AUTO_UPDATE: 'maybe' }), false)
  })
  test('today\'s ad-hoc build cannot update in place', () => {
    const r = canAutoInstall({ os: 'mac', packaged: true, signature: parseCodesign(ADHOC), bundleWritable: true })
    assert.equal(r.ok, false)
  })
  test('a Developer ID build in /Applications can', () => {
    assert.deepEqual(canAutoInstall({ os: 'mac', packaged: true, signature: parseCodesign(DEVID), bundleWritable: true }), { ok: true })
  })
  test('never from a dev run, the dmg, an unread signature, or Windows unless turned on', () => {
    const sig = parseCodesign(DEVID)
    assert.equal(canAutoInstall({ os: 'mac', packaged: false, signature: sig }).ok, false)
    assert.equal(canAutoInstall({ os: 'mac', packaged: true, signature: sig, bundleWritable: false }).ok, false)
    assert.equal(canAutoInstall({ os: 'mac', packaged: true }).ok, false)
    assert.equal(canAutoInstall({ os: 'windows', packaged: true }).ok, false)
    assert.equal(canAutoInstall({ os: 'windows', packaged: true, windows: true }).ok, true)
  })
})

describe('parseCodesign', () => {
  test('ad hoc', () => assert.deepEqual(parseCodesign(ADHOC), { developerId: false, teamId: undefined, adhoc: true }))
  test('Developer ID', () => assert.deepEqual(parseCodesign(DEVID), { developerId: true, teamId: 'ABCDE12345', adhoc: false }))
  test('another kind of certificate, or nothing', () => {
    assert.equal(parseCodesign(DEVID.replace('Developer ID Application', 'Apple Development')).developerId, false)
    assert.equal(parseCodesign('').developerId, false)
    assert.equal(parseCodesign(undefined).developerId, false)
  })
  test('the .app of this executable', () => {
    assert.equal(appBundleOf('/Applications/miyagi.app/Contents/MacOS/miyagi'), '/Applications/miyagi.app')
    assert.equal(appBundleOf('/usr/local/bin/electron'), undefined)
  })
})

describe('channel', () => {
  test('stable unless beta', () => {
    assert.equal(parseChannel('beta'), 'beta')
    assert.equal(parseChannel(' BETA '), 'beta')
    assert.equal(parseChannel('nightly'), 'stable')
    assert.equal(parseChannel(undefined), 'stable')
  })
  test('electron-updater names', () => {
    assert.equal(updaterChannel('stable'), 'latest')
    assert.equal(updaterChannel('beta'), 'beta')
  })
  test('a prerelease build stays on beta', () => {
    assert.equal(channelFor('0.3.0-beta.2', undefined), 'beta')
    assert.equal(channelFor('0.3.0', undefined), 'stable')
    assert.equal(channelFor('0.3.0', 'beta'), 'beta')
  })
})

describe('feedFor', () => {
  test('packaged: the official feed, env ignored', () => {
    assert.deepEqual(feedFor('mac', true, { MIYAGI_UPDATE_FEED: 'https://evil.example/mac' }), { provider: 'generic', url: 'https://downloads.miyagi.study/mac' })
  })
  test('dev: an https or localhost override, nothing else', () => {
    assert.deepEqual(feedFor('mac', false, { MIYAGI_UPDATE_FEED: 'http://127.0.0.1:8099/mac/' }), { provider: 'generic', url: 'http://127.0.0.1:8099/mac' })
    assert.equal(feedFor('mac', false, { MIYAGI_UPDATE_FEED: 'http://example.com/mac' }), undefined)
    assert.equal(feedFor('mac', false, { MIYAGI_UPDATE_FEED: 'https://u:p@example.com/mac' }), undefined)
    assert.equal(feedFor('mac', false, { MIYAGI_UPDATE_FEED: 'off' }), undefined)
    assert.deepEqual(feedFor('windows', false, {}), { provider: 'generic', url: 'https://downloads.miyagi.study/windows' })
  })
})

/**
 * Behaves like electron-updater 6.x's AppUpdater where it matters here: setting `channel` also sets
 * `allowDowngrade = true` (AppUpdater.channel setter). Records the order of writes.
 */
class FakeUpdater implements UpdaterSettings {
  autoDownload = false
  autoInstallOnAppQuit = false
  allowDowngrade = false
  allowPrerelease = false
  logger: unknown = console
  feeds: (Feed & { channel?: string })[] = []
  private _channel: string | null = null
  get channel(): string | null {
    return this._channel
  }
  set channel(value: string | null) {
    this._channel = value
    this.allowDowngrade = true
  }
  setFeedURL(options: Feed & { channel?: string }): void {
    this.feeds.push(options)
  }
}

describe('configureUpdater', () => {
  const feed = feedFor('mac', true, {})!
  test('stable: latest channel, no prereleases, and NO downgrades even though the channel setter allows them', () => {
    const u = new FakeUpdater()
    configureUpdater(u, feed, 'stable')
    assert.equal(u.channel, 'latest')
    assert.equal(u.allowPrerelease, false)
    assert.equal(u.allowDowngrade, false)
    assert.equal(u.autoDownload, true)
    assert.equal(u.autoInstallOnAppQuit, true)
    assert.equal(u.logger, null)
    assert.deepEqual(u.feeds, [{ provider: 'generic', url: 'https://downloads.miyagi.study/mac', channel: 'latest' }])
  })
  test('beta: beta channel, prereleases on, still no downgrades', () => {
    const u = new FakeUpdater()
    configureUpdater(u, feed, 'beta')
    assert.equal(u.channel, 'beta')
    assert.equal(u.allowPrerelease, true)
    assert.equal(u.allowDowngrade, false)
  })
  test('a beta tester who switches to Stable is not moved back to an older stable', () => {
    const u = new FakeUpdater()
    configureUpdater(u, feed, 'beta')
    configureUpdater(u, feed, 'stable')
    assert.equal(u.channel, 'latest')
    assert.equal(u.allowDowngrade, false)
    assert.equal(u.feeds.length, 2)
  })
  test('main configures only through configureUpdater (no stray channel or allowDowngrade writes)', () => {
    const src = readFileSync(join(__dirname, '..', 'src', 'main', 'features', 'autoUpdate.ts'), 'utf8')
    const code = src
      .split('\n')
      .filter((l) => !/^\s*(\*|\/\/|\/\*)/.test(l))
      .join('\n')
    assert.match(code, /configureUpdater\(u, feed, channel\(\)\)/)
    assert.doesNotMatch(code, /\.allowDowngrade\s*=/)
    assert.doesNotMatch(code, /\.channel\s*=(?!=)/)
  })
})

describe('minimum version', () => {
  test('below min, or a pulled build: required', () => {
    const p = readVersionPolicy({ min: '0.2.0', blocked: ['0.2.3', 'junk'], latest: '0.2.4' })
    assert.deepEqual(p, { min: '0.2.0', blocked: ['0.2.3'], latest: '0.2.4' })
    assert.equal(policyVerdict(p, '0.1.9'), 'required')
    assert.equal(policyVerdict(p, '0.2.0-beta.1'), 'required')
    assert.equal(policyVerdict(p, '0.2.3'), 'required')
    assert.equal(policyVerdict(p, '0.2.0'), 'ok')
    assert.equal(policyVerdict(p, '0.2.4'), 'ok')
  })
  test('no answer, a bad answer or an unreadable version never locks anyone out', () => {
    assert.equal(policyVerdict(undefined, '0.0.1'), 'ok')
    assert.equal(policyVerdict(readVersionPolicy('nope'), '0.0.1'), 'ok')
    assert.equal(policyVerdict(readVersionPolicy({ min: 'soon' }), '0.0.1'), 'ok')
    assert.equal(policyVerdict(readVersionPolicy({ min: '9.0.0' }), 'dev'), 'ok')
  })
})

describe('main feature with the flag off', () => {
  test('inert: all four handles answer, and none starts a timer, codesign, a network call or a broadcast', async () => {
    const before = process.env.MIYAGI_AUTO_UPDATE
    delete process.env.MIYAGI_AUTO_UPDATE
    const timers: string[] = []
    const spawned: string[] = []
    const fetched: string[] = []
    const real = { setTimeout: globalThis.setTimeout, setInterval: globalThis.setInterval, fetch: globalThis.fetch, execFile: childProcess.execFile }
    globalThis.setTimeout = ((...a: Parameters<typeof setTimeout>) => {
      timers.push('setTimeout')
      return real.setTimeout(...a)
    }) as typeof setTimeout
    globalThis.setInterval = ((...a: Parameters<typeof setInterval>) => {
      timers.push('setInterval')
      return real.setInterval(...a)
    }) as typeof setInterval
    globalThis.fetch = (async (input: string | URL | Request) => {
      fetched.push(String(input instanceof Request ? input.url : input))
      return new Response('{}', { status: 200 })
    }) as typeof fetch
    // autoUpdate.ts calls execFile through the module object (CommonJS under tsx), so this catches a codesign run.
    ;(childProcess as { execFile: unknown }).execFile = ((file: string) => {
      spawned.push(file)
      throw new Error(`unexpected child process ${file}`)
    }) as unknown
    const h = makeHarness()
    try {
      autoUpdate.setup(h.ctx)
      const v = (await h.invoke('autoUpdate:get')) as AutoView
      assert.equal(v.phase, 'off')
      assert.equal(v.required, false)
      const checked = (await h.invoke('autoUpdate:check')) as AutoView
      assert.equal(checked.phase, 'off')
      assert.equal(await h.invoke('autoUpdate:restart'), false)
      const file = join(h.dir, 'auto-update.json')
      assert.equal(existsSync(file), false)
      // The harness runs 0.0.0-test, a prerelease, so the view says beta whatever is saved (channelFor).
      const stable = (await h.invoke('autoUpdate:channel', 'stable')) as AutoView
      assert.equal(stable.phase, 'off')
      assert.equal(stable.channel, 'beta')
      assert.deepEqual(JSON.parse(readFileSync(file, 'utf8')), { channel: 'stable' }, 'the choice is saved even while off')
      const beta = (await h.invoke('autoUpdate:channel', 'beta')) as AutoView
      assert.equal(beta.channel, 'beta')
      assert.deepEqual(JSON.parse(readFileSync(file, 'utf8')), { channel: 'beta' })
      // Let anything the handles might have queued run before counting.
      await new Promise((r) => setImmediate(r))
      assert.deepEqual(timers, [])
      assert.deepEqual(spawned, [])
      assert.deepEqual(fetched, [])
      assert.deepEqual(h.broadcasts, [])
    } finally {
      globalThis.setTimeout = real.setTimeout
      globalThis.setInterval = real.setInterval
      globalThis.fetch = real.fetch
      ;(childProcess as { execFile: unknown }).execFile = real.execFile
      h.close()
      if (before !== undefined) process.env.MIYAGI_AUTO_UPDATE = before
    }
  })
})
