/**
 * The Mac download has one set of names, and every place that reads or writes them has to agree (RELEASING.md, "Who
 * reads which name"; the names live in .github/scripts/release-notes.mjs):
 *
 *   names        the release scripts and the workflow publish the names the in-app update card pins (OFFICIAL_ASSETS)
 *   card         a rolling "mac" release as the pipeline (or ship-mac.sh --publish) writes it is one the update card
 *                reads: version from the title, Miyagi-Mac.dmg as the installer, its sha256, "What's new" from the notes
 *   today        the rolling release as it is before the first dmg ships (one zip, no version) gives no offer
 *   notes        release-notes.mjs: RELEASE-NOTES.txt filter, title, rolling and full notes, the assemble folder
 *
 * Run from app/: node --import tsx --import ./test/setup.mjs --test --test-force-exit test/*.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, test } from 'node:test'
import { OFFICIAL_ASSETS, OFFICIAL_RELEASE_REPO, readRelease } from '../src/renderer/src/features/updates/manifest'
import {
  ARM64_DMG,
  RELEASES_REPO,
  ROLLING_TAG,
  ROLLING_ZIP,
  X64_DMG,
  assemble,
  dmgSums,
  fullNotes,
  rollingAssets,
  rollingNotes,
  title,
  updateZip,
  whatsNew
} from '../../.github/scripts/release-notes.mjs'

/** A repo file as text, with LF line ends whatever the checkout uses. */
const repoFile = (...parts: string[]): string => readFileSync(join(__dirname, '..', '..', ...parts), 'utf8').replace(/\r\n/g, '\n')

const A = 'a'.repeat(64)
const B = 'b'.repeat(64)
const C = 'c'.repeat(64)
const UNSIGNED_LINE = 'Unsigned build: open it once, then System Settings › Privacy & Security › Open Anyway.'
const url = (name: string, tag = ROLLING_TAG): string => `https://github.com/${RELEASES_REPO}/releases/download/${tag}/${name}`
const asset = (name: string, over: Record<string, unknown> = {}): Record<string, unknown> => ({ name, state: 'uploaded', size: 126_000_000, browser_download_url: url(name), ...over })

/** The rolling release as GitHub's API returns it after a publish. */
function rolling(opts: { version?: string; intel?: boolean; unsigned?: boolean; whatsnew?: string[]; digest?: string } = {}): Record<string, unknown> {
  const { version = '0.2.0', intel = true, unsigned = true, whatsnew = ['Lessons open faster.'], digest } = opts
  return {
    tag_name: ROLLING_TAG,
    name: title(version, unsigned),
    draft: false,
    prerelease: false,
    body: rollingNotes({ version, whatsnew, unsigned, sha256: A }),
    assets: rollingAssets(intel).map((n) => asset(n, n === ARM64_DMG && digest ? { digest } : {}))
  }
}

