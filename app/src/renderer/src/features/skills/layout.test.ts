/**
 * features/skills/layout.ts: the layered layout. Run from app/:
 *   node --import tsx --test src/renderer/src/features/skills/layout.test.ts src/renderer/src/features/skills/model.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { assignLayers, countCrossings, edgePath, edgeRoute, edgeSamples, findRows, isDummy, layoutGraph, overlaps, packLayer, placeGraph, snapLayer, type Layout } from './layout'
import { buildSkillGraph, plain, type SkillGraph } from './model'
import { labelLines, estimate, mapInput, nodeBox, pathInput, PLACE, reach, SIZES, TRUNK, type TreeInput, type TreeView } from './graphInput'

type Scenario = { segments: Record<string, Array<{ type?: string; payload: unknown }>> }
const scenario = (name: string): Scenario => JSON.parse(readFileSync(new URL(`../../../../../mock/scenarios/${name}.json`, import.meta.url), 'utf8')) as Scenario
const NOW = Date.parse('2026-11-22T12:00:00Z')
const graph = buildSkillGraph(scenario('skills').segments.skills_progress[0].payload, NOW)!
/** The real-engine fallback (today's tracks as chains, a trunk joining them). */
const fallback = buildSkillGraph(scenario('progress').segments.prog_data[0].payload, NOW)!

/**
 * The tree canvas at the Library window's sizes (SkillsView measured on the stage): the canvas between the goal line and
 * the dock, less the zoom controls' 32 px on the right. 1280x800 is the default window.
 */
const WINDOWS: Record<string, { w: number; h: number }> = {
  '1024x700': { w: 788 - 32, h: 382 },
  '1280x800': { w: 1008 - 32, h: 482 },
  '1280x800 (reviewer box)': { w: 1008 - 32, h: 445 },
  '1728x1080': { w: 1456 - 32, h: 762 }
}

function crossingsOf(l: Layout): number {
  const down: Array<Array<{ from: string; to: string }>> = l.layers.map(() => [])
  for (const e of l.edges) if (!e.flat) for (let i = 0; i + 1 < e.chain.length; i++) down[l.items[e.chain[i]].layer].push({ from: e.chain[i], to: e.chain[i + 1] })
  return countCrossings(l.layers, down)
}

const views: Array<[TreeView, (g: SkillGraph) => TreeInput]> = [
  ['path', (g) => pathInput(g)],
  ['map', (g) => mapInput(g)]
]
const lay = (input: TreeInput): Layout => layoutGraph(input.nodes, input.links, input.options)

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

