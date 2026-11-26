/**
 * app-ready-copy (Nov 25): the renderer's words promise only what the app does, and the packaged renderer carries no
 * mock data.
 *
 *   copy     no "sync" and no "follow you" in any string the renderer can show: lesson history and skills live on this
 *            Mac, and nothing moves them between computers. Comments and identifiers (syncSteps, async) don't count:
 *            each file goes through esbuild first (comments dropped, JSX text turned into string literals), then only
 *            the string literals are read.
 *   apps     Settings > Apps has no Connect button and no "Not ready yet." (the app can't set up an add-on yet).
 *   cap      the lesson_builds cap line is calm: the lesson still builds here.
 *   skills   the empty Skills page names the skill the learner clicked.
 *   stage    bridge.ts and main.tsx reach the mock engine, the scenarios, the fixture stand-ins and the Stage only
 *            through dev-only dynamic imports (`npm run build` then drops them; `grep "Sam Rivera" out/renderer` is empty).
 */
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { transformSync } from 'esbuild'
import { APPS } from '../src/renderer/src/features/settings/v4/facts'
import { BUILDS_LINE, capLine } from '../src/renderer/src/features/signincard/notice'
import { emptyLines } from '../src/renderer/src/features/skills/copy'

const RENDERER = join(__dirname, '..', 'src', 'renderer', 'src')

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return walk(p)
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith('.d.ts') ? [p] : []
  })
}

/** Every string literal (and template piece) in a TS/TSX source, comments gone, JSX text included. */
export function stringsOf(source: string, tsx = true): string[] {
  const code = transformSync(source, { loader: tsx ? 'tsx' : 'ts', jsx: 'transform', legalComments: 'none' }).code
  const out: string[] = []
  const re = /"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g
  for (const m of code.matchAll(re)) out.push(m[1] ?? m[2] ?? m[3] ?? '')
  return out
}

/** The promises the app can't keep (Nov 25): progress syncing, or following the learner to another computer. */
const PROMISE = /\bsync(s|ed|ing)?\b|\bfollows? you\b/i

/** Strings that are not copy: module paths. */
const notCopy = (s: string): boolean => /^\.{0,2}\//.test(s)

test('renderer copy never says "sync" or "follow you"', () => {
  const files = walk(RENDERER)
  assert.ok(files.length > 200, 'the walk found the renderer')
  const hits: string[] = []
  for (const f of files) {
    const rel = relative(RENDERER, f).split(sep).join('/')
    for (const s of stringsOf(readFileSync(f, 'utf8'), f.endsWith('.tsx'))) if (!notCopy(s) && PROMISE.test(s)) hits.push(`${rel}: ${s.slice(0, 100)}`)
  }
  assert.deepEqual(hits, [], `history and skills stay on this Mac; say that instead:\n${hits.join('\n')}`)
})

test('the copy check can fail (JSX text, a template, a plain string), and ignores comments and names', () => {
  const probe = (src: string): boolean => stringsOf(src).some((s) => PROMISE.test(s))
  assert.equal(probe('const a = <p>Your progress syncs across Macs.</p>'), true)
  assert.equal(probe('const n = 2; const a = `Lessons follow you to ${n} computers`'), true)
  assert.equal(probe("const a = 'Sign in to sync'"), true)
  assert.equal(probe('// keep these in sync\nconst syncSteps = async () => 1\nconst a = "Also follows your Mac’s setting."'), false)
})

test('Settings > Apps: no Connect button and no "Not ready yet."', () => {
  for (const a of APPS) assert.ok(a.how === 'connected' || a.how === 'screen', `${a.id}: ${a.how}`)
  const panels = readFileSync(join(RENDERER, 'features/settings/v4/Panels.tsx'), 'utf8')
  const apps = panels.slice(panels.indexOf('// ---- Apps'), panels.indexOf('// ---- Your data'))
  assert.ok(apps.length > 200, 'found the Apps section')
  assert.doesNotMatch(apps, /tryInvoke|RunButton|apps:connect|label="Connect"|Not ready yet/)
  assert.doesNotMatch(readFileSync(join(RENDERER, 'features/settings/v4/facts.ts'), 'utf8'), /Not ready yet/)
})

test('the lesson_builds cap line is calm: the lesson still builds here', () => {
  for (const reason of ['lesson_builds', 'miyagi_lesson_quota'])
    for (const resetsAt of [undefined, '2026-12-01T00:00:00Z']) assert.equal(capLine({ reason, status: 429, resetsAt }), BUILDS_LINE)
  assert.ok(BUILDS_LINE.split(/\s+/).length <= 12)
  assert.doesNotMatch(BUILDS_LINE, /used|ran out|limit|!|—/i)
})

test('the empty Skills page names the clicked skill', () => {
  assert.equal(emptyLines('Python loops').title, 'Python loops')
  assert.equal(emptyLines('  ').title, 'No skills yet')
  assert.equal(emptyLines().title, 'No skills yet')
  for (const w of ['Python loops', undefined]) assert.ok(emptyLines(w).line.split(/\s+/).length <= 12)
})

test('mocks and the Stage load only through dev-only dynamic imports', () => {
  const bridge = readFileSync(join(RENDERER, 'bridge.ts'), 'utf8')
  const main = readFileSync(join(RENDERER, 'main.tsx'), 'utf8')
  const statics = (src: string): string[] => [...src.matchAll(/^import\s+(?!type\b)[^'"]*['"]([^'"]+)['"]/gm)].map((m) => m[1])
  for (const spec of [...statics(bridge), ...statics(main)]) assert.doesNotMatch(spec, /mock\/|dev\/Stage|dev\/stageMocks/, spec)
  assert.match(bridge, /import\.meta\.env\.DEV\s*\n?\s*\?\s*import\('\.\/dev\/stageMocks'\)/)
  assert.match(main, /import\.meta\.env\.DEV \? lazy\(\(\) => import\('\.\/dev\/Stage'\)/)
  // The stand-ins with fixture people or scenario words load from dev/stageMocks.ts only.
  const fixtures = ['features/auth/web', 'features/account/web', 'features/circle/web']
  for (const f of walk(RENDERER)) {
    const rel = relative(RENDERER, f).split(sep).join('/')
    if (rel === 'dev/stageMocks.ts') continue
    const dir = rel.split('/').slice(0, -1).join('/')
    for (const spec of statics(readFileSync(f, 'utf8'))) {
      const target = spec.startsWith('.') ? join(dir, spec).split(sep).join('/') : spec
      assert.ok(!fixtures.includes(target), `${rel} imports ${spec}: load it from dev/stageMocks.ts`)
    }
  }
})
