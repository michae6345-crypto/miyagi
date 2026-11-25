/**
 * The age record on disk: it persists, a block resists a re-entry (and a relaunch), and no birth date is ever written.
 *   cd app && node --import tsx --test src/main/features/agegate/store.test.ts
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, beforeEach, test } from 'node:test'
import { bandRecord, decide } from '../../../renderer/src/features/agegate/age'
import { AGE_FILE, readAge, writeAge } from './store'

const T = { y: 2026, m: 11, d: 21 }
let dir: string
let file: string
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'miyagi-age-'))
  file = join(dir, AGE_FILE)
})
afterEach(() => rmSync(dir, { recursive: true, force: true }))

const onDisk = (): string => readFileSync(file, 'utf8')

test('the band persists across reads (a relaunch reads the same file)', () => {
  writeAge(file, bandRecord('13-17', T), T)
  assert.deepEqual(readAge(file, T), { band: '13-17', confirmed: '2026-11-21' })
  assert.deepEqual(JSON.parse(onDisk()), { band: '13-17', confirmed: '2026-11-21' })
})

test('a block persists and resists a re-entry with another date, a band, or a shorter block', () => {
  const kid = decide({ y: 2015, m: 6, d: 10 }, T)
  assert.equal(kid.kind, 'blocked')
  if (kid.kind !== 'blocked') return
  writeAge(file, kid.record, T)
  // "Quit and relaunch": a fresh read of the same file.
  assert.deepEqual(readAge(file, T), { blockedUntil: '2028-07-01' })
  // Going back and claiming to be an adult, or older, changes nothing.
  assert.deepEqual(writeAge(file, bandRecord('18+', T), T), { blockedUntil: '2028-07-01' })
  assert.deepEqual(writeAge(file, { blockedUntil: '2027-01-01' }, T), { blockedUntil: '2028-07-01' })
  assert.deepEqual(writeAge(file, { band: '13-17', confirmed: '2026-11-21' }, T), { blockedUntil: '2028-07-01' })
  assert.deepEqual(JSON.parse(onDisk()), { blockedUntil: '2028-07-01' })
})

test('a block lapses on its day: then the step asks again', () => {
  writeAge(file, { blockedUntil: '2028-07-01' }, T)
  assert.equal(readAge(file, { y: 2028, m: 7, d: 1 }), undefined)
  assert.deepEqual(writeAge(file, bandRecord('13-17', T), { y: 2028, m: 7, d: 1 }), { band: '13-17', confirmed: '2028-07-01' })
})

test('no birth date is ever written: not the date, not its day, not a stray field', () => {
  const births = [
    { y: 2015, m: 6, d: 10 },
    { y: 2011, m: 3, d: 4 },
    { y: 1990, m: 8, d: 17 },
    { y: 2012, m: 2, d: 29 }
  ]
  for (const b of births) {
    rmSync(file, { force: true })
    const r = decide(b, T)
    const sent = r.kind === 'blocked' ? r.record : bandRecord(r.kind === 'teen' ? '13-17' : '18+', T)
    // A renderer that tried to slip the date in too.
    writeAge(file, { ...sent, birth: `${b.y}-${b.m}-${b.d}`, y: b.y, m: b.m, d: b.d }, T)
    const text = onDisk()
    const keys = Object.keys(JSON.parse(text))
    assert.ok(keys.every((k) => k === 'band' || k === 'confirmed' || k === 'blockedUntil'), text)
    assert.ok(!text.includes(String(b.y)), `birth year in ${text}`)
    assert.ok(!text.includes(`-${String(b.m).padStart(2, '0')}-${String(b.d).padStart(2, '0')}`), `birth day in ${text}`)
    assert.ok(!/birth/.test(text))
  }
  // Nothing else was left in the folder (no temp file with more in it).
  assert.deepEqual(readdirSync(dir), [AGE_FILE])
})

test('a broken or foreign file reads as nothing on record', () => {
  writeFileSync(file, 'not json')
  assert.equal(readAge(file, T), undefined)
  writeFileSync(file, JSON.stringify({ birth: '2011-03-04' }))
  assert.equal(readAge(file, T), undefined)
})