test('rows: a chain alone in its track lies flat; never across tracks, never into a node with two ways in', () => {
  const ids = ['r', 'a', 'b', 'c', 'x', 'y', 'm']
  const links = [
    { from: 'r', to: 'a' },
    { from: 'a', to: 'b' },
    { from: 'b', to: 'c' },
    { from: 'r', to: 'x' },
    { from: 'x', to: 'y' },
    { from: 'y', to: 'm' },
    { from: 'c', to: 'm' }
  ]
  const group = (id: string): number => ('abc'.includes(id) ? 1 : 'xym'.includes(id) ? 2 : 0)
  const rows = findRows(ids, links, group, new Set(['r']), 5, 1)
  assert.deepEqual(rows, [['a', 'b', 'c'], ['x', 'y']])
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

for (const [name, g] of [
  ['mock', graph],
  ['fallback', fallback]
] as const)
  test(`the ${name} Map: one tree, zero crossings, integer grid, gaps kept, trunk and goal centered`, () => {
    const input = mapInput(g)
    const l = lay(input)
    assert.equal(l.crossings, 0)
    assert.equal(crossingsOf(l), 0)
    for (const row of l.layers)
      for (let i = 1; i < row.length; i++) {
        const a = l.items[row[i - 1]]
        const b = l.items[row[i]]
        assert.ok(b.pos - a.pos >= Math.ceil((a.span + b.span) / 2), `${a.id} / ${b.id} too close`)
      }
    for (const it of Object.values(l.items)) assert.equal(it.pos, Math.round(it.pos))
    // One trunk: the only item of layer 0, on the middle of the tree.
    const roots = l.layers[0]
    assert.equal(roots.length, 1)
    const mid = (l.min + l.max) / 2
    assert.ok(Math.abs(l.items[roots[0]].pos - mid) <= 1, `trunk ${l.items[roots[0]].pos} vs middle ${mid}`)
    // The goal: alone in the top layer, on the middle too.
    const top = l.layers[l.layers.length - 1]
    assert.deepEqual(top, [g.goal!.id])
    assert.ok(Math.abs(l.items[g.goal!.id].pos - mid) <= 1, 'goal centered')
  })

test('the mock Map is short: a chain alone in its track lies flat (pandas, git)', () => {
  const l = lay(mapInput(graph))
  assert.ok(l.layers.length <= 7, `${l.layers.length} layers`)
  for (const run of [
    ['dfs', 'csv', 'clean', 'group', 'sales'],
    ['git', 'branch', 'wt', 'pr']
  ]) {
    assert.equal(new Set(run.map((id) => l.items[id].layer)).size, 1, `${run.join('>')} in one layer`)
    const xs = run.map((id) => l.items[id].pos)
    // Side by side, 2 half slots apart, one way or the other.
    for (let i = 1; i < xs.length; i++) assert.equal(Math.abs(xs[i] - xs[i - 1]), 2)
  }
  for (const e of l.edges.filter((x) => x.flat)) assert.equal(l.items[e.from].layer, l.items[e.to].layer)
})

test('the mock Path: only the goal path, the goal alone at the end and centered, zero crossings', () => {
  const input = pathInput(graph)
  assert.equal(input.nodes.length, 12)
  const l = lay(input)
  assert.equal(l.crossings, 0)
  const last = l.layers[l.layers.length - 1]
  assert.deepEqual(last, ['fit'])
  assert.ok(Math.abs(l.items.fit.pos - (l.min + l.max) / 2) <= 1)
  for (const e of l.edges) assert.ok(l.items[e.from].layer < l.items[e.to].layer)
})

test('hidden links: few, and every node keeps a drawn way in', () => {
  for (const g of [graph, fallback])
    for (const [, make] of views) {
      const input = make(g)
      const l = lay(input)
      assert.ok(l.hidden.length <= 2, `hidden ${JSON.stringify(l.hidden)}`)
      const into = new Set(input.links.map((x) => x.to))
      const drawnInto = new Set(l.edges.map((e) => e.to))
      for (const id of into) assert.ok(drawnInto.has(id), `${id} lost its last drawn way in`)
    }
})

test('way points stay between their edge ends (no loop out past either)', () => {
  for (const g of [graph, fallback])
    for (const [view, make] of views) {
      const l = lay(make(g))
      for (const e of l.edges) {
        const a = l.items[e.from].pos
        const z = l.items[e.to].pos
        for (const d of e.chain.slice(1, -1)) {
          assert.ok(isDummy(d))
          const x = l.items[d].pos
          assert.ok(x >= Math.min(a, z) && x <= Math.max(a, z), `${view} ${e.from}>${e.to}: way point at ${x} outside [${a}, ${z}]`)
        }
      }
    }
})

test('two unlinked nodes never share a column in neighbouring layers', () => {
  for (const g of [graph, fallback])
    for (const [view, make] of views) {
      const l = lay(make(g))
      const linked = new Set(l.edges.map((e) => `${e.from}>${e.to}`))
      for (let i = 0; i + 1 < l.layers.length; i++)
        for (const a of l.layers[i])
          for (const z of l.layers[i + 1]) {
            if (l.items[a].dummy || l.items[z].dummy) continue
            if (l.items[a].pos === l.items[z].pos) assert.ok(linked.has(`${a}>${z}`), `${view}: ${a} under ${z} with no edge`)
          }
    }
})

test('nothing overlaps: labels never collide, and no edge runs through a node or a label', () => {
  for (const g of [graph, fallback])
    for (const box of Object.values(WINDOWS))
      for (const [view, make] of views) {
        const input = make(g)
        const l = lay(input)
        const p = placeGraph(l, PLACE[view](box, l, input))
        const ids = input.nodes.filter((n) => n.id !== TRUNK).map((n) => n.id)
        const boxes = ids.map((id) => nodeBox(view, input, id, p))
        assert.deepEqual(overlaps(boxes), [], `${view} at ${box.w}x${box.h}`)
        for (const e of l.edges) {
          const pts = edgeSamples(
            edgeRoute(e, l, p, SIZES[view].orientation, (id) => reach(view, input, id)),
            SIZES[view].orientation
          )
          for (const b of boxes) {
            if (b.id === e.from || b.id === e.to) continue
            const hit = pts.find((q) => q.x > b.x + 1 && q.x < b.x + b.w - 1 && q.y > b.y + 1 && q.y < b.y + b.h - 1)
            assert.equal(hit, undefined, `${view} ${box.w}x${box.h}: ${e.from}>${e.to} runs through ${b.id}`)
          }
        }
      }
})

test('the Path opens readable: scale 0.85 or more at 1280 and 1728 (and the window it was failing at)', () => {
  const input = pathInput(graph)
  const l = lay(input)
  for (const key of ['1280x800', '1280x800 (reviewer box)', '1728x1080']) {
    const p = placeGraph(l, PLACE.path(WINDOWS[key], l, input))
    assert.ok(p.scale >= 0.85, `Path at ${key}: ${p.scale.toFixed(2)}`)
  }
  // The smallest window: nodes stay about 36 px on screen.
  const small = placeGraph(l, PLACE.path(WINDOWS['1024x700'], l, input))
  assert.ok(small.scale * 2 * SIZES.path.nodeR >= 35, `Path at 1024x700: ${small.scale.toFixed(2)}`)
})

test('the Map fills its view: whole, centered, wider than tall in a wide window', () => {
  const input = mapInput(graph)
  const l = lay(input)
  for (const box of Object.values(WINDOWS)) {
    const p = placeGraph(l, PLACE.map(box, l, input))
    const w = p.w * p.scale
    const h = p.h * p.scale
    assert.ok(w <= box.w + 1 && h <= box.h + 1, 'fits')
    // No big dead band: it touches the box on its binding side (within the pad).
    assert.ok(box.w - w <= 2 * 14 + 2 || box.h - h <= 2 * 14 + 2, `fills ${box.w}x${box.h}: ${Math.round(w)}x${Math.round(h)}`)
  }
  // The default window shows it at least half size, the large one near full size.
  assert.ok(placeGraph(l, PLACE.map(WINDOWS['1280x800'], l, input)).scale >= 0.5)
  assert.ok(placeGraph(l, PLACE.map(WINDOWS['1728x1080'], l, input)).scale >= 0.8)
})

test('labels: inline code marks are dropped; names wrap to two lines at most', () => {
  assert.equal(plain('`groupby`'), 'groupby')
  assert.equal(plain('Training with `fit`'), 'Training with fit')
  assert.ok(!fallback.nodes.some((n) => n.label.includes('`')))
  assert.equal(labelLines('Loops', 112, false, estimate, 2), 1)
  assert.equal(labelLines('Group and summarize', 112, false, estimate, 2), 2)
  assert.equal(labelLines('A very long name that would need three lines', 112, false, estimate, 2), 2)
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
