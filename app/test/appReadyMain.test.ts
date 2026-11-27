/**
 * Lane C (michael/app-ready-main), offline, the main-process parts that need no window:
 *
 *   location     a built Mac app outside Applications offers the move (features/location.ts shouldOfferMove), once per
 *                version after Not now
 *   localEngine  an engine-less copy points at miyagi.study, not the team repo; the engine is spawned with
 *                umask 077; an outdated companion (below the bundled one, so always below 0.0.7) updates quietly
 *
 * Nothing is spawned, no dialog opens, no network. Run from app/:
 *   node --import tsx --import ./test/setup.mjs --test --test-force-exit test/appReadyMain.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, describe, test } from 'node:test'

// localEngine.ts imports ipcMain and clipboard: add them to the shared electron fake (as engineIsolation.test.ts does).
// eslint-disable-next-line @typescript-eslint/no-require-imports
const electron = require('electron') as Record<string, unknown>
if (!electron.ipcMain) Object.defineProperty(electron, 'ipcMain', { value: { handle: () => undefined }, enumerable: true })
if (!electron.clipboard) Object.defineProperty(electron, 'clipboard', { value: { writeText: () => undefined }, enumerable: true })
// eslint-disable-next-line @typescript-eslint/no-require-imports
const le = require('../src/main/localEngine') as typeof import('../src/main/localEngine')
// eslint-disable-next-line @typescript-eslint/no-require-imports
const loc = require('../src/main/features/location') as typeof import('../src/main/features/location')

const dir = mkdtempSync(join(tmpdir(), 'miyagi-ready-'))
after(() => rmSync(dir, { recursive: true, force: true }))

describe('move to Applications', () => {
  const base = { platform: 'darwin', packaged: true, inApplications: false, version: '0.1.1' }

  test('a packaged build outside /Applications offers the move', () => {
    assert.equal(loc.shouldOfferMove(base), true)
  })
  test('not in Applications only: inside it, in npm run dev, on Windows or with MIYAGI_NO_MOVE, never', () => {
    assert.equal(loc.shouldOfferMove({ ...base, inApplications: true }), false)
    assert.equal(loc.shouldOfferMove({ ...base, packaged: false }), false)
    assert.equal(loc.shouldOfferMove({ ...base, platform: 'win32' }), false)
    assert.equal(loc.shouldOfferMove({ ...base, off: true }), false)
  })
  test('Not now holds for this version only; an update asks again', () => {
    const file = join(dir, loc.LOCATION_FILE)
    assert.equal(loc.readDeclined(file), undefined)
    loc.writeDeclined(file, '0.1.1')
    assert.equal(loc.readDeclined(file), '0.1.1')
    assert.equal(statSync(file).mode & 0o777, 0o600)
    assert.equal(loc.shouldOfferMove({ ...base, declined: loc.readDeclined(file) }), false)
    assert.equal(loc.shouldOfferMove({ ...base, version: '0.1.2', declined: loc.readDeclined(file) }), true)
    writeFileSync(file, '{not json')
    assert.equal(loc.readDeclined(file), undefined)
  })
  test('copy: calm, short, lowercase miyagi, no em dash', () => {
    for (const s of Object.values(loc.MOVE_COPY)) {
      assert.ok(s.trim().split(/\s+/).length <= 12, s)
      assert.ok(!/M(?=iyagi)/.test(s), s)
      assert.ok(!s.includes(String.fromCharCode(0x2014)), s)
    }
  })
  test('offerMoveToApplications is a no-op in a dev run (never a dialog here)', async () => {
    assert.equal(await loc.offerMoveToApplications(), false)
  })
})

describe('the engine on this Mac', () => {
  test('an engine-less copy points at the public site, never at the team repo (it goes private)', () => {
    assert.ok(le.MISSING_LINE.includes('miyagi.study'))
    assert.ok(!/github|curl/.test(le.MISSING_LINE))
    assert.ok(!('ONE_LINER' in le), 'no install one-liner into michae6345-crypto/miyagi')
  })

  test('umask 077 around the spawn, the old one back after', () => {
    if (process.platform === 'win32') return
    const before = join(dir, 'before.txt')
    writeFileSync(before, 'x')
    const usual = statSync(before).mode & 0o777
    const inside = join(dir, 'inside.txt')
    const r = le.withPrivateUmask(() => {
      writeFileSync(inside, 'x')
      return 7
    })
    assert.equal(r, 7)
    assert.equal(statSync(inside).mode & 0o777, 0o600)
    const afterFile = join(dir, 'after.txt')
    writeFileSync(afterFile, 'x')
    assert.equal(statSync(afterFile).mode & 0o777, usual, 'the app keeps its own umask')
    // a throw still puts it back
    assert.throws(() =>
      le.withPrivateUmask(() => {
        throw new Error('spawn failed')
      })
    )
    const again = join(dir, 'again.txt')
    writeFileSync(again, 'x')
    assert.equal(statSync(again).mode & 0o777, usual)
  })

  test('the companion: an outdated one updates quietly in a built app; nothing else does', () => {
    assert.equal(le.compareVersions('0.0.6', le.COMPANION_MIN) < 0, true)
    assert.equal(le.autoUpdateCompanion({ state: 'outdated', version: '0.0.6', bundled: '0.0.8' }, true), true)
    assert.equal(le.autoUpdateCompanion({ state: 'outdated', version: '0.0.7', bundled: '0.0.8' }, true), true)
    assert.equal(le.autoUpdateCompanion({ state: 'outdated', version: '0.0.6', bundled: '0.0.8' }, false), false, 'never in npm run dev')
    assert.equal(le.autoUpdateCompanion({ state: 'installed', version: '0.0.8', bundled: '0.0.8' }, true), false)
    assert.equal(le.autoUpdateCompanion({ state: 'missing', bundled: '0.0.8' }, true), false, 'a first install stays the learner’s button')
    assert.equal(le.autoUpdateCompanion({ state: 'no-vscode', bundled: '0.0.8' }, true), false)
  })
})