describe('names: what is published is what the update card pins', () => {
  test('the release repo and the Apple silicon dmg are the ones the card trusts', () => {
    assert.equal(RELEASES_REPO, OFFICIAL_RELEASE_REPO)
    assert.equal(ROLLING_TAG, 'mac')
    assert.equal(ARM64_DMG, 'Miyagi-Mac.dmg')
    assert.equal(X64_DMG, 'Miyagi-Mac-x64.dmg')
    assert.equal(ROLLING_ZIP, 'Miyagi-Mac.zip') // install.sh --app (claude/distribution): MIYAGI_APP_URL ends in this name
    assert.ok(OFFICIAL_ASSETS.mac.includes(ARM64_DMG))
    // Every installer the card may offer is a file the rolling release holds.
    for (const name of OFFICIAL_ASSETS.mac) assert.ok(rollingAssets(true).includes(name), `${name} is pinned by the card but never published`)
    assert.deepEqual(rollingAssets(false), ['Miyagi-Mac.dmg', 'Miyagi-Mac.zip'])
    assert.deepEqual(rollingAssets(true), ['Miyagi-Mac.dmg', 'Miyagi-Mac-x64.dmg', 'Miyagi-Mac.zip'])
  })

  test('release.yml refreshes the rolling release with exactly those names', () => {
    const yml = repoFile('.github', 'workflows', 'release.yml')
    const step = /refresh the rolling "mac" release[\s\S]*?(?=\n {2}publish-r2:)/.exec(yml)?.[0] ?? ''
    assert.match(step, new RegExp(`cp ${updateZip('arm64').replace(/\./g, '\\.')} ${ROLLING_ZIP.replace(/\./g, '\\.')}\\n`))
    const always = /rolling=\(([^)]*)\)/.exec(step)?.[1].split(/\s+/) ?? []
    const whenIntel = /\[ -f (\S+) \] && rolling\+=\(([^)]*)\)/.exec(step)
    assert.deepEqual([...always].sort(), [...rollingAssets(false)].sort())
    assert.deepEqual([whenIntel?.[1], whenIntel?.[2]], [X64_DMG, X64_DMG])
    assert.match(step, /gh release upload mac "\$\{rolling\[@\]\}" --clobber/)
    // The title and notes the card reads come from release-notes.mjs (assemble), not from text in the workflow.
    assert.match(yml, /node \.github\/scripts\/release-notes\.mjs assemble release "\$VERSION"/)
    assert.match(step, /gh release edit mac --title "\$\(cat TITLE\.txt\)" --notes-file ROLLING\.md --latest=false/)
    // Only a published, non-prerelease run may replace what users download.
    assert.match(step, /if: needs\.plan\.outputs\.draft != 'true' && needs\.plan\.outputs\.prerelease != 'true'/)
  })

  test('release-mac.sh names the dmg and the update zip per arch', () => {
    const sh = repoFile('app', 'scripts', 'release-mac.sh')
    assert.match(sh, /if \[ "\$ARCH" = arm64 \]; then DMG_NAME="Miyagi-Mac\.dmg"; else DMG_NAME="Miyagi-Mac-\$ARCH\.dmg"; fi/)
    assert.match(sh, /ZIP="dist\/Miyagi-Mac-\$ARCH\.zip"/)
    assert.match(sh, /"-c\.mac\.artifactName=Miyagi-Mac-\\\$\{arch\}\.\\\$\{ext\}"/)
    assert.equal(updateZip('arm64'), 'Miyagi-Mac-arm64.zip')
    assert.equal(updateZip('x64'), 'Miyagi-Mac-x64.zip')
  })

  test('ship-mac.sh: an Intel build never takes the Apple silicon name, and a publish writes the version', () => {
    const sh = repoFile('app', 'scripts', 'ship-mac.sh')
    assert.match(sh, /if \[ "\$ARCH" = "--x64" \]; then NAME=Miyagi-Mac-x64; else NAME=Miyagi-Mac; fi/)
    assert.match(sh, /DMG="dist\/\$NAME\.dmg"/)
    assert.match(sh, /"-c\.dmg\.artifactName=\$NAME\.\\\$\{ext\}"/)
    const publish = /if \[ "\$PUBLISH" = 1 \]; then[\s\S]*?\nfi\n/.exec(sh)?.[0] ?? ''
    assert.match(publish, /gh release upload mac "\$DMG" --clobber --repo "\$REPO"/)
    assert.match(publish, /release-notes\.mjs "\$\{NOTES\[@\]\}" > dist\/ROLLING\.md/)
    assert.match(publish, /gh release edit mac --title "\$TITLE" --notes-file dist\/ROLLING\.md --repo "\$REPO"/)
    // The Intel branch uploads its dmg and leaves the title, notes and zip (the Apple silicon build's) alone.
    const intel = /if \[ "\$ARCH" = "--x64" \]; then\n([\s\S]*?)\n {2}else\n/.exec(publish)?.[1] ?? 'missing'
    assert.doesNotMatch(intel, /gh release (edit|upload)/)
  })

  test('the engine in a release is the released commit, not a branch (one trunk since Nov 25)', () => {
    // main carries the app and the engine together, and bundle-engine.mjs defaults to HEAD. A branch name here would
    // override that and ship a tag's app with an older engine.
    const yml = repoFile('.github', 'workflows', 'release.yml')
    assert.match(yml, /\n {6}engine_ref:\n[^\n]+\n {8}type: string\n {8}default: HEAD\n/)
    assert.match(yml, /engine_ref="\$\{IN_ENGINE_REF:-HEAD\}"/)
    assert.match(yml, /engine_ref="\$\{VAR_ENGINE_REF:-HEAD\}"/)
    const texts = { 'release.yml': yml, 'release-mac.sh': repoFile('app', 'scripts', 'release-mac.sh'), 'RELEASING.md': repoFile('RELEASING.md') }
    for (const [name, text] of Object.entries(texts)) assert.doesNotMatch(text, /integration\/live/, `${name} still names the old engine branch`)
  })

  test('electron-builder.yml and the docs use the same dmg name', () => {
    assert.match(repoFile('app', 'electron-builder.yml'), /\ndmg:\n {2}artifactName: Miyagi-Mac\.\$\{ext\}\n/)
    const doc = repoFile('RELEASING.md')
    for (const name of [...rollingAssets(true), updateZip('arm64'), updateZip('x64')]) assert.ok(doc.includes(name), `RELEASING.md doesn't mention ${name}`)
  })
})

