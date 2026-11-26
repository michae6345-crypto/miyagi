/**
 * Delete account, the local part: the erase list, and the wipe in a temp home (nothing real is touched).
 *   cd app && node --import tsx --test src/main/features/accountDelete/wipe.test.ts
 */
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { afterEach, beforeEach, test } from 'node:test'
import { allowedRoots, eraseTargets, insideRoots, USER_DATA_FILES, wipe, type Where } from './wipe'

let root: string
let w: Where
beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'miyagi-wipe-'))
  const home = join(root, 'home')
  w = { userData: join(home, 'Library/Application Support/miyagi'), logs: join(home, 'Library/Logs/miyagi'), crashDumps: join(home, 'Library/Application Support/miyagi/Crashpad'), home, packaged: true, env: {}, lessons: false }
})
afterEach(() => rmSync(root, { recursive: true, force: true }))

function touch(p: string): void {
  mkdirSync(dirname(p), { recursive: true })
  writeFileSync(p, 'x')
}

test('the list names every file the code keeps in userData (read from the code, see wipe.ts)', () => {
  const names = eraseTargets(w).map((t) => t.what)
  for (const f of ['keys.bin', 'auth.bin', 'login.json', 'cloud-link.json', 'session.json', 'install.bin', 'onboarding.json', 'age.json', 'prefs.json', 'reminders.json', 'updates.json', 'player-bounds.json']) {
    assert.ok(names.includes(f), f)
    assert.ok(names.includes(`${f}.tmp`), `${f}.tmp`)
  }
  for (const d of ['errors', 'crash-reports', 'telemetry', 'funnel', 'logs', 'crash dumps', 'demo/cache/search', 'demo/cache/lessons', 'demo/cache/transcripts', 'demo/runs', 'engine logs', 'engine state', 'spoken lines']) assert.ok(names.includes(d), d)
  assert.ok(!names.includes('engine.json'), 'engine.json is a machine setting, kept')
})

test('lesson folders only when ticked', () => {
  assert.ok(!eraseTargets(w).some((t) => t.what === 'lesson folders'))
  const ticked = eraseTargets({ ...w, lessons: true }).filter((t) => t.what === 'lesson folders')
  assert.deepEqual(ticked.map((t) => t.path), [join(w.home, 'miyagi', 'lessons')])
})

test('the dev build wipes its own engine state (state-dev), the built app ~/miyagi/state', () => {
  const state = (p: boolean): string | undefined => eraseTargets({ ...w, packaged: p }).find((t) => t.what === 'engine state')?.path
  assert.equal(state(true), join(w.home, 'miyagi', 'state'))
  assert.equal(state(false), join(w.home, 'miyagi', 'state-dev'))
  assert.equal(eraseTargets({ ...w, env: { MIYAGI_STATE_DIR: '~/miyagi/other' } }).find((t) => t.what === 'engine state')?.path, join(w.home, 'miyagi', 'other'))
})

test('the wipe removes everything on the list and keeps the rest', () => {
  for (const f of USER_DATA_FILES) touch(join(w.userData, f))
  touch(join(w.userData, 'auth.bin.tmp'))
  touch(join(w.userData, 'errors', 'errors.json'))
  touch(join(w.userData, 'crash-reports', 'r1.txt'))
  touch(join(w.userData, 'telemetry', 'state.json'))
  touch(join(w.userData, 'funnel', 'state.json'))
  touch(join(w.userData, 'funnel', 'state.json.tmp'))
  touch(join(w.userData, 'engine.json'))
  touch(join(w.logs, 'island.log'))
  touch(join(w.home, 'miyagi/engine/src/demo/cache/search/q.json'))
  touch(join(w.home, 'miyagi/engine/src/demo/cache/lessons/l.json'))
  touch(join(w.home, 'miyagi/engine/src/demo/cache/transcripts/v.json'))
  touch(join(w.home, 'miyagi/engine/src/demo/runs/r.jsonl'))
  touch(join(w.home, 'miyagi/engine/src/server/main.py'))
  touch(join(w.home, 'miyagi/engine/logs/engine.log'))
  touch(join(w.home, 'miyagi/state/current.json'))
  touch(join(w.home, '.cache/sandhacks-tutor/tts/a.mp3'))
  touch(join(w.home, 'miyagi/lessons/my-project/main.py'))

  const r = wipe(eraseTargets(w), allowedRoots(w))
  assert.equal(r.ok, true)
  assert.deepEqual(r.failed, [])
  assert.deepEqual(r.skipped, [])
  assert.deepEqual(readdirSync(w.userData), ['engine.json'])
  assert.deepEqual(readdirSync(w.logs), [])
  assert.ok(existsSync(w.logs), 'the logs folder itself stays (Electron writes there)')
  for (const gone of ['miyagi/engine/src/demo/cache/search', 'miyagi/engine/src/demo/cache/lessons', 'miyagi/engine/src/demo/cache/transcripts', 'miyagi/engine/src/demo/runs', 'miyagi/engine/logs', 'miyagi/state', '.cache/sandhacks-tutor/tts'])
    assert.ok(!existsSync(join(w.home, gone)), gone)
  assert.ok(existsSync(join(w.home, 'miyagi/engine/src/server/main.py')), 'the engine itself stays')
  assert.ok(existsSync(join(w.home, 'miyagi/lessons/my-project/main.py')), 'lesson folders stay unless ticked')

  const ticked = wipe(eraseTargets({ ...w, lessons: true }), allowedRoots(w))
  assert.equal(ticked.ok, true)
  assert.ok(!existsSync(join(w.home, 'miyagi/lessons')))
})

test('an env override outside miyagi’s folders is skipped, never removed', () => {
  const outside = join(root, 'precious')
  touch(join(outside, 'keep.txt'))
  const bad: Where = { ...w, lessons: true, env: { MIYAGI_LESSONS_DIR: outside, MIYAGI_STATE_DIR: '/', COACH_TTS_DIR: w.home, MIYAGI_HOME: '/' } }
  const r = wipe(eraseTargets(bad), allowedRoots(bad))
  assert.ok(existsSync(join(outside, 'keep.txt')))
  assert.ok(r.skipped.includes('lesson folders'))
  assert.ok(r.skipped.includes('engine state'))
  assert.ok(r.skipped.includes('spoken lines'))
})

test('insideRoots: strictly inside, never the root itself, never a way out', () => {
  const roots = [join(root, 'a')]
  assert.ok(insideRoots(join(root, 'a', 'x'), roots))
  assert.ok(!insideRoots(join(root, 'a'), roots))
  assert.ok(!insideRoots(join(root, 'a', '..', 'b'), roots))
  assert.ok(!insideRoots(join(root, 'ab'), roots))
  assert.ok(!insideRoots('relative/path', roots))
})

test('one file that can’t go does not stop the others; the result says so', () => {
  const targets = eraseTargets(w)
  const removed: string[] = []
  const r = wipe(targets, allowedRoots(w), {
    existsSync: () => true,
    readdirSync: () => [],
    rmSync: (p) => {
      if (p.endsWith('auth.bin')) throw new Error('EPERM')
      removed.push(p)
    }
  })
  assert.equal(r.ok, false)
  assert.deepEqual(r.failed, ['auth.bin'])
  assert.ok(removed.some((p) => p.endsWith('keys.bin')))
  assert.ok(removed.some((p) => p.endsWith('install.bin')))
})
