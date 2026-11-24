/**
 * library lane, v4 (agents/v4-library.md): the plan catalog the Library and Plans pages read (features/plans/catalog.ts).
 * Data only, no DOM: the groups the Plans page draws, the playlist link parser, the hour labels and the offline
 * plan-from-a-goal, and the offline fallbacks in the ui-v4 contract's shapes (PlaylistInfo, PlanProposal, PlanState)
 * the dialogs and the Library use when no engine answers.
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
  planStateFromCatalog,
  planStateFromProposal,
  PLAN_GROUPS,
  PLANS,
  playlistById,
  playlistIdOf,
  playlistInfoFromCatalog,
  PLAYLISTS,
  proposalFromGoal,
  skillForTitle,
  skillLabel,
  START_HERE
} from '../src/renderer/src/features/plans/catalog'

test('a catalog playlist as playlist.get answers it: video ids, a lesson per video, the plan project', () => {
  const list = playlistById('PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv')!
  const info = playlistInfoFromCatalog(list)
  assert.equal(info.url, 'https://www.youtube.com/playlist?list=PLjEaoINr3zgGUwGwXlj9kBe7TrVWNjkyv')
  assert.equal(info.proposing, false)
  assert.equal(info.proposal?.lessons.length, list.videos.length)
  assert.ok(info.proposal?.lessons.every((l, i) => l.videoId === list.videos[i].id && !!l.videoId))
  assert.equal(info.proposal?.project?.title, planById('intro-blender')?.project.title)
  // Skipped videos are left out of the plan it becomes; a video lesson keeps its id (learn_url).
  const pr = { ...info.proposal!, lessons: info.proposal!.lessons.map((l, i) => ({ ...l, skip: i === 1 })) }
  const st = planStateFromProposal('pl-x', pr)
  assert.equal(st.total, list.videos.length - 1)
  assert.equal(st.lessons[1].videoId, list.videos[2].id)
  assert.equal(st.nextIndex, 0)
})

test('a goal as plan.proposal answers it: lessons with from, the tools, a note', () => {
  const pr = proposalFromGoal('I want to 3D print a stand for my phone')!
  assert.equal(pr.source, 'goal')
  assert.ok(pr.lessons.length > 0 && pr.lessons.every((l) => l.from && planById(l.from.planId)?.lessons[l.from.index]?.title === l.title))
  assert.ok((pr.tools ?? []).some((t) => t.id === 'freecad'))
  assert.ok(pr.note)
  assert.equal(proposalFromGoal('zzqx'), null)
})

test('a catalog plan as a PlanState: lesson states follow done, nextIndex is the next lesson', () => {
  const p = planById('intro-blender')!
  const st = planStateFromCatalog(p, 2)
  assert.equal(st.catalogId, p.id)
  assert.deepEqual(st.lessons.slice(0, 4).map((l) => l.state), ['done', 'done', 'next', 'todo'])
  assert.equal(st.nextIndex, 2)
  assert.equal(planStateFromCatalog(p, p.lessons.length).nextIndex, null)
})

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

test('a goal plan offers each app once, only the apps the goal matches (QA R2-06)', () => {
  const labels = (proposalFromGoal('a budget in google sheets')?.tools ?? []).map((t) => t.label)
  assert.equal(new Set(labels).size, labels.length)
  assert.ok(labels.includes('Google Sheets'), labels.join(', '))
  for (const off of ['Docker Desktop', 'VS Code', 'Terminal']) assert.ok(!labels.includes(off), `${off} in ${labels.join(', ')}`)
})

test('a playlist video grows the skill its title names, from any catalog plan; no match gives no skill', () => {
  const blender = planById('intro-blender')
  const label = (t: string): string | undefined => skillForTitle(t, blender)?.label
  assert.equal(label('Blender Basic Materials Tutorial (Donut Part 4)'), 'Materials')
  assert.equal(label('Blender Basic Texturing Tutorial (Donut Part 5)'), 'Image textures')
  assert.equal(label('Blender Basic UV Unwrapping Tutorial (Donut Part 6)'), 'UV unwrapping')
  // "Modelling" is not "Edit mode": whole words only, and no positional guess.
  assert.equal(label('Blender Basic Modelling Tutorial (Donut Part 2)'), undefined)
  // A word many skills share ("model") never picks one of them.
  assert.equal(skillForTitle('Large Language Models explained briefly', planById('neural-networks')), undefined)
})
