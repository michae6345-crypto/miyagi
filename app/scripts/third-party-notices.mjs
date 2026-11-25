#!/usr/bin/env node
/**
 * Writes licenses/THIRD-PARTY-NOTICES.txt: the npm packages the built app carries (bundled into out/ by electron-vite,
 * or copied into app.asar as a production dependency), each with its license text. MIT, ISC and BSD ask for the
 * copyright and permission notice to travel with every copy, so the file ships in Contents/Resources/licenses
 * (electron-builder.yml extraResources) next to the font licenses.
 *
 * Which packages: every bare import in src/ and ../shared (not electron, not vite, not node: builtins, not type-only
 * @types), then their `dependencies`, transitively. test/fontLicenses.test.ts fails when a package found this way is
 * missing from the committed file, so a new import means: run `node scripts/third-party-notices.mjs` and commit.
 *
 *   node scripts/third-party-notices.mjs          write the file
 *   node scripts/third-party-notices.mjs --check  exit 1 if a package is missing from the committed file
 */
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { builtinModules } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const APP = join(dirname(fileURLToPath(import.meta.url)), '..')
export const NOTICES = join(APP, 'licenses', 'THIRD-PARTY-NOTICES.txt')

/** Imports that never reach the user: Electron ships its own licenses (Resources/LICENSE.electron.txt), vite is build-time. */
const NOT_SHIPPED = new Set(['electron', 'vite'])
const SOURCE = /\.(ts|tsx|mts|js|mjs)$/
const SKIP_FILE = /\.(test|check)\.(ts|tsx|mjs)$/
const IMPORT = /(?:^|[\s;])(?:import|export)\s+(?!type\s)(?:[^'"`;]*?\sfrom\s+)?['"]([^'"./][^'"]*)['"]|import\(\s*['"]([^'"./][^'"]*)['"]\s*\)/g

function walk(dir, out = []) {
  if (!existsSync(dir)) return out
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, out)
    else if (SOURCE.test(name) && !SKIP_FILE.test(name)) out.push(p)
  }
  return out
}

/** `react-dom/client` → `react-dom`, `@scope/pkg/x` → `@scope/pkg`. */
export function packageOf(spec) {
  const parts = spec.split('/')
  return spec.startsWith('@') ? parts.slice(0, 2).join('/') : parts[0]
}

const builtins = new Set(builtinModules.flatMap((m) => [m, m.split('/')[0]]))

/** The packages the source imports directly (a sorted list of names). */
export function directImports(app = APP) {
  const found = new Set()
  for (const file of [...walk(join(app, 'src')), ...walk(join(app, '..', 'shared'))]) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(IMPORT)) {
      const spec = m[1] ?? m[2]
      if (!spec || spec.startsWith('node:') || spec.includes('?')) continue
      const name = packageOf(spec)
      if (builtins.has(name) || NOT_SHIPPED.has(name) || name.startsWith('@types/')) continue
      found.add(name)
    }
  }
  return [...found].sort()
}

const LICENSE_FILE = /^(licen[cs]e|copying|notice)(\.(md|txt|markdown))?$/i

/** Every shipped package with its version, license id and license text, roots and their dependencies. */
export function collect(app = APP) {
  const nm = join(app, 'node_modules')
  const seen = new Map()
  const visit = (name) => {
    if (seen.has(name)) return
    const dir = join(nm, name)
    const pj = join(dir, 'package.json')
    if (!existsSync(pj)) throw new Error(`third-party-notices: ${name} is imported but not in node_modules`)
    const j = JSON.parse(readFileSync(pj, 'utf8'))
    const file = readdirSync(dir).find((f) => LICENSE_FILE.test(f))
    const text = file ? readFileSync(join(dir, file), 'utf8').trim() : ''
    seen.set(name, { name, version: j.version, license: typeof j.license === 'string' ? j.license : (j.license?.type ?? 'see package'), text })
    for (const dep of Object.keys(j.dependencies ?? {})) visit(dep)
  }
  for (const name of directImports(app)) visit(name)
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name))
}

const RULE = '-'.repeat(78)

export function render(entries) {
  const head = [
    'miyagi: third-party notices',
    '',
    'miyagi is built with the open-source packages below. Each keeps its own license, reproduced in full.',
    '',
    'Also in this app, with their own license files:',
    '  - Fonts: licenses/fonts/ (Bricolage Grotesque and Google Sans Flex, SIL Open Font License 1.1).',
    '  - Electron: LICENSE.electron.txt, and Chromium: LICENSES.chromium.html (in the Resources folder on a Mac,',
    '    next to miyagi.exe on Windows).',
    '  - The bundled engine (Resources/engine): Python and its packages keep the license files they came with.',
    '',
    `Packages (${entries.length}): ${entries.map((e) => e.name).join(', ')}`,
    ''
  ]
  const body = entries.flatMap((e) => [RULE, `${e.name} ${e.version} (${e.license})`, RULE, '', e.text || `Licensed under ${e.license}.`, ''])
  return [...head, ...body].join('\n')
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]
if (isMain) {
  const entries = collect()
  if (process.argv.includes('--check')) {
    const have = existsSync(NOTICES) ? readFileSync(NOTICES, 'utf8') : ''
    const missing = entries.filter((e) => !have.includes(`${RULE}\n${e.name} `))
    if (missing.length) {
      console.error(`missing from ${NOTICES}: ${missing.map((e) => e.name).join(', ')}. Run node scripts/third-party-notices.mjs`)
      process.exit(1)
    }
    console.log(`ok: ${entries.length} packages listed`)
  } else {
    writeFileSync(NOTICES, render(entries))
    console.log(`wrote ${NOTICES} (${entries.length} packages)`)
  }
}
