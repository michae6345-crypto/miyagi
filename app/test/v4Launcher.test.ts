/**
 * launcher lane, v4 (Nov 24): the launcher's Plans rows and its row pictures, offline. launcher/plans.ts picks the plans
 * still going (most recent first, at most MAX_PLANS, never the lesson already being built), says "3 of 8" and "Next ·
 * <lesson>", and trims the sections under them so the idle panel fits a 700 px tall screen; launcher/art.ts gives a
 * cached lesson the Library's picture.
 */
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import type { PlanState } from '../../shared/contracts/events'
import { planById, planStateFromCatalog } from '../src/renderer/src/features/plans/catalog'
import { launcherPlans, limitWithPlans, MAX_PLANS, nextLessonIndex, planLine, planStarted } from '../src/renderer/src/features/launcher/plans'
import { artOfItem } from '../src/renderer/src/features/launcher/art'

function preset(id: string, done: number, updatedAt?: string): PlanState {
  const p = planById(id)
  assert.ok(p, `catalog plan ${id}`)
  return { ...planStateFromCatalog(p, done), ...(updatedAt ? { updatedAt } : {}) }
}

describe('launcher plans', () => {
  test('the next lesson: nextIndex, else the first one not done, -1 once every lesson is done', () => {
    const p = preset('intro-blender', 1)
    assert.equal(nextLessonIndex(p), 1)
    assert.equal(nextLessonIndex({ ...p, nextIndex: undefined }), 1)
    const finished = preset('intro-blender', planById('intro-blender')!.lessons.length)
    assert.equal(nextLessonIndex(finished), -1)
    assert.equal(nextLessonIndex({ ...p, nextIndex: 999 }), -1, 'an index past the lessons is no next lesson')
  })

  test('started: a lesson passed or opened', () => {
    const fresh = preset('intro-python', 0)
    assert.equal(planStarted(fresh), false)
    assert.equal(planStarted(preset('intro-python', 2)), true)
    assert.equal(planStarted({ ...fresh, lessons: fresh.lessons.map((l, i) => (i === 0 ? { ...l, state: 'in_progress' } : l)) }), true)
  })

  test('only plans still going, most recently touched first, at most MAX_PLANS', () => {
    const blender = preset('intro-blender', 1, '2026-11-20T10:00:00Z')
    const nn = preset('neural-networks', 3, '2026-11-24T10:00:00Z')
    const py = preset('intro-python', 0, '2026-11-22T10:00:00Z')
    const done = preset('intro-terminal', planById('intro-terminal')!.lessons.length, '2026-11-24T12:00:00Z')
    const out = launcherPlans([blender, nn, py, done])
    assert.equal(out.length, MAX_PLANS)
    assert.deepEqual(
      out.map((p) => p.id),
      ['neural-networks', 'intro-python']
    )
  })

  test('without dates the engine order stands', () => {
    const a = preset('intro-blender', 1)
    const b = preset('neural-networks', 3)
    assert.deepEqual(
      launcherPlans([a, b]).map((p) => p.id),
      ['intro-blender', 'neural-networks']
    )
  })

  test('a plan whose next lesson is the one being built is left out', () => {
    const nn = preset('neural-networks', 3)
    const next = nn.lessons[3].title
    assert.equal(launcherPlans([nn], next.toUpperCase()).length, 0)
    assert.equal(launcherPlans([nn], 'Something else').length, 1)
  })

  test('the row: "3 of 8", "Next · <lesson>" and the bar value', () => {
    const nn = preset('neural-networks', 3)
    const line = planLine(nn)
    assert.equal(line.count, `3 of ${nn.total}`)
    assert.equal(line.next, nn.lessons[3].title)
    assert.ok(Math.abs(line.value - 3 / nn.total) < 1e-9)
    const empty: PlanState = { ...nn, lessons: [], total: 0, done: 0, nextIndex: null }
    assert.deepEqual(planLine(empty), { count: '0 of 0', next: undefined, value: 0 })
  })

  test('with plans on screen the sections under them show one row fewer, never none', () => {
    assert.equal(limitWithPlans(3, 0), 3)
    assert.equal(limitWithPlans(3, 2), 2)
    assert.equal(limitWithPlans(1, 1), 1)
  })
})

describe('launcher row pictures', () => {
  test("a cached lesson gets the Library's art from its tool and title", () => {
    assert.equal(artOfItem({ tools: ['terminal'], title: 'Set up a Python environment' }), 'terminal')
    assert.equal(artOfItem({ tools: ['jupyter'], title: 'Plot your data with matplotlib' }), 'plot')
    assert.equal(artOfItem({ tools: ['jupyter'], title: 'Clean a CSV with pandas' }), 'table')
    assert.equal(artOfItem({ tools: ['jupyter', 'vscode'], title: 'Code your first neural network' }), 'network')
    assert.equal(artOfItem({ tools: ['excel'], title: 'Budget' }), 'table')
    assert.equal(artOfItem({ tools: ['vscode'], title: 'Anything' }), 'code')
    assert.equal(artOfItem({ tools: [], title: 'No tools' }), 'code')
  })
})
