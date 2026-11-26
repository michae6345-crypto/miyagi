/**
 * Font and license hygiene (app-font-licenses lane, Nov 24). The app's fonts are bundled, SIL OFL 1.1, and their
 * license texts ship with the app. This fails when:
 *   - any app source loads a font from Google's servers or any other remote URL (privacy: no request leaves the Mac
 *     to draw text; legal: a self-hosted font is one we can show the license for);
 *   - a font file (.woff2 / .woff / .ttf / .otf) under src/ or brand/ has no license .txt beside it;
 *   - an @font-face family in styles.css (a bundled file, not local()) is missing from Settings > About's list;
 *   - electron-builder.yml stops copying a font license or the npm notices into Resources/licenses;
 *   - a package the source imports is missing from licenses/THIRD-PARTY-NOTICES.txt.
 */
import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { basename, dirname, extname, join, relative } from 'node:path'
import { test } from 'node:test'
import { FONT_LICENSES, licenseText, OFL } from '../src/renderer/src/features/settings/licenses'
// @ts-expect-error: a plain .mjs build script without types
import { collect, NOTICES } from '../scripts/third-party-notices.mjs'

const APP = join(__dirname, '..')
const CODE = /\.(css|html|ts|tsx|js|mjs|cjs|svg)$/
const FONT = /\.(woff2?|ttf|otf)$/i

function walk(dir: string, keep: (f: string) => boolean, out: string[] = []): string[] {
  if (!existsSync(dir)) return out
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, keep, out)
    else if (keep(name)) out.push(p)
  }
  return out
}

