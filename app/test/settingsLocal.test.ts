/**
 * Settings (settings lane): the renderer-side preferences' validation, the search across settings and the progress export.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEFAULT_LOCAL, progressJson, sanitizeLocal, searchSettings, TEXT_SCALE, ROW_HEIGHT } from '../src/renderer/src/features/settings/local'
import { isPanel, PANELS } from '../src/renderer/src/features/settings/panels'

test('sanitizeLocal keeps only known keys with valid values', () => {
  assert.deepEqual(sanitizeLocal({ textSize: 'large', density: 'compact', motion: 'reduce', startPage: 'skills' }), { textSize: 'large', density: 'compact', motion: 'reduce', startPage: 'skills' })
  assert.deepEqual(sanitizeLocal({ textSize: 'huge', density: 3, extra: 1, startPage: 'account' }), {})
  assert.deepEqual(sanitizeLocal(null), {})
  assert.deepEqual(sanitizeLocal('x'), {})
})

test('defaults are scale 1 and comfortable rows', () => {
  assert.equal(TEXT_SCALE[DEFAULT_LOCAL.textSize], 1)
  assert.ok(ROW_HEIGHT.compact < ROW_HEIGHT.comfortable)
})

const items = [
  { id: 'a', panel: 'general', label: 'Start page', caption: 'The page the window opens on.', keywords: 'home' },
  { id: 'b', panel: 'appearance', label: 'Text size', caption: 'Scales everything.', keywords: 'font zoom' },
  { id: 'c', panel: 'notifications', label: 'Sounds', caption: 'A soft tick when a page passes.' }
]

test('searchSettings needs every word, ranks label hits first, ignores case', () => {
  assert.deepEqual(searchSettings(items, 'FONT').map((i) => i.id), ['b'])
  assert.deepEqual(searchSettings(items, 'page').map((i) => i.id), ['a', 'c'])
  assert.deepEqual(searchSettings(items, 'start home').map((i) => i.id), ['a'])
  assert.deepEqual(searchSettings(items, 'nothing here'), [])
  assert.deepEqual(searchSettings(items, '   '), [])
})

test('panels: the five sheet sections are all valid, and ids are unique', () => {
  for (const s of ['general', 'permissions', 'privacy', 'account', 'shortcuts']) assert.ok(isPanel(s))
  assert.ok(!isPanel('nope'))
  assert.equal(new Set(PANELS.map((p) => p.id)).size, PANELS.length)
})

test('progressJson wraps the data with the app name and the time', () => {
  const j = JSON.parse(progressJson({ a: 1 }, new Date('2026-11-22T10:00:00Z')))
  assert.equal(j.app, 'miyagi')
  assert.equal(j.exportedAt, '2026-11-22T10:00:00.000Z')
  assert.deepEqual(j.progress, { a: 1 })
  assert.equal(JSON.parse(progressJson(undefined)).progress, null)
})
