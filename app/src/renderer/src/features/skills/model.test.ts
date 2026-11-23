/**
 * The Skills page view model (model.ts). Offline, no React, no window:
 * `node --import tsx --test src/renderer/src/features/skills/model.test.ts` from app/.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { buildSkillGraph, libraryItemSkills, needsLine } from './model'

const scenario = JSON.parse(readFileSync(new URL('../../../../../mock/scenarios/skills.json', import.meta.url), 'utf8')) as {
  segments: Record<string, Array<{ payload: Record<string, unknown> }>>
}
const progress = scenario.segments.skills_progress[0].payload
const library = scenario.segments.skills_library[0].payload as { items: unknown[] }
// Nov 22 2026, evening: Functions and DataFrames (due Nov 21) and Dot product (due Nov 22, 9:00) are due.
const NOW = new Date(2026, 10, 22, 18).getTime()

describe('buildSkillGraph: progress.graph', () => {
  const g = buildSkillGraph(progress, NOW)!

  it('reads the mock learner from the graph', () => {
    assert.equal(g.source, 'graph')
    assert.equal(g.nodes.length, 26)
    assert.deepEqual(
      g.tracks.map((t) => t.label),
      ['python', 'numpy', 'pandas', 'math', 'neural networks', 'git']
    )
    assert.deepEqual(
      g.capstones.map((c) => c.id),
      ['fit', 'sales', 'pr']
    )
    assert.equal(g.byId.fit.kind, 'capstone')
  })

  it('counts the goal as the mockups do: 6 of 11 mastered, 2 practicing', () => {
    assert.equal(g.goal?.id, 'fit')
    assert.equal(g.goal?.inferred, false)
    assert.equal(g.goal?.total, 11)
    assert.equal(g.goal?.mastered, 6)
    assert.equal(g.goal?.practicing, 2)
    assert.ok(g.byId.layers.onGoalPath && !g.byId.vect.onGoalPath)
  })

  it('keeps review a modifier on mastered, and says what a locked skill needs', () => {
    assert.equal(g.byId.dot.state, 'mastered')
    assert.equal(g.byId.dot.review, true)
    assert.equal(g.byId.arrays.review, false)
    assert.equal(needsLine(g.byId.layers, g), 'needs 3 skills')
    assert.equal(needsLine(g.byId.grad, g), 'needs A single neuron')
  })

  it('uses the engine’s next, also ready and keep fresh', () => {
    assert.equal(g.next?.skillId, 'broad')
    assert.equal(g.next?.lessonTitle, 'NumPy in 20 minutes')
    assert.equal(g.next?.stepIndex, 2)
    assert.equal(g.byId.broad.isNext, true)
    assert.deepEqual(g.alsoReady, ['neuron', 'mat', 'clean'])
    assert.deepEqual(g.keepFresh, ['func', 'dfs'])
  })

  it('plays only events newer than the ack, oldest first', () => {
    assert.deepEqual(
      g.events.map((e) => e.id),
      ['ev_csv', 'ev_clean']
    )
    assert.equal(g.ack, '2026-11-18T16:20:01Z')
    const acked = buildSkillGraph({ ...progress, graph: { ...(progress.graph as object), ackedUntil: g.ack } }, NOW)!
    assert.equal(acked.events.length, 0)
    assert.equal(acked.ack, undefined)
  })

  it('leaves the goal empty when the learner has not picked one', () => {
    const none = buildSkillGraph({ ...progress, graph: { ...(progress.graph as object), goal: null } }, NOW)!
    assert.equal(none.goal, null)
  })

  it('resolves a library item’s skill chips', () => {
    const chips = libraryItemSkills(library.items[0], g)
    assert.deepEqual(
      chips.teaches.map((n) => n.label),
      ['Arrays', 'Indexing', 'Broadcasting']
    )
    assert.deepEqual(
      chips.unlocks.map((n) => n.id),
      ['vect']
    )
  })
})

describe('buildSkillGraph: today’s tracks (fallback)', () => {
  const { graph: _graph, ...old } = progress
  const g = buildSkillGraph(old, NOW)!

  it('turns tracks, their edges and cross links into one graph', () => {
    assert.equal(g.source, 'tracks')
    assert.equal(g.nodes.length, 23) // 26 less the 3 capstones, which today's tracks never carry
    assert.ok(g.links.some((l) => l.from === 'index' && l.to === 'broad' && l.kind === 'requires'))
    assert.ok(g.links.some((l) => l.from === 'dot' && l.to === 'neuron' && l.kind === 'helps'))
  })

  it('derives ready and locked from the prerequisites', () => {
    assert.equal(g.byId.broad.state, 'practicing')
    assert.equal(g.byId.vect.state, 'locked')
    assert.equal(g.byId.clean.state, 'ready')
    assert.equal(g.byId.wt.state, 'ready')
  })

  it('infers the goal: the furthest-along track’s last skill, drawn as the capstone', () => {
    // git: 2 of 3 mastered is the furthest along of the unfinished tracks.
    assert.equal(g.goal?.id, 'wt')
    assert.equal(g.goal?.inferred, true)
    assert.equal(g.byId.wt.kind, 'capstone')
    assert.equal(g.capstones[0]?.id, 'wt')
  })

  it('derives next, also ready and keep fresh', () => {
    assert.ok(g.next)
    assert.ok(g.alsoReady.length <= 3 && !g.alsoReady.includes(g.next!.skillId))
    assert.deepEqual(g.keepFresh, ['func', 'dfs', 'dot'])
    assert.equal(g.events.length, 0)
  })

  it('draws a track with no edges as a short chain', () => {
    const chain = buildSkillGraph({ skills: [{ track: 'Blender', items: [{ label: 'Move', state: 'mastered' }, { label: 'Extrude', state: 'not_started' }, { label: 'Bevel', state: 'not_started' }] }] }, NOW)!
    assert.deepEqual(
      chain.links.map((l) => [l.from, l.to, l.inferred]),
      [
        ['move', 'extrude', true],
        ['extrude', 'bevel', true]
      ]
    )
    assert.equal(chain.byId.extrude.state, 'ready')
    assert.equal(chain.byId.bevel.state, 'locked')
    assert.equal(chain.goal?.id, 'bevel')
    assert.equal(chain.next?.skillId, 'extrude')
  })

  it('handles nothing at all', () => {
    assert.equal(buildSkillGraph(undefined, NOW), undefined)
    const empty = buildSkillGraph({ skills: [], completed: [] }, NOW)!
    assert.equal(empty.nodes.length, 0)
    assert.equal(empty.goal, null)
    assert.equal(empty.next, null)
  })
})
