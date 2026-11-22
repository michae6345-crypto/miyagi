/**
 * app-harden: every way out to the system browser goes through main/safeOpen.ts. This reads app/src and fails on any
 * shell.openExternal anywhere else, so a new direct call (an unchecked URL from the engine, a page or a renderer)
 * can't slip in unnoticed.
 */
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { test } from 'node:test'

const SRC = join(__dirname, '..', 'src')

/**
 * Files allowed to call shell.openExternal themselves.
 *   main/safeOpen.ts          the one gate
 *   main/features/player.ts   Adrian A14: the YouTube player page's own window-open override (Adrian's claim; it moves
 *                             to safeOpen in that lane). Remove this line when it does.
 */
const ALLOWED = new Set(['main/safeOpen.ts', 'main/features/player.ts'])

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return walk(p)
    return /\.(ts|tsx|js|mjs|cjs)$/.test(name) ? [p] : []
  })
}

/** Code lines only: block-comment and line-comment lines are skipped (docs may name the API). */
function codeLines(text: string): { n: number; line: string }[] {
  return text
    .split('\n')
    .map((line, i) => ({ n: i + 1, line }))
    .filter(({ line }) => !/^\s*(\*|\/\*|\/\/)/.test(line))
}

const files = walk(SRC).map((p) => ({ rel: relative(SRC, p).split(sep).join('/'), text: readFileSync(p, 'utf8') }))

test('no shell.openExternal in app/src outside safeOpen.ts (player.ts allowlisted: Adrian A14)', () => {
  assert.ok(files.length > 50, 'the walk found the source tree')
  const hits: string[] = []
  for (const f of files) {
    if (ALLOWED.has(f.rel)) continue
    for (const { n, line } of codeLines(f.text)) {
      // shell.openExternal(…), shell['openExternal'], or openExternal pulled out of shell / electron.
      if (/\bshell\s*(\.|\?\.)\s*openExternal\b|\bshell\s*\[\s*['"]openExternal['"]\s*\]|\{[^}]*\bopenExternal\b[^}]*\}\s*=\s*(shell|require\(\s*['"]electron['"]\s*\))|\bopenExternal\s*\(/.test(line)) {
        hits.push(`${f.rel}:${n}: ${line.trim()}`)
      }
    }
  }
  assert.deepEqual(hits, [], `call safeOpenExternal / openLinkInBrowser / openSetupDownload from main/safeOpen.ts instead:\n${hits.join('\n')}`)
})

test('the grep would catch a direct call (the check can fail)', () => {
  const probe = codeLines("import { shell } from 'electron'\nvoid shell.openExternal(url)\n// shell.openExternal in a comment is fine")
  assert.equal(probe.filter(({ line }) => /\bshell\s*(\.|\?\.)\s*openExternal\b/.test(line)).length, 1)
})

test('overview.ts opens the Stats page through safeOpen.ts (isEngineStatsUrl, then openEngineStats), never shell', () => {
  const overview = files.find((f) => f.rel === 'main/features/overview.ts')?.text ?? ''
  assert.match(overview, /import \{ isEngineStatsUrl, openEngineStats \} from '\.\.\/safeOpen'/)
  assert.match(overview, /isEngineStatsUrl\(url, port\) \? openEngineStats\(url, port\)/)
  assert.doesNotMatch(overview, /\bshell\b/)
})

test('the general opener (open:external) has no loopback exception: openEngineStats is only for overview.ts', () => {
  const safe = files.find((f) => f.rel === 'main/safeOpen.ts')?.text ?? ''
  const body = safe.slice(safe.indexOf('export async function safeOpenExternal'), safe.indexOf('/** Open one System Settings pane'))
  assert.ok(body.length > 0)
  assert.doesNotMatch(body, /isEngineStatsUrl|openEngineStats/)
  const users = files.filter((f) => f.rel !== 'main/safeOpen.ts' && /\bopenEngineStats\b/.test(f.text)).map((f) => f.rel)
  assert.deepEqual(users, ['main/features/overview.ts'])
})

test('setup Download / Open buttons never window.open an engine URL or send open_in_browser (main’s setup list decides)', () => {
  for (const rel of ['renderer/src/features/cards/index.tsx', 'renderer/src/features/cards/VSCodeSheet.tsx']) {
    const text = files.find((f) => f.rel === rel)?.text ?? ''
    assert.ok(text, rel)
    assert.doesNotMatch(text, /window\.open\(\s*x\.install\.url/, rel)
    assert.doesNotMatch(text, /cardAct\(\s*'open_in_browser'/, rel)
    assert.match(text, /linkRowAct\(x\.tool, x\.install\.url\)/, rel)
  }
  const store = files.find((f) => f.rel === 'renderer/src/features/drawer/store.ts')?.text ?? ''
  assert.match(store, /openSetupLink\(tool, url \?\? ''\)/)
})
