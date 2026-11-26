// The Mac release's names, title and notes, in one place. Used by .github/workflows/release.yml (assemble) and
// app/scripts/ship-mac.sh (--publish), and read by app/test/releaseNames.test.ts, which checks that what gets published
// is what the in-app update card reads (app/src/renderer/src/features/updates/manifest.ts). Plain Node, no packages.
//
//   node release-notes.mjs assemble <release dir> <version>
//       reads <dir>/build-*.json, WHATSNEW.txt and SHA256SUMS.txt; writes NOTES.md, ROLLING.md, TITLE.txt, UNSIGNED.txt
//   node release-notes.mjs rolling --version 0.2.0 --sha256 <hex> [--unsigned] [--notes app/RELEASE-NOTES.txt]
//       prints the rolling release's notes (ship-mac.sh pipes them to `gh release edit mac --notes-file -`)
//   node release-notes.mjs title --version 0.2.0 [--unsigned]
//
// The names (RELEASING.md, "Who reads which name"):
//   rolling release "mac" on adrian-erlikhman/miyagi, the only place users and the app download from
//     Miyagi-Mac.dmg       Apple silicon. The site's download button and the update card (OFFICIAL_ASSETS.mac).
//     Miyagi-Mac-x64.dmg   Intel, when it was built. For the update card on Intel Macs once OFFICIAL_ASSETS lists it.
//     Miyagi-Mac.zip       the Apple silicon app zipped: install.sh --app, and the site until its link moves to the dmg.
//   versioned release vX.Y.Z: the dmgs, Miyagi-Mac-arm64.zip / -x64.zip (+ .blockmap), latest-mac.yml, SHA256SUMS.txt
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

export const RELEASES_REPO = 'adrian-erlikhman/miyagi'
export const ROLLING_TAG = 'mac'
export const ARM64_DMG = 'Miyagi-Mac.dmg'
export const X64_DMG = 'Miyagi-Mac-x64.dmg'
/** The Apple silicon app zipped, under the name install.sh --app downloads. */
export const ROLLING_ZIP = 'Miyagi-Mac.zip'
export const updateZip = (arch) => `Miyagi-Mac-${arch}.zip`
/** What the rolling release holds after a publish (the Intel dmg only when it was built). */
export const rollingAssets = (intel) => (intel ? [ARM64_DMG, X64_DMG, ROLLING_ZIP] : [ARM64_DMG, ROLLING_ZIP])
export const MAX_WHATSNEW = 6

const HEX64 = /^[0-9a-f]{64}$/
const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/

function need(ok, message) {
  if (!ok) throw new Error(`[release-notes] ${message}`)
}

