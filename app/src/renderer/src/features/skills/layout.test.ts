/**
 * features/skills/layout.ts: the layered layout. Run from app/:
 *   node --import tsx --test src/renderer/src/features/skills/layout.test.ts src/renderer/src/features/skills/model.test.ts
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { assignLayers, countCrossings, edgePath, edgeRoute, edgeSamples, findRows, isDummy, layoutGraph, overlaps, packLayer, placeGraph, snapLayer, trackOrder, type Layout, type Placed } from './layout'
import { buildSkillGraph, plain, type SkillGraph } from './model'
import { edgePoints, estimate, estimateMapName, estimateMapState, estimateState, geom, HEADER_H, labelLines, MAP_PITCH, mapInput, nodeBox, pathInput, PLACE, reach, SIZES, stateFits, trackHeaders, TRUNK, type TreeInput, type TreeView } from './graphInput'
import { mapLine, stateLine } from './copy'

type Scenario = { segments: Record<string, Array<{ type?: string; payload: unknown }>> }
const scenario = (name: string): Scenario => JSON.parse(readFileSync(new URL(`../../../../../mock/scenarios/${name}.json`, import.meta.url), 'utf8')) as Scenario
const NOW = Date.parse('2026-11-22T12:00:00Z')
const graph = buildSkillGraph(scenario('skills').segments.skills_progress[0].payload, NOW)!
/** The real-engine fallback (today's tracks as chains, a trunk joining them). */
const fallback = buildSkillGraph(scenario('progress').segments.prog_data[0].payload, NOW)!

/**
 * The tree canvas at the Library window's sizes (SkillsView measured on the stage): the canvas between the goal line and
 * the dock, less the zoom controls' 44 px on the right. 1280x800 is the default window.
 */