describe('card: the update card reads the rolling release the pipeline writes', () => {
  test('version from the title, Miyagi-Mac.dmg, its sha256 from the notes, and the notes as "What\'s new"', () => {
    const r = readRelease(rolling({ whatsnew: ['Lessons open faster.', 'The island follows the notch.'] }), 'mac', 'arm64')
    assert.deepEqual(r, {
      version: '0.2.0',
      notes: ['Lessons open faster.', 'The island follows the notch.', UNSIGNED_LINE],
      url: url(ARM64_DMG),
      sha256: A,
      size: 126_000_000,
      file: ARM64_DMG,
      prerelease: false
    })
  })

  test("GitHub's own digest of the dmg wins over the notes line", () => {
    assert.equal(readRelease(rolling({ digest: `sha256:${B}` }), 'mac', 'arm64')?.sha256, B)
  })

  test('a signed release has no unsigned line, and no notes is fine', () => {
    const r = readRelease(rolling({ unsigned: false, whatsnew: [] }), 'mac', 'arm64')
    assert.equal(r?.version, '0.2.0')
    assert.deepEqual(r?.notes, [])
  })

  test('without the Intel dmg (intel off) the offer is the same', () => {
    assert.equal(readRelease(rolling({ intel: false }), 'mac', 'arm64')?.file, ARM64_DMG)
  })

  test('Intel Macs get Miyagi-Mac-x64.dmg as soon as OFFICIAL_ASSETS.mac lists it', (t) => {
    const file = readRelease(rolling(), 'mac', 'x64')?.file
    if (OFFICIAL_ASSETS.mac.includes(X64_DMG)) {
      assert.equal(file, X64_DMG)
    } else {
      // Known gap (RELEASING.md, Open points): the pin has one name, so an Intel Mac is offered the Apple silicon dmg.
      // The rolling release already holds the Intel dmg; adding its name to OFFICIAL_ASSETS.mac is the whole fix.
      assert.equal(file, ARM64_DMG)
      t.diagnostic(`known gap: an Intel Mac is offered ${ARM64_DMG} until OFFICIAL_ASSETS.mac lists ${X64_DMG}`)
    }
  })

  test('the versioned release (vX.Y.Z) reads the same way', () => {
    const tag = 'v0.2.0'
    const json = { tag_name: tag, name: title('0.2.0', false), draft: false, prerelease: false, body: '', assets: [asset(ARM64_DMG, { browser_download_url: url(ARM64_DMG, tag), digest: `sha256:${C}` })] }
    const r = readRelease(json, 'mac', 'arm64')
    assert.deepEqual([r?.version, r?.url, r?.sha256], ['0.2.0', url(ARM64_DMG, tag), C])
  })
})

