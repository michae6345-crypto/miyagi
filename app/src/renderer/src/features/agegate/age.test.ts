/**
 * The age step's maths and its record (pure).
 *   cd app && node --import tsx --test src/renderer/src/features/agegate/age.test.ts
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ageCleared, ageOn, bandRecord, blockActive, blockUntil, cleanRecord, decide, mergeRecord, validBirth, type Birth } from './age'

const T = { y: 2026, m: 11, d: 21 }

test('exactly 13 today is 13 (teen), the day before is 12 (blocked)', () => {
  assert.equal(ageOn({ y: 2013, m: 11, d: 21 }, T), 13)
  assert.equal(decide({ y: 2013, m: 11, d: 21 }, T).kind, 'teen')
  assert.equal(ageOn({ y: 2013, m: 11, d: 22 }, T), 12)
  assert.equal(decide({ y: 2013, m: 11, d: 22 }, T).kind, 'blocked')
})

test('exactly 18 today is an adult, a day short is a teen', () => {
  assert.equal(decide({ y: 2008, m: 11, d: 21 }, T).kind, 'adult')
  assert.equal(decide({ y: 2008, m: 11, d: 22 }, T).kind, 'teen')
})

test('Feb 29 birthdays: a year older on Mar 1 when the year has no Feb 29, on Feb 29 when it has', () => {
  const leap: Birth = { y: 2012, m: 2, d: 29 }
  // 2025 is not a leap year: 12 on Feb 28, 13 on Mar 1.
  assert.equal(ageOn(leap, { y: 2025, m: 2, d: 28 }), 12)
  assert.equal(ageOn(leap, { y: 2025, m: 3, d: 1 }), 13)
  assert.equal(decide(leap, { y: 2025, m: 2, d: 28 }).kind, 'blocked')
  assert.equal(decide(leap, { y: 2025, m: 3, d: 1 }).kind, 'teen')
  // 2028 is: 16 on Feb 29 itself.
  assert.equal(ageOn(leap, { y: 2028, m: 2, d: 28 }), 15)
  assert.equal(ageOn(leap, { y: 2028, m: 2, d: 29 }), 16)
})

test('Feb 29 only exists in leap years; Feb 30, Apr 31 and month 13 never', () => {
  assert.ok(validBirth({ y: 2012, m: 2, d: 29 }, T))
  assert.ok(validBirth({ y: 2000, m: 2, d: 29 }, T)) // divisible by 400
  assert.ok(!validBirth({ y: 1900, m: 2, d: 29 }, T)) // divisible by 100, not 400
  assert.ok(!validBirth({ y: 2013, m: 2, d: 29 }, T))
  assert.ok(!validBirth({ y: 2010, m: 2, d: 30 }, T))
  assert.ok(!validBirth({ y: 2010, m: 4, d: 31 }, T))
  assert.ok(!validBirth({ y: 2010, m: 13, d: 1 }, T))
  assert.ok(!validBirth({ y: 2010, m: 0, d: 1 }, T))
})

test('future dates are refused: tomorrow, next month, next year; today is allowed', () => {
  assert.ok(!validBirth({ y: 2026, m: 11, d: 22 }, T))
  assert.ok(!validBirth({ y: 2026, m: 12, d: 1 }, T))
  assert.ok(!validBirth({ y: 2027, m: 1, d: 1 }, T))
  assert.ok(validBirth({ y: 2026, m: 11, d: 21 }, T))
  assert.equal(decide({ y: 2026, m: 11, d: 21 }, T).kind, 'blocked') // born today
})

test('nothing half-picked is valid (Continue stays off)', () => {
  assert.ok(!validBirth({ y: 2000, m: 5 }, T))
  assert.ok(!validBirth({ m: 5, d: 1 }, T))
  assert.ok(!validBirth({}, T))
  assert.ok(!validBirth({ y: 2000.5, m: 5, d: 1 }, T))
  assert.ok(!validBirth({ y: T.y - 121, m: 1, d: 1 }, T))
})

test('blockedUntil: the first of the month after the 13th birthday, never the birth date', () => {
  assert.equal(blockUntil({ y: 2015, m: 6, d: 10 }), '2028-07-01')
  assert.equal(blockUntil({ y: 2015, m: 6, d: 1 }), '2028-07-01')
  assert.equal(blockUntil({ y: 2015, m: 12, d: 31 }), '2029-01-01')
  // Feb 29 2016: 13 on Mar 1 2029 (no Feb 29), so blocked until Apr 1.
  assert.equal(blockUntil({ y: 2016, m: 2, d: 29 }), '2029-04-01')
  const r = decide({ y: 2015, m: 6, d: 10 }, T)
  assert.equal(r.kind, 'blocked')
  if (r.kind === 'blocked') {
    assert.deepEqual(Object.keys(r.record), ['blockedUntil'])
    assert.ok(!JSON.stringify(r.record).includes('2015'))
    assert.ok(!JSON.stringify(r.record).includes('-10'))
  }
})

test('a block holds until its day, then lapses', () => {
  const b = { blockedUntil: '2028-07-01' }
  assert.ok(blockActive(b, T))
  assert.ok(blockActive(b, { y: 2028, m: 6, d: 30 }))
  assert.ok(!blockActive(b, { y: 2028, m: 7, d: 1 }))
  assert.ok(!ageCleared(b, T))
})

test('a block in force wins over any re-entry; a lapsed one does not', () => {
  const b = { blockedUntil: '2028-07-01' }
  assert.deepEqual(mergeRecord(b, { band: '18+', confirmed: '2026-11-21' }, T), b)
  assert.deepEqual(mergeRecord(b, { blockedUntil: '2027-01-01' }, T), b)
  assert.deepEqual(mergeRecord(b, { band: '18+', confirmed: '2026-11-21' }, { y: 2028, m: 7, d: 1 }), { band: '18+', confirmed: '2028-07-01' })
  // From a band, a younger answer blocks (going back and picking again).
  assert.deepEqual(mergeRecord(bandRecord('18+', T), { blockedUntil: '2028-07-01' }, T), b)
})

test('only the two shapes are kept; stray fields (a birth date) are dropped', () => {
  assert.deepEqual(cleanRecord({ band: '13-17', confirmed: '2026-11-21', birth: '2011-03-04', y: 2011 }), { band: '13-17', confirmed: '2026-11-21' })
  assert.deepEqual(cleanRecord({ blockedUntil: '2028-07-01', birth: '2015-06-10' }), { blockedUntil: '2028-07-01' })
  assert.equal(cleanRecord({ blockedUntil: '2028-07-10' }), undefined) // not the first of a month: not ours
  assert.equal(cleanRecord({ band: '21+', confirmed: '2026-11-21' }), undefined)
  assert.equal(cleanRecord({ band: '18+', confirmed: '2026-02-30' }), undefined)
  assert.equal(cleanRecord('18+'), undefined)
  assert.equal(mergeRecord(undefined, { birth: '2011-03-04' }, T), undefined)
  // main stamps its own date on a band
  assert.deepEqual(mergeRecord(undefined, { band: '18+', confirmed: '1999-01-01' }, T), { band: '18+', confirmed: '2026-11-21' })
})