const WINDOWS: Record<string, { w: number; h: number }> = {
  '1024x700': { w: 788 - 44, h: 382 },
  '1280x800': { w: 1008 - 44, h: 482 },
  '1280x800 (reviewer box)': { w: 1008 - 44, h: 445 },
  '1728x1080': { w: 1456 - 44, h: 762 }
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
  test(`the ${name} Map: one tree, zero crossings, integer grid, gaps kept, trunk under the goal on the canvas center`, () => {
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
    // One trunk: the only item of layer 0. The goal: alone in the top layer, exactly over the trunk.
    const roots = l.layers[0]
    assert.equal(roots.length, 1)
    const top = l.layers[l.layers.length - 1]
    assert.deepEqual(top, [g.goal!.id])
    assert.equal(l.items[roots[0]].pos, l.items[g.goal!.id].pos, 'trunk under the goal')
    // Both on the canvas center, within one grid unit (a half slot), in every window.
    for (const [key, box] of Object.entries(WINDOWS)) {
      const p = placeGraph(l, PLACE.map(box, l, input))
      for (const id of [roots[0], g.goal!.id]) assert.ok(Math.abs(p.at[id].x - p.w / 2) <= p.half, `${id} at ${Math.round(p.at[id].x)} vs center ${Math.round(p.w / 2)} (${key})`)
    }
  })

for (const [name, g] of [
  ['mock', graph],
  ['fallback', fallback]
] as const)
  test(`the ${name} Map is one tree growing up: each skill in its prerequisite depth's layer, each track one branch`, () => {
    const input = mapInput(g)
    const l = lay(input)
    assert.equal(l.edges.filter((e) => e.flat).length, 0, 'no flat rows')
    // Layer = the longest chain of prerequisites below it (the goal pinned on top).
    const preds = new Map<string, string[]>()
    for (const k of input.links) preds.set(k.to, [...(preds.get(k.to) ?? []), k.from])
    const depth = new Map<string, number>()
    const d = (id: string): number => {
      if (!depth.has(id)) depth.set(id, Math.max(-1, ...(preds.get(id) ?? []).map(d)) + 1)
      return depth.get(id)!
    }
    for (const n of input.nodes) if (!n.last) assert.equal(l.items[n.id].layer, d(n.id), `${n.id} in layer ${l.items[n.id].layer}, depth ${d(n.id)}`)
    // A track's skills sit side by side in every layer (no other track between them).
    const groupOf = new Map(input.nodes.map((n) => [n.id, n.group ?? 0]))
    for (const row of l.layers) {
      const gs = row.filter((id) => !isDummy(id)).map((id) => groupOf.get(id))
      for (let i = 0; i < gs.length; i++) for (let j = i + 2; j < gs.length; j++) if (gs[i] === gs[j]) for (let k = i + 1; k < j; k++) assert.equal(gs[k], gs[i], `track ${gs[i]} split in ${row.join(',')}`)
    }
    // The tracks keep one left-to-right order in every layer (branches never swap sides).
    const before = new Set<string>()
    for (const row of l.layers) {
      const gs = [...new Set(row.filter((id) => !isDummy(id) && !input.nodes.find((n) => n.id === id)?.last).map((id) => groupOf.get(id)!))]
      for (let i = 0; i < gs.length; i++) for (let j = i + 1; j < gs.length; j++) before.add(`${gs[i]}<${gs[j]}`)
    }
    for (const k of before) {
      const [a, b] = k.split('<')
      assert.ok(!before.has(`${b}<${a}`), `tracks ${a} and ${b} swap sides`)
    }
  })

test('the mock Map is balanced: no layer much wider than the mean', () => {
  const input = mapInput(graph)
  const l = lay(input)
  const n = input.nodes.filter((x) => x.id !== TRUNK).length
  const bound = Math.ceil(n / l.layers.length) + 2
  for (const row of l.layers) {
    const w = row.filter((id) => !isDummy(id)).length
    assert.ok(w <= bound, `${w} in ${row.join(',')} > ${bound}`)
  }
})

test('trackOrder: the trunk track in the middle, linked tracks side by side, a branch each side', () => {
  // Track 0 is the trunk; 1 and 2 hang off it; 3 hangs off 2 only.
  const ids = ['a0', 'a1', 'b0', 'b1', 'c0', 'c1', 'd0', 'd1']
  const group = (id: string): number => 'abcd'.indexOf(id[0])
  const layer: Record<string, number> = { a0: 0, a1: 1, b0: 2, b1: 3, c0: 2, c1: 3, d0: 4, d1: 5 }
  const links = [
    { from: 'a0', to: 'a1' },
    { from: 'a1', to: 'b0' },
    { from: 'a1', to: 'c0' },
    { from: 'b0', to: 'b1' },
    { from: 'c0', to: 'c1' },
    { from: 'c1', to: 'd0' },
    { from: 'd0', to: 'd1' }
  ]
  const order = trackOrder(ids, links, layer, group, 0)
  const pos = (g: number): number => order.indexOf(g)
  assert.equal(Math.abs(pos(2) - pos(3)), 1, `${order}`)
  assert.ok(pos(0) === 1 || pos(0) === 2, `trunk near the middle: ${order}`)
  assert.ok(Math.sign(pos(1) - pos(0)) !== Math.sign(pos(2) - pos(0)), `one branch each side: ${order}`)
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

test('the whole Map opens fitted: nothing cropped, nodes 30 px or more on screen at 1280x800, the width filled at 1728', () => {
  for (const g of [graph, fallback]) {
    const input = mapInput(g)
    const l = lay(input)
    for (const [key, box] of Object.entries(WINDOWS)) {
      const p = placeGraph(l, PLACE.map(box, l, input))
      // One view: it opens at the scale that shows all of it (no pan on open, Fit changes nothing).
      assert.equal(p.scale, p.whole, `${key}: opens below Fit`)
      assert.ok(p.w * p.scale <= box.w + 1 && p.h * p.scale <= box.h + 1, `${key}: ${Math.round(p.w * p.scale)}x${Math.round(p.h * p.scale)} in ${box.w}x${box.h}`)
      if (g !== graph) continue
      const node = p.scale * 2 * SIZES.map.nodeR
      // The mock's whole tree (11 layers) at the default window and above: nodes stay 30 px and up.
      if (!key.startsWith('1024')) assert.ok(node >= 30, `Map nodes at ${key}: ${node.toFixed(1)} px`)
      else assert.ok(node >= 22, `Map nodes at ${key}: ${node.toFixed(1)} px`)
      // Wide windows are used: the tree spans most of the canvas width.
      if (box.w >= 1200) assert.ok(p.w * p.scale >= box.w * 0.9, `${key}: fills ${Math.round(((p.w * p.scale) / box.w) * 100)}% of the width`)
    }
  }
})

test('the Map is an even grid: every layer gap is the same, in every window', () => {
  for (const g of [graph, fallback])
    for (const [key, box] of Object.entries(WINDOWS)) {
      const input = mapInput(g)
      const l = lay(input)
      const p = placeGraph(l, PLACE.map(box, l, input))
      const ys = l.layers.map((row) => p.at[row[0]].y)
      for (let i = 1; i < ys.length; i++) assert.ok(Math.abs(ys[i - 1] - ys[i] - p.flowGap) < 0.01, `${key}: gap ${i} is ${(ys[i - 1] - ys[i]).toFixed(2)}, not ${p.flowGap.toFixed(2)}`)
      assert.ok(p.flowGap >= MAP_PITCH[0] - 0.01 && p.flowGap <= MAP_PITCH[1] + 0.01)
    }
})

test('no Map edge leaves the canvas: every point of every edge lies inside the content', () => {
  for (const g of [graph, fallback])
    for (const [key, box] of Object.entries(WINDOWS)) {
      const input = mapInput(g)
      const l = lay(input)
      const p = placeGraph(l, PLACE.map(box, l, input))
      for (const c of curves('map', input, l, p)) for (const q of c.pts) assert.ok(q.x >= 0 && q.x <= p.w && q.y >= 0 && q.y <= p.h, `${key}: ${c.key} at ${Math.round(q.x)},${Math.round(q.y)} (${Math.round(p.w)}x${Math.round(p.h)})`)
    }
})

/** Each edge's curve, sampled about every px (content px). */
function curves(view: TreeView, input: TreeInput, l: Layout, p: Placed): Array<{ key: string; from: string; to: string; pts: Array<{ x: number; y: number }> }> {
  const pts = edgePoints(view, input, l, p)
  return l.edges.map((e) => {
    const raw = pts.get(`${e.from}>${e.to}`)!
    let len = 0
    for (let i = 1; i < raw.length; i++) len += Math.hypot(raw[i].x - raw[i - 1].x, raw[i].y - raw[i - 1].y)
    return { key: `${e.from}>${e.to}`, from: e.from, to: e.to, pts: edgeSamples(raw, SIZES[view].orientation, Math.max(8, Math.ceil((len / Math.max(1, raw.length - 1)) * 1.2))) }
  })
}

test('edges never share a line: no two overlap for more than 8 px', () => {
  for (const g of [graph, fallback])
    for (const [view, make] of views)
      for (const [key, box] of Object.entries(WINDOWS)) {
        const input = make(g)
        const l = lay(input)
        const p = placeGraph(l, PLACE[view](box, l, input))
        const cs = curves(view, input, l, p)
        for (let i = 0; i < cs.length; i++)
          for (let j = i + 1; j < cs.length; j++) {
            const a = cs[i]
            const b = cs[j]
            let run = 0
            for (let k = 1; k < a.pts.length; k++) {
              const q = a.pts[k]
              if (b.pts.some((r) => Math.hypot(q.x - r.x, q.y - r.y) < 1.5)) run += Math.hypot(q.x - a.pts[k - 1].x, q.y - a.pts[k - 1].y)
            }
            assert.ok(run <= 8, `${view} ${key}: ${a.key} and ${b.key} share ${run.toFixed(1)} px`)
          }
      }
})

test('no name or state line is cut: every label fits its lines, every state line its width', () => {
  for (const [view, make] of views) {
    const input = make(graph)
    for (const n of input.nodes) {
      if (n.id === TRUNK) continue
      const node = graph.byId[n.id]
      const gm = geom(view, input, n.id)
      if (view === 'map') {
        // One line beside the node, names 12 px and state lines 11 px.
        assert.ok(estimateMapName(node.label, gm.hero) <= gm.labelW, `map: "${node.label}" is cut`)
        const line = mapLine(node, graph, (t) => stateFits(view, input, n.id, t, estimateMapState))
        assert.ok(estimateMapState(line) <= gm.labelW, `map: "${line}" beside ${node.label} is cut`)
        continue
      }
      const need = labelLines(node.label, gm.labelW, gm.hero, estimate, 9)
      assert.ok(need <= SIZES[view].lines, `${view}: "${node.label}" needs ${need} lines`)
      const line = stateLine(node, graph, (t) => stateFits(view, input, n.id, t))
      assert.ok(estimateState(line) <= gm.labelW - 8, `${view}: "${line}" under ${node.label} is cut`)
    }
    // Text sits in content px and the tree scales as one: what fits at one window fits at 1024, 1280 and 1728.
    for (const box of Object.values(WINDOWS)) {
      const l = lay(input)
      assert.ok(placeGraph(l, PLACE[view](box, l, input)).scale > 0)
    }
  }
})

test('the Map heads each track once, above its topmost skill, clear of every node, label, edge, header and the canvas edge', () => {
  for (const g of [graph, fallback])
    for (const [key, box] of Object.entries(WINDOWS)) {
      const input = mapInput(g)
      const l = lay(input)
      const p = placeGraph(l, PLACE.map(box, l, input))
      const cs = curves('map', input, l, p)
      const hs = trackHeaders(
        g.tracks,
        (id) => g.byId[id]?.track,
        input,
        l,
        p,
        [...edgePoints('map', input, l, p).values()]
      )
      const withNodes = g.tracks.filter((t) => g.nodes.some((n) => n.track === t.id && n.id !== g.goal?.id))
      assert.deepEqual(hs.map((h) => h.track).sort(), withNodes.map((t) => t.id).sort(), `${key}: every branch headed`)
      const boxes = input.nodes.filter((n) => n.id !== TRUNK).map((n) => nodeBox('map', input, n.id, p))
      for (const h of hs) {
        assert.ok(h.x >= 0 && h.y >= 0 && h.x + h.w <= p.w && h.y + h.h <= p.h, `${key}: ${h.text} is cut by the canvas`)
        for (const b of boxes) assert.ok(!(h.x < b.x + b.w && b.x < h.x + h.w && h.y < b.y + b.h && b.y < h.y + h.h), `${key}: ${h.text} on ${b.id}`)
        for (const c of cs) assert.equal(c.pts.find((q) => q.x > h.x && q.x < h.x + h.w && q.y > h.y && q.y < h.y + h.h), undefined, `${key}: ${h.text} on ${c.key}`)
        // Over its own branch: within a row of its topmost skill, in the same column neighbourhood.
        const own = input.nodes.filter((n) => n.id !== g.goal?.id && g.byId[n.id]?.track === h.track)
        const top = own.reduce((a, n) => (l.items[n.id].layer > l.items[a.id].layer ? n : a), own[0])
        assert.ok(Math.abs(h.x - p.at[top.id].x) < 12 + 12 * 13 + h.w && h.y + HEADER_H <= p.at[top.id].y, `${key}: ${h.text} is not above its branch`)
      }
      assert.deepEqual(overlaps(hs.map((h) => ({ id: h.track, x: h.x, y: h.y, w: h.w, h: h.h }))), [], `${key}: headers touch`)
    }
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
