/**
 * Lane C (michael/app-ready-main): the update card reads the "mac" release the way ship-mac.sh --publish leaves it.
 * The notes come from the real scripts/release-notes.sh (bash, prints only); the release object is what the GitHub
 * Releases API answers after `gh release upload mac Miyagi-Mac.dmg` and `gh release edit mac --title "miyagi <v>"`.
 * Nothing is built, uploaded or fetched. Run from app/:
 *   node --import tsx --import ./test/setup.mjs --test --test-force-exit test/shipRelease.test.ts
 */
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { cleanNotes, isNewer, readRelease } from '../src/renderer/src/features/updates/manifest'

const APP = join(__dirname, '..')
const VERSION = (JSON.parse(readFileSync(join(APP, 'package.json'), 'utf8')) as { version: string }).version
const BUILD = '1d453ca0'
const DIGEST = 'a'.repeat(64)

const notes = (version = VERSION, build = BUILD): string => execFileSync('bash', [join(APP, 'scripts', 'release-notes.sh'), version, build], { encoding: 'utf8' })

/** The Releases API's answer for tag "mac" after a ship-mac.sh --publish. */
function shipped(body: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    tag_name: 'mac',
    name: `miyagi ${VERSION}`,
    draft: false,
    prerelease: false,
    body,
    assets: [
      {
        name: 'Miyagi-Mac.dmg',
        state: 'uploaded',
        size: 182_000_000,
        digest: `sha256:${DIGEST}`,
        browser_download_url: 'https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg'
      },
      {
        name: 'Miyagi-Mac.zip',
        state: 'uploaded',
        browser_download_url: 'https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.zip'
      }
    ],
    ...over
  }
}

describe('readRelease on ship-mac.sh output', () => {
  test('this build is 0.1.1', () => {
    assert.equal(VERSION, '0.1.1')
  })

  test('the notes say how to install, with the version and build', () => {
    const body = notes()
    assert.match(body, /Open the DMG and drag miyagi to Applications\./)
    assert.match(body, /Privacy & Security, Open Anyway/)
    assert.match(body, /No setup needed/)
    assert.match(body, new RegExp(`^Version: ${VERSION.replace(/\./g, '\\.')}$`, 'm'))
    assert.match(body, new RegExp(`^Build ${BUILD}$`, 'm'))
    assert.ok(!/unzip|right-click|needs internet/i.test(body), 'none of the old release text')
    assert.ok(!body.includes(String.fromCharCode(0x2014)), 'no em dash')
    assert.ok(!/M(?=iyagi)/.test(body), 'lowercase miyagi')
  })

  test('the script refuses junk arguments', () => {
    assert.throws(() => notes('0.1.1; rm', BUILD))
    assert.throws(() => notes(VERSION, 'not-a-sha'))
  })

  test('version from the title, the dmg and its digest, notes without version or build lines', () => {
    const r = readRelease(shipped(notes()), 'mac', 'arm64')
    assert.ok(r, 'a release')
    assert.equal(r.version, VERSION)
    assert.equal(r.url, 'https://github.com/adrian-erlikhman/miyagi/releases/download/mac/Miyagi-Mac.dmg')
    assert.equal(r.file, 'Miyagi-Mac.dmg')
    assert.equal(r.sha256, DIGEST)
    assert.equal(r.size, 182_000_000)
    assert.deepEqual(r.notes, ['Open the DMG and drag miyagi to Applications.', 'If macOS stops it: System Settings, Privacy & Security, Open Anyway.', 'No setup needed. The engine is inside the app.'])
    assert.equal(isNewer(r, '0.1.0'), true, '0.1.0 is offered the update')
    assert.equal(isNewer(r, VERSION), false)
  })

  test('the Version line alone is enough when the title was not edited', () => {
    const r = readRelease(shipped(notes(), { name: 'mac' }), 'mac', 'arm64')
    assert.equal(r?.version, VERSION)
  })

  test('cleanNotes drops a Build line but keeps a sentence that starts with Build', () => {
    assert.deepEqual(cleanNotes('Build 1d453ca0\nBuild lessons faster.'), ['Build lessons faster.'])
  })

  test('ship-mac.sh --publish titles the release and writes these notes', () => {
    const sh = readFileSync(join(APP, 'scripts', 'ship-mac.sh'), 'utf8')
    assert.ok(sh.includes('gh release edit mac --title "miyagi $VERSION" --notes-file "$NOTES" --repo "$REPO"'))
    assert.ok(sh.includes('bash scripts/release-notes.sh "$VERSION" "$BUILD" > "$NOTES"'))
  })
})
