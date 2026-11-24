/**
 * Settings v4 page (v4-settings lane): the Apps and Your data placeholders' words, the cache size, the panels the v4
 * page adds, and which list row a folded panel lights.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { APP_GROUPS, APPS, appCaption, askDelete, size, takeDeleteAsk, usedBy } from '../src/renderer/src/features/settings/v4/facts'
import { isPanel, panelOf, PANELS } from '../src/renderer/src/features/settings/panels'

test('size: KB, MB and GB; nothing for a missing or bad number', () => {
  assert.equal(size(212 * 1024 * 1024), '212 MB')
  assert.equal(size(3 * 1024), '3 KB')
  assert.equal(size(10), '1 KB')
  assert.equal(size(1.5 * 1024 ** 3), '1.5 GB')
  assert.equal(size(undefined), undefined)
  assert.equal(size(-1), undefined)
  assert.equal(size(Number.NaN), undefined)
})

test('apps: every row is in a listed group, ids are unique, captions read as sentences', () => {
  assert.equal(new Set(APPS.map((a) => a.id)).size, APPS.length)
  for (const a of APPS) assert.ok(APP_GROUPS.includes(a.group), a.id)
  assert.equal(usedBy(1), 'Used by 1 plan.')
  assert.equal(usedBy(14), 'Used by 14 plans.')
  assert.equal(usedBy(0), '')
  assert.equal(appCaption(APPS[0]), 'Reads your files and the terminal. Used by 14 plans.')
  for (const a of APPS) assert.ok(!/Miyagi/.test(appCaption(a)), 'lowercase miyagi')
})

test('panels: apps and data are panels for the page, not rows of the sheet', () => {
  assert.ok(isPanel('apps') && isPanel('data'))
  assert.equal(panelOf('apps').label, 'Apps')
  assert.equal(panelOf('data').label, 'Your data')
  assert.ok(!PANELS.some((p) => p.id === 'apps' || p.id === 'data'))
})

test('delete ask: opens the confirm once, right after the ask', () => {
  assert.equal(takeDeleteAsk(), false)
  askDelete()
  assert.equal(takeDeleteAsk(), true)
})