/** Every way a page could fetch a font from the network: Google Fonts hosts, or a font file / @font-face / stylesheet over http(s). */
function remoteFontLoads(text: string): string[] {
  const hits: string[] = []
  for (const m of text.matchAll(/fonts\.(googleapis|gstatic)\.com/gi)) hits.push(m[0])
  for (const m of text.matchAll(/(?:https?:)?\/\/[^\s'"`)]+\.(?:woff2?|ttf|otf|eot)\b/gi)) hits.push(m[0])
  for (const block of text.match(/@font-face\s*{[^}]*}/gi) ?? []) for (const m of block.matchAll(/url\(\s*['"]?(?:https?:)?\/\/[^)]*\)/gi)) hits.push(m[0])
  for (const m of text.matchAll(/@import\s+(?:url\()?\s*['"]?(?:https?:)?\/\/[^;]*/gi)) hits.push(m[0])
  for (const m of text.matchAll(/new\s+FontFace\([^)]*(?:https?:)?\/\/[^)]*\)/gi)) hits.push(m[0])
  return hits
}

test('the remote-font check can fail: it catches Google Fonts and any remote font URL', () => {
  assert.ok(remoteFontLoads('<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">').length)
  assert.ok(remoteFontLoads('src: url(https://fonts.gstatic.com/s/inter/v1/x.woff2)').length)
  assert.ok(remoteFontLoads('@font-face { font-family: X; src: url("https://cdn.example.com/x") }').length)
  assert.ok(remoteFontLoads('const u = "//cdn.example.com/fonts/x.ttf"').length)
  assert.ok(remoteFontLoads('@import url("https://example.com/fonts.css");').length)
  assert.ok(remoteFontLoads("new FontFace('X', 'url(https://example.com/x)')").length)
  assert.deepEqual(remoteFontLoads('@font-face { font-family: X; src: url("./assets/fonts/x.woff2") format("woff2"); }'), [])
  assert.deepEqual(remoteFontLoads('import f from "../assets/fonts/x.woff2?inline"'), [])
})

test('no app source loads a font from Google or any other remote host', () => {
  const files = [...walk(join(APP, 'src'), (f) => CODE.test(f)), ...walk(join(APP, 'brand'), (f) => CODE.test(f))]
  assert.ok(files.length > 50, 'the scan found the source')
  const bad = files.flatMap((f) => remoteFontLoads(readFileSync(f, 'utf8')).map((h) => `${relative(APP, f)}: ${h}`))
  assert.deepEqual(bad, [], 'fonts are bundled with the app, never fetched')
})

test("the built app's CSP lets fonts load only from the app itself", () => {
  const serve = readFileSync(join(APP, 'src/main/serve.ts'), 'utf8')
  const fontSrc = serve.match(/"font-src ([^"]*)"/)
  assert.ok(fontSrc, 'serve.ts sets font-src')
  assert.equal(fontSrc[1].trim(), "'self' data:")
})

test('every font file under src/ and brand/ has a license .txt beside it', () => {
  const fonts = [...walk(join(APP, 'src'), (f) => FONT.test(f)), ...walk(join(APP, 'brand'), (f) => FONT.test(f))]
  assert.ok(fonts.length >= 3, 'found the bundled fonts')
  const missing = fonts.filter((f) => {
    const txts = readdirSync(dirname(f)).filter((n) => extname(n).toLowerCase() === '.txt')
    return !txts.some((t) => /licen[cs]e/i.test(readFileSync(join(dirname(f), t), 'utf8')))
  })
  assert.deepEqual(missing.map((f) => relative(APP, f)), [], 'add the font license (e.g. OFL.txt) next to the font file')
})

test('every bundled @font-face family is listed in Settings > About > Open-source licenses', () => {
  const css = readFileSync(join(APP, 'src/renderer/src/styles.css'), 'utf8')
  const families = new Set<string>()
  for (const block of css.match(/@font-face\s*{[^}]*}/g) ?? []) {
    if (!/url\(/.test(block)) continue // local() only: a system font, nothing shipped
    const fam = block.match(/font-family:\s*["']?([^"';]+)["']?/)
    if (fam) families.add(fam[1].trim())
  }
  assert.ok(families.size >= 1)
  for (const fam of families) assert.ok(FONT_LICENSES.some((f) => f.name === fam), `${fam} is bundled but not in FONT_LICENSES`)
})

test("each listed font's license file exists, names its copyright, and is the OFL 1.1", () => {
  for (const f of FONT_LICENSES) {
    const text = readFileSync(join(APP, f.source), 'utf8')
    assert.ok(text.includes(f.copyright.replace(/^Copyright /, '')) || text.includes(f.copyright), `${f.name}: copyright line in ${f.source}`)
    assert.ok(/SIL OPEN FONT LICENSE Version 1\.1/.test(text), `${f.name}: OFL 1.1 text`)
    assert.equal(f.license, OFL)
    assert.ok(f.href.startsWith('https://github.com/'), 'github.com is on main/safeOpen.ts ALLOWED_HOSTS')
  }
})

test('electron-builder copies every font license and the npm notices into Resources/licenses', () => {
  const yml = readFileSync(join(APP, 'electron-builder.yml'), 'utf8')
  // Top-level (column 0), so it applies to mac and win alike (electron-builder merges it with their own lists).
  const top = yml.match(/^extraResources:\n((?:[ ]+.*\n)+)/m)
  assert.ok(top, 'a top-level extraResources list')
  const pairs = [...FONT_LICENSES.map((f) => [f.source, f.shipped]), ['licenses/THIRD-PARTY-NOTICES.txt', 'licenses/THIRD-PARTY-NOTICES.txt']]
  for (const [from, to] of pairs) {
    assert.ok(existsSync(join(APP, from)), `${from} exists`)
    assert.match(top[1], new RegExp(`- from: ${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\n\\s+to: ${to.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\n`), `${from} -> ${to}`)
  }
  for (const f of FONT_LICENSES) assert.ok(f.shipped.startsWith('licenses/fonts/') && basename(f.shipped).endsWith('.txt'))
})

test("the view's license text carries both copyrights and the whole OFL", () => {
  const raw = readFileSync(join(APP, FONT_LICENSES[0].source), 'utf8')
  const t = licenseText(raw)
  for (const f of FONT_LICENSES) assert.ok(t.includes(f.copyright), f.name)
  assert.match(t, /SIL OPEN FONT LICENSE Version 1\.1/)
  for (const part of ['PREAMBLE', 'DEFINITIONS', 'PERMISSION & CONDITIONS', 'TERMINATION', 'DISCLAIMER']) assert.ok(t.includes(part), part)
  assert.ok(!/Anybody|Shantell|Syne/.test(t), 'only fonts the app ships')
})

test('THIRD-PARTY-NOTICES.txt lists every npm package the app ships (run node scripts/third-party-notices.mjs)', () => {
  const have = readFileSync(NOTICES, 'utf8')
  const entries = collect() as Array<{ name: string; text: string }>
  for (const name of ['react', 'react-dom', 'motion', 'lucide-react', 'zustand', 'ws']) assert.ok(entries.some((e) => e.name === name), `${name} found by the scan`)
  assert.ok(!entries.some((e) => e.name === 'electron' || e.name === 'vite'))
  const missing = entries.filter((e) => !have.includes(`\n${e.name} `)).map((e) => e.name)
  assert.deepEqual(missing, [])
  for (const e of entries) assert.ok(e.text.length > 100, `${e.name} has its license text`)
})