describe('today: the rolling release before the first dmg ships', () => {
  // adrian-erlikhman/miyagi release "mac" on Nov 24: one zip (the Nov 19 build), a title with no version.
  const live = {
    tag_name: 'mac',
    name: 'Miyagi for Mac',
    draft: false,
    prerelease: false,
    body: 'For Apple silicon Macs.\n\nUnzip, then move Miyagi to Applications.\n\nBuild 0a0af09 (app 1b6ddcb, engine b9bef2c, engine inside), 2026-11-19.\n',
    assets: [asset(ROLLING_ZIP, { size: 132_709_706, digest: `sha256:${C}` })]
  }

  test('a zip is not an installer: no offer', () => {
    assert.equal(readRelease(live, 'mac', 'arm64'), undefined)
  })

  test('a dmg uploaded without the title and notes has no version: still no offer', () => {
    // What `ship:mac --publish` did before it set them: the card found no semver anywhere and stayed silent for good.
    assert.equal(readRelease({ ...live, assets: [...live.assets, asset(ARM64_DMG)] }, 'mac', 'arm64'), undefined)
  })
})

describe('notes: release-notes.mjs', () => {
  test('RELEASE-NOTES.txt: comments and blank lines are skipped, the first 6 lines kept', () => {
    const text = '# What is new\r\n\r\nLessons open faster.\n   \n  # a comment\nTwo\nThree\nFour\nFive\nSix\nSeven\n'
    assert.deepEqual(whatsNew(text), ['Lessons open faster.', 'Two', 'Three', 'Four', 'Five', 'Six'])
    assert.deepEqual(whatsNew(repoFile('app', 'RELEASE-NOTES.txt')), [])
    assert.deepEqual(whatsNew(undefined), [])
  })

  test('the title carries the version, and "(unsigned)" when the build is ad hoc', () => {
    assert.equal(title('0.2.0', false), 'miyagi 0.2.0')
    assert.equal(title('0.2.0', true), 'miyagi 0.2.0 (unsigned)')
    assert.equal(title('1.0.0-beta.2', false), 'miyagi 1.0.0-beta.2')
    assert.throws(() => title('next', false), /isn't X\.Y\.Z/)
    assert.throws(() => title('v0.2.0', false), /isn't X\.Y\.Z/)
  })

  test('rolling notes: Version first, the lines, the dmg hash last', () => {
    assert.equal(rollingNotes({ version: '0.2.0', whatsnew: ['One', 'Two'], unsigned: true, sha256: A }), `Version: 0.2.0\n\n- One\n- Two\n- ${UNSIGNED_LINE}\n\nsha256: ${A}\n`)
    assert.equal(rollingNotes({ version: '0.2.0', sha256: A }), `Version: 0.2.0\n\n\nsha256: ${A}\n`)
    assert.throws(() => rollingNotes({ version: '0.2.0', sha256: 'abc' }), /64 hex/)
    assert.throws(() => rollingNotes({ version: '', sha256: A }), /isn't X\.Y\.Z/)
  })

  test('full notes list the Intel dmg only when it was built', () => {
    const both = fullNotes({ version: '0.2.0', whatsnew: ['One'], unsigned: false, engine: 'integration/live@bef133de', dmgSums: [[A, ARM64_DMG], [B, X64_DMG]] })
    assert.equal(
      both,
      `Version: 0.2.0\n\n## What's new\n\n- One\n\nSigned with a Developer ID and notarized by Apple.\n\n- Apple silicon: \`Miyagi-Mac.dmg\`\n- Intel: \`Miyagi-Mac-x64.dmg\`\n- Engine inside: \`integration/live@bef133de\`\n\nSHA-256 (all files in SHA256SUMS.txt):\n\nsha256: ${A} (Miyagi-Mac.dmg)\nsha256: ${B} (Miyagi-Mac-x64.dmg)\n`
    )
    const arm = fullNotes({ version: '0.2.0', unsigned: true, engine: 'e', dmgSums: [[A, ARM64_DMG]] })
    assert.doesNotMatch(arm, /Intel/)
    assert.match(arm, /\*\*Unsigned build\*\*/)
  })

  test('SHA256SUMS.txt: only the dmg lines, in file order', () => {
    const sums = `${A}  Miyagi-Mac.dmg\n${B}  Miyagi-Mac-x64.dmg\n${C}  Miyagi-Mac-arm64.zip\n${C}  latest-mac.yml\n`
    assert.deepEqual(dmgSums(sums), [[A, ARM64_DMG], [B, X64_DMG]])
    assert.deepEqual(dmgSums(sums.replace(/\n/g, '\r\n')), [[A, ARM64_DMG], [B, X64_DMG]])
  })

  describe('assemble: the folder the workflow fills', () => {
    const build = (arch: string, signed: boolean, version = '0.2.0'): string => JSON.stringify({ version, arch, signed, engine: 'integration/live@bef133de', dmg: arch === 'arm64' ? ARM64_DMG : X64_DMG })
    function folder(files: Record<string, string>): string {
      const dir = mkdtempSync(join(tmpdir(), 'miyagi-release-'))
      for (const [name, text] of Object.entries(files)) writeFileSync(join(dir, name), text)
      return dir
    }
    const read = (dir: string, name: string): string => readFileSync(join(dir, name), 'utf8')

    test('both arches, unsigned, with notes: the four files, and the card reads the result', () => {
      const dir = folder({
        'build-arm64.json': build('arm64', false),
        'build-x64.json': build('x64', false),
        'WHATSNEW.txt': 'Lessons open faster.\nThe island follows the notch.\n',
        'SHA256SUMS.txt': `${A}  Miyagi-Mac.dmg\n${B}  Miyagi-Mac-x64.dmg\n${C}  Miyagi-Mac-arm64.zip\n`
      })
      try {
        assert.deepEqual(assemble(dir, '0.2.0'), { unsigned: true, intel: true })
        assert.equal(read(dir, 'TITLE.txt'), 'miyagi 0.2.0 (unsigned)')
        assert.equal(read(dir, 'UNSIGNED.txt'), 'true')
        assert.equal(read(dir, 'ROLLING.md'), `Version: 0.2.0\n\n- Lessons open faster.\n- The island follows the notch.\n- ${UNSIGNED_LINE}\n\nsha256: ${A}\n`)
        assert.match(read(dir, 'NOTES.md'), /- Intel: `Miyagi-Mac-x64\.dmg`\n- Engine inside: `integration\/live@bef133de`\n/)
        // The whole point: these exact files, published, are a release the card reads.
        const json = { tag_name: 'mac', name: read(dir, 'TITLE.txt'), draft: false, prerelease: false, body: read(dir, 'ROLLING.md'), assets: rollingAssets(true).map((n) => asset(n)) }
        const r = readRelease(json, 'mac', 'arm64')
        assert.deepEqual([r?.version, r?.file, r?.sha256, r?.notes.length], ['0.2.0', ARM64_DMG, A, 3])
      } finally {
        rmSync(dir, { recursive: true, force: true })
      }
    })

    test('Apple silicon only, signed, no notes', () => {
      const dir = folder({ 'build-arm64.json': build('arm64', true), 'WHATSNEW.txt': '', 'SHA256SUMS.txt': `${A}  Miyagi-Mac.dmg\n` })
      try {
        assert.deepEqual(assemble(dir, '0.2.0'), { unsigned: false, intel: false })
        assert.equal(read(dir, 'TITLE.txt'), 'miyagi 0.2.0')
        assert.equal(read(dir, 'ROLLING.md'), `Version: 0.2.0\n\n\nsha256: ${A}\n`)
      } finally {
        rmSync(dir, { recursive: true, force: true })
      }
    })

    test('it stops on a folder that would publish a release the card cannot read', () => {
      const cases: [Record<string, string>, RegExp][] = [
        [{ 'SHA256SUMS.txt': `${A}  Miyagi-Mac.dmg\n` }, /no build-<arch>\.json/],
        [{ 'build-x64.json': build('x64', false), 'SHA256SUMS.txt': `${B}  Miyagi-Mac-x64.dmg\n` }, /no Apple silicon build/],
        [{ 'build-arm64.json': build('arm64', false, '0.1.9'), 'SHA256SUMS.txt': `${A}  Miyagi-Mac.dmg\n` }, /is version 0\.1\.9, the release is 0\.2\.0/],
        [{ 'build-arm64.json': build('arm64', false), 'SHA256SUMS.txt': `${C}  Miyagi-Mac-arm64.zip\n` }, /no line for Miyagi-Mac\.dmg/]
      ]
      for (const [files, why] of cases) {
        const dir = folder(files)
        try {
          assert.throws(() => assemble(dir, '0.2.0'), why)
        } finally {
          rmSync(dir, { recursive: true, force: true })
        }
      }
    })
  })
})
