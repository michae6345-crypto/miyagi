/** features/ptt/route.ts, offline: where a final text goes; and the prefs shape of the ptt setting. */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import { DEFAULT_PREFS, sanitizePrefs } from '../src/common/prefs'
import { routeFor } from '../src/renderer/src/features/ptt/route'

describe('routeFor', () => {
  test('a lesson is running: the same ask a typed question makes', () => {
    assert.equal(routeFor('why does the loss go down', true), 'ask')
  })
  test('no lesson: the launcher opens prefilled so the learner confirms', () => {
    assert.equal(routeFor('teach me about numpy', false), 'launcher')
  })
  test('empty or blank is nothing, with or without a lesson', () => {
    for (const lesson of [true, false]) for (const t of ['', '  ', '\n']) assert.equal(routeFor(t, lesson), 'none')
  })
})

describe('the ptt pref', () => {
  test('defaults: on, fn+control', () => {
    assert.deepEqual(DEFAULT_PREFS.ptt, { enabled: true, chord: 'fn+control' })
  })
  test('sanitize keeps valid values and repairs invalid ones', () => {
    assert.deepEqual(sanitizePrefs({ ptt: { enabled: false, chord: 'control+option' } }).ptt, { enabled: false, chord: 'control+option' })
    assert.deepEqual(sanitizePrefs({ ptt: { enabled: 'yes', chord: 'shift+x' } }).ptt, { enabled: true, chord: 'fn+control' })
    assert.equal(sanitizePrefs({ ptt: 'on' }).ptt, undefined)
    assert.equal(sanitizePrefs({}).ptt, undefined)
  })
})
