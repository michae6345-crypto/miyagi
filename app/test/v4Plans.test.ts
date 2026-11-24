/**
 * library lane, v4 (agents/v4-library.md): the plan catalog the Library and Plans pages read (features/plans/catalog.ts).
 * Data only, no DOM: the groups the Plans page draws, the playlist link parser, the hour labels and the offline
 * plan-from-a-goal that stands in until the ui-v4 contract's plan messages land.
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  aboutHours,
  afterTitles,
  checkedBy,
  FIRST_RUN,
  hoursShort,
  nextPlans,
  planById,
  planForLesson,
  planFromGoal,
  PLAN_GROUPS,
  PLANS,
  playlistById,
  playlistIdOf,
  PLAYLISTS,
  skillLabel,
  START_HERE
} from '../src/renderer/src/features/plans/catalog'

test('the catalog has 40 plans and 50 playlists, every playlist on a real plan', () => {
  assert.equal(PLANS.length, 40)
  assert.equal(PLAYLISTS.length, 50)
  for (const l of PLAYLISTS) assert.ok(planById(l.planId), l.planId)
  for (const id of [...START_HERE, ...FIRST_RUN]) assert.ok(planById(id), id)
})

test('the Plans page groups: 13 languages, 16 apps and tools, 11 going further, every plan once', () => {
  const counts = PLAN_GROUPS.map((g) => PLANS.filter(g.match).length)
  assert.deepEqual(counts, [13, 16, 11])
  for (const p of PLANS) assert.equal(PLAN_GROUPS.filter((g) => g.match(p)).length, 1, p.id)
})

test('a playlist link gives its id; anything else gives nothing', () => {
  assert.equal(playlistIdOf('youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv'), 'PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv')
  assert.equal(playlistIdOf('https://www.youtube.com/watch?v=abc&list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv&index=2'), 'PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv')
  assert.equal(playlistIdOf('https://www.youtube.com/watch?v=abc'), undefined)
  assert.equal(playlistIdOf('hello'), undefined)
  assert.equal(playlistById('PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv')?.channel, 'Blender Guru')
})

test('time labels round to the half hour', () => {
  assert.equal(aboutHours(150), 'about 2.5 hr')
  assert.equal(aboutHours(45), 'about 45 min')
  assert.equal(hoursShort(185), '3 hr')
})

test('plan facts come from the data', () => {
  const blender = planById('intro-blender')!
  assert.match(checkedBy(blender), /add-on/)
  assert.ok(nextPlans(blender).some((p) => p.id === 'blender-materials'))
  assert.equal(afterTitles(planById('intro-typescript')!), 'Intro to JavaScript')
  assert.equal(skillLabel('bl.modifiers'), 'Modifiers')
  assert.equal(planForLesson('Move, rotate and scale')?.id, 'intro-blender')
})

test('a goal builds a plan from the catalog, the picked tool first, ending in a project', () => {
  const g = planFromGoal('I want to 3D print a stand for my phone')
  assert.equal(g.from[0].topic, 'cad')
  assert.ok(g.tools.length >= 2)
  assert.ok(g.lessons.length >= 6 && g.lessons.length <= 8)
  assert.ok(g.project?.title)
  const fusion = planFromGoal('I want to 3D print a stand for my phone', 'fusion')
  assert.equal(fusion.from[0].tool.id, 'fusion')
  assert.deepEqual(planFromGoal('').lessons, [])
})
