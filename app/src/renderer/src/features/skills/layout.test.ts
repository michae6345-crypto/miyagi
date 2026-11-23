/**
 * features/skills/layout.ts: the layered layout. Run from app/:
 *   node --import tsx --test src/renderer/src/features/skills/layout.test.ts src/renderer/src/features/skills/model.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { assignLayers, countCrossings, edgePath, layoutGraph, overlaps, packLayer, placeGraph, snapLayer, type Layout } from './layout'
import { buildSkillGraph } from './model'
import { mapInput, nodeBox, pathInput, PLACE, TRUNK } from './graphInput'

const mock = JSON.parse(readFileSync(new URL('../../../../../mock/scenarios/skills.json', import.meta.url), 'utf8')) as {
  segments: Record<string, Array<{ payload: unknown }>>
}
const NOW = Date.parse('2026-11-22T12:00:00Z')
const graph = buildSkillGraph(mock.segments.skills_progress[0].payload, NOW)!

function crossingsOf(l: Layout): number {
  const down: Array<Array<{ from: string; to: string }>> = l.layers.map(() => [])
  for (const e of l.edges) for (let i = 0; i + 1 < e.chain.length; i++) down[l.items[e.chain[i]].layer].push({ from: e.chain[i], to: e.chain[i + 1] })
  return countCrossings(l.layers, down)
}

test('layers: longest path, prerequisites always below what they open', () => {
  const { layer } = assignLayers(['a', 'b', 'c', 'd'], [
    { from: 'a', to: 'b' },
    { from: 'b', to: 'c' },
    { from: 'a', to: 'c' },
    { from: 'd', to: 'c' }
  ])
  assert.equal(layer.a, 0)
  assert.equal(layer.b, 1)
  assert.equal(layer.c, 2)
  // A root with one way out slides up next to it (no long edge from the bottom).
  assert.equal(layer.d, 1)
})

test('layers: a cycle is broken, never loops', () => {
  const r = assignLayers(['a', 'b', 'c'], [
    { from: 'a', to: 'b' },
    { from: 'b', to: 'c' },
    { from: 'c', to: 'a' }
  ])
  assert.equal(r.dropped.length, 1)
  for (const l of r.kept) assert.ok(r.layer[l.from] < r.layer[l.to])
})

test('layers: a pinned node sits alone in the last layer', () => {
  const { layer } = assignLayers(['a', 'b', 'g', 'c'], [
    { from: 'a', to: 'b' },
    { from: 'b', to: 'c' },
    { from: 'a', to: 'g' }
  ], ['g'])
  assert.equal(layer.g, 3)
})

test('packLayer keeps order and gaps and stays near what each item wants', () => {
  const out = packLayer([0, 0, 0], [1, 1, 1], [2, 2])
  assert.deepEqual(out, [-2, 0, 2])
  const spread = packLayer([-10, 0, 10], [1, 1, 1], [2, 2])
  assert.deepEqual(spread, [-10, 0, 10])
  const snapped = snapLayer([0.4, 1.2, 3.9], [2, 2])
  for (let i = 1; i < snapped.length; i++) assert.ok(snapped[i] - snapped[i - 1] >= 2)
  for (const x of snapped) assert.equal(x, Math.round(x))
})

test('the mock Map: zero crossings, integer grid, gaps kept', () => {
  const { nodes, links } = mapInput(graph)
  const l = layoutGraph(nodes, links)
  assert.equal(l.crossings, 0)
  assert.equal(crossingsOf(l), 0)
  for (const row of l.layers)
    for (let i = 1; i < row.length; i++) {
      const a = l.items[row[i - 1]]
      const b = l.items[row[i]]
      assert.ok(b.pos - a.pos >= Math.ceil((a.span + b.span) / 2), `${a.id} / ${b.id} too close`)
    }
  for (const it of Object.values(l.items)) assert.equal(it.pos, Math.round(it.pos))
  // One trunk: the only root sits in layer 0, roughly centered.
  const roots = l.layers[0].filter((id) => !l.items[id].dummy)
  assert.deepEqual(roots, ['setup'])
  assert.ok(Math.abs(l.items.setup.pos) <= (l.max - l.min) / 3, 'trunk near the middle')
})

test('the mock Path: only the goal path, the goal alone at the end, zero crossings', () => {
  const { nodes, links } = pathInput(graph)
  assert.equal(nodes.length, 12)
  const l = layoutGraph(nodes, links)
  assert.equal(l.crossings, 0)
  const last = l.layers[l.layers.length - 1]
  assert.deepEqual(last, ['fit'])
  for (const e of l.edges) assert.ok(l.items[e.from].layer < l.items[e.to].layer)
})

test('hidden links: few, and every node keeps a drawn way in', () => {
  for (const input of [pathInput(graph), mapInput(graph)]) {
    const l = layoutGraph(input.nodes, input.links)
    assert.ok(l.hidden.length <= 2, `hidden ${JSON.stringify(l.hidden)}`)
    const into = new Set(input.links.map((x) => x.to))
    const drawnInto = new Set(l.edges.map((e) => e.to))
    for (const id of into) assert.ok(drawnInto.has(id), `${id} lost its last drawn way in`)
  }
})

test('placed labels never overlap, in both views and three window sizes', () => {
  for (const [w, h] of [
    [820, 520],
    [1060, 600],
    [1500, 800]
  ]) {
    for (const view of ['path', 'map'] as const) {
      const input = view === 'path' ? pathInput(graph) : mapInput(graph)
      const l = layoutGraph(input.nodes, input.links)
      const opts = PLACE[view]({ w, h }, l, input)
      const p = placeGraph(l, opts)
      const boxes = input.nodes.filter((n) => n.id !== TRUNK).map((n) => nodeBox(view, n.id, n.id === input.hero, p))
      assert.deepEqual(overlaps(boxes), [], `${view} at ${w}x${h}`)
    }
  }
})

test('edgePath: one cubic per gap, handles along the flow', () => {
  const d = edgePath(
    [
      { x: 0, y: 0 },
      { x: 100, y: 40 },
      { x: 200, y: 40 }
    ],
    'right'
  )
  assert.equal(d, 'M0,0 C50,0 50,40 100,40 C150,40 150,40 200,40')
  const v = edgePath(
    [
      { x: 0, y: 100 },
      { x: 20, y: 0 }
    ],
    'up'
  )
  assert.equal(v, 'M0,100 C0,50 20,50 20,0')
})