/** app/RELEASE-NOTES.txt: one plain line per change. Lines starting with "#" and blank lines are skipped; first 6 kept. */
export function whatsNew(text) {
  return String(text ?? '')
    .split(/\r?\n/)
    .filter((l) => !/^\s*(#|$)/.test(l))
    .slice(0, MAX_WHATSNEW)
}

/** The release title. The update card reads the version from it ("miyagi 0.2.0"). */
export function title(version, unsigned) {
  need(SEMVER.test(version), `version "${version}" isn't X.Y.Z`)
  return `miyagi ${version}${unsigned ? ' (unsigned)' : ''}`
}

/**
 * The rolling "mac" release's notes. The update card shows the body's plain lines as "What's new" and drops the
 * Version and sha256 lines (manifest.ts cleanNotes), so only user-facing lines go here. `sha256` is Miyagi-Mac.dmg's:
 * the card reads the first "sha256:" line when the asset carries no digest.
 */
export function rollingNotes({ version, whatsnew = [], unsigned = false, sha256 }) {
  need(SEMVER.test(version), `version "${version}" isn't X.Y.Z`)
  need(sha256 === undefined || HEX64.test(sha256), `sha256 "${sha256}" isn't 64 hex characters`)
  const out = [`Version: ${version}`, '']
  for (const line of whatsnew) out.push(`- ${line}`)
  if (unsigned) out.push('- Unsigned build: open it once, then System Settings › Privacy & Security › Open Anyway.')
  out.push('')
  if (sha256) out.push(`sha256: ${sha256}`)
  return out.join('\n') + '\n'
}

/** The versioned release's notes (vX.Y.Z): what's new, signed or not, the files, the engine, the dmg hashes. */
export function fullNotes({ version, whatsnew = [], unsigned = false, engine, dmgSums }) {
  need(SEMVER.test(version), `version "${version}" isn't X.Y.Z`)
  const out = [`Version: ${version}`, '']
  if (whatsnew.length) out.push("## What's new", '', ...whatsnew.map((l) => `- ${l}`), '')
  if (unsigned) {
    out.push('**Unsigned build** (ad hoc, no Developer ID, not notarized). First open: open miyagi once, press Done,')
    out.push('then System Settings › Privacy & Security › **Open Anyway**. Every new build asks for Screen Recording again.')
  } else {
    out.push('Signed with a Developer ID and notarized by Apple.')
  }
  out.push('', `- Apple silicon: \`${ARM64_DMG}\``)
  if (dmgSums.some(([, name]) => name === X64_DMG)) out.push(`- Intel: \`${X64_DMG}\``)
  out.push(`- Engine inside: \`${engine}\``, '', 'SHA-256 (all files in SHA256SUMS.txt):', '')
  for (const [hex, name] of dmgSums) out.push(`sha256: ${hex} (${name})`)
  return out.join('\n') + '\n'
}

/** SHA256SUMS.txt ("<hex>  <name>" per line) → [[hex, name]] for the dmgs, in file order. */
export function dmgSums(sumsText) {
  const out = []
  for (const line of String(sumsText ?? '').split(/\r?\n/)) {
    const m = /^([0-9a-f]{64}) {2}(Miyagi-Mac.*\.dmg)$/.exec(line)
    if (m) out.push([m[1], m[2]])
  }
  return out
}

/** The release folder the assemble job filled → NOTES.md, ROLLING.md, TITLE.txt, UNSIGNED.txt in it. */
export function assemble(dir, version) {
  const builds = readdirSync(dir)
    .filter((f) => /^build-.*\.json$/.test(f))
    .sort()
    .map((f) => JSON.parse(readFileSync(join(dir, f), 'utf8')))
  need(builds.length > 0, `no build-<arch>.json in ${dir}`)
  for (const b of builds) need(b.version === version, `build-${b.arch}.json is version ${b.version}, the release is ${version}`)
  const arm = builds.find((b) => b.arch === 'arm64')
  need(arm, `no Apple silicon build in ${dir} (the site and the update card download ${ARM64_DMG})`)
  const unsigned = builds.some((b) => !b.signed)
  let whatsnew = []
  try {
    whatsnew = whatsNew(readFileSync(join(dir, 'WHATSNEW.txt'), 'utf8'))
  } catch {
    // no WHATSNEW.txt: no lines
  }
  const sums = dmgSums(readFileSync(join(dir, 'SHA256SUMS.txt'), 'utf8'))
  const armSum = sums.find(([, name]) => name === ARM64_DMG)
  need(armSum, `SHA256SUMS.txt has no line for ${ARM64_DMG}`)
  writeFileSync(join(dir, 'NOTES.md'), fullNotes({ version, whatsnew, unsigned, engine: arm.engine, dmgSums: sums }))
  writeFileSync(join(dir, 'ROLLING.md'), rollingNotes({ version, whatsnew, unsigned, sha256: armSum[0] }))
  writeFileSync(join(dir, 'TITLE.txt'), title(version, unsigned))
  writeFileSync(join(dir, 'UNSIGNED.txt'), String(unsigned))
  return { unsigned, intel: sums.some(([, name]) => name === X64_DMG) }
}

function flags(argv) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    need(a.startsWith('--'), `unknown argument: ${a}`)
    if (a === '--unsigned') out.unsigned = true
    else out[a.slice(2)] = argv[++i]
  }
  return out
}

function main([cmd, ...rest]) {
  if (cmd === 'assemble') {
    need(rest.length === 2, 'usage: release-notes.mjs assemble <release dir> <version>')
    assemble(rest[0], rest[1])
  } else if (cmd === 'rolling') {
    const f = flags(rest)
    need(f.version && f.sha256, 'usage: release-notes.mjs rolling --version X.Y.Z --sha256 <hex> [--unsigned] [--notes <file>]')
    const whatsnew = f.notes ? whatsNew(readFileSync(f.notes, 'utf8')) : []
    process.stdout.write(rollingNotes({ version: f.version, whatsnew, unsigned: !!f.unsigned, sha256: f.sha256 }))
  } else if (cmd === 'title') {
    const f = flags(rest)
    need(f.version, 'usage: release-notes.mjs title --version X.Y.Z [--unsigned]')
    process.stdout.write(title(f.version, !!f.unsigned))
  } else {
    need(false, 'usage: release-notes.mjs assemble | rolling | title (see the header)')
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main(process.argv.slice(2))
  } catch (e) {
    console.error(e instanceof Error ? e.message : e)
    process.exit(1)
  }
}
