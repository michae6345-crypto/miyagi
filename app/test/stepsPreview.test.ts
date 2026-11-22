// Lesson detail step preview: the fold after six rows and its label (features/library/stepsPreview.ts).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { PREVIEW_FOLD, foldLabel, previewSteps } from '../src/renderer/src/features/library/stepsPreview'
import { cleanDetail } from '../src/renderer/src/features/library/sanitize'

const steps = (n: number) => Array.from({ length: n }, (_, index) => ({ index, title: `Step ${index + 1}` }))

test('no steps: nothing to show, nothing folded', () => {
  assert.deepEqual(previewSteps([], false), { rows: [], hidden: 0 })
})

test('up to the fold shows whole, with no control', () => {
  const p = previewSteps(steps(PREVIEW_FOLD), false)
  assert.equal(p.rows.length, PREVIEW_FOLD)
  assert.equal(p.hidden, 0)
})

test('past the fold shows six and counts the rest', () => {
  const p = previewSteps(steps(9), false)
  assert.equal(p.rows.length, PREVIEW_FOLD)
  assert.equal(p.hidden, 3)
  assert.equal(p.rows[5].title, 'Step 6')
})

test('expanded shows every row', () => {
  const p = previewSteps(steps(9), true)
  assert.equal(p.rows.length, 9)
  assert.equal(p.hidden, 0)
})

test('does not mutate its input', () => {
  const s = steps(8)
  previewSteps(s, false).rows.pop()
  assert.equal(s.length, 8)
})

test('fold label', () => {
  assert.equal(foldLabel(9, false), 'Show all 9 steps')
  assert.equal(foldLabel(9, true), 'Show fewer')
})

test('cleanDetail keeps title, what and minutes, and tolerates a list without them', () => {
  const item = { id: 'a1', title: 'T', steps: 2, tools: ['vscode'], ready: true }
  const d = cleanDetail({ item, steps: [{ index: 0, title: 'One', what: 'Do the first thing', estMinutes: 3 }, { index: 1, title: 'Two' }] }, 'a1')
  assert.equal(d?.steps[0].what, 'Do the first thing')
  assert.equal(d?.steps[0].estMinutes, 3)
  assert.equal(d?.steps[1].what, undefined)
  assert.deepEqual(cleanDetail({ item }, 'a1')?.steps, [])
})
