/**
 * Feature: skills. The skill tree's layered layout (Sugiyama style), pure: no React, no DOM, no layout library.
 *
 *   1  layers     longest path from the roots (`assignLayers`), then each node slides to the layer that keeps its edges
 *                 shortest (a node with more ways out than in moves up toward what it opens; the goal stays last)
 *   2  dummies    an edge that spans k layers gets k-1 invisible way points, so it routes and orders like a node
 *   3  order      barycenter sweeps down and up, then adjacent swaps (`transpose`), keeping the order with the fewest
 *                 crossings (`countCrossings`); ties keep a track's skills together
 *   4  straighten each node moves toward the mean of its neighbours, then every layer is packed back into order with
 *                 its minimum gaps by isotonic regression (pool adjacent violators), so long edges run straight and a
 *                 parent sits centered over its children; positions end on an integer grid of half slots ("even rows")
 *   5  place      `placeGraph` turns layers and slots into pixels for a box: the gaps stretch between a min and a max to
 *                 fill the view, and only past the min does the whole tree scale down (text stays crisp)
 *   6  edges      `edgePath` draws one curve style everywhere: a cubic per layer gap whose tangents run along the flow
 *
 * Orientation: 'right' (Path: layer 0 on the left, the goal on the right) or 'up' (Map: layer 0 at the bottom, a tree
 * growing up from its trunk). Units: a node takes 2 half slots across the flow, a way point 1.
 */

export type LayoutNode = {
  id: string
  /** Groups (tracks) stay together when the order is otherwise a tie. */
  group?: number
  /** Pinned to the last layer (the goal on the Path). */
  last?: boolean
  /** Across-the-flow size in half slots (2 = a node, 3 = the hero card). */
  span?: number
}
export type LayoutLink = { from: string; to: string }

export type LayoutItem = {
  id: string
  /** A way point of a long edge (drawn as nothing). */
  dummy: boolean
  layer: number
  /** Index inside its layer. */
  order: number
  /** Across the flow, in half slots (integers). */
  pos: number
  span: number
}

export type LayoutEdge = {
  from: string
  to: string
  /** from, the way points, to: one id per layer it passes. */
  chain: string[]
}

export type Layout = {
  items: Record<string, LayoutItem>
  /** Ids per layer, in order (way points included). */
  layers: string[][]
  edges: LayoutEdge[]
  /** Links set aside so the resting tree has no crossings (drawn only for the node in focus). */
  hidden: LayoutLink[]
  crossings: number
  /** Across the flow, in half slots: the smallest and largest pos. */
  min: number
  max: number
}

// ---- 1. layers ----------------------------------------------------------------------------------------------------

/**
 * Layer per node: the longest chain of links into it, then a pass that slides each node toward the side with more
 * links, within its prerequisites and what it opens. Links that close a cycle are dropped (returned in `dropped`).
 */
export function assignLayers(ids: string[], links: LayoutLink[], lastIds: string[] = []): { layer: Record<string, number>; kept: LayoutLink[]; dropped: LayoutLink[] } {
  const known = new Set(ids)
  const seen = new Set<string>()
  const clean = links.filter((l) => known.has(l.from) && known.has(l.to) && l.from !== l.to && !seen.has(`${l.from}>${l.to}`) && seen.add(`${l.from}>${l.to}`))
  // Kahn's order; whatever is left in a cycle is broken at its first link in input order.
  const indeg = new Map(ids.map((id) => [id, 0]))
  for (const l of clean) indeg.set(l.to, (indeg.get(l.to) ?? 0) + 1)
  const order: string[] = []
  const done = new Set<string>()
  const dropped: LayoutLink[] = []
  let kept = clean
  for (;;) {
    const queue = ids.filter((id) => !done.has(id) && indeg.get(id) === 0)
    while (queue.length) {
      const id = queue.shift()!
      done.add(id)
      order.push(id)
      for (const l of kept) {
        if (l.from !== id) continue
        indeg.set(l.to, indeg.get(l.to)! - 1)
        if (indeg.get(l.to) === 0) queue.push(l.to)
      }
    }
    if (done.size === ids.length) break
    // A cycle: drop the first remaining link into the earliest stuck node.
    const stuck = ids.find((id) => !done.has(id))!
    const bad = kept.find((l) => l.to === stuck && !done.has(l.from))!
    dropped.push(bad)
    kept = kept.filter((l) => l !== bad)
    indeg.set(stuck, indeg.get(stuck)! - 1)
  }
  const layer: Record<string, number> = Object.fromEntries(ids.map((id) => [id, 0]))
  const preds = new Map<string, string[]>()
  const succs = new Map<string, string[]>()
  for (const l of kept) {
    preds.set(l.to, [...(preds.get(l.to) ?? []), l.from])
    succs.set(l.from, [...(succs.get(l.from) ?? []), l.to])
  }
  for (const id of order) for (const p of preds.get(id) ?? []) layer[id] = Math.max(layer[id], layer[p] + 1)

  // Pinned last: one layer past everything else.
  const last = new Set(lastIds.filter((id) => known.has(id)))
  const top = (): number => Math.max(0, ...ids.filter((id) => !last.has(id)).map((id) => layer[id]))
  if (last.size) for (const id of last) layer[id] = Math.max(layer[id], top() + 1)

  // Balance: slide toward the heavier side while it shortens the edges (a few passes, from the top down).
  for (let pass = 0; pass < 4; pass++) {
    let moved = false
    for (const id of [...order].reverse()) {
      if (last.has(id)) continue
      const ps = preds.get(id) ?? []
      const ss = succs.get(id) ?? []
      if (!ss.length) continue
      const lo = ps.length ? Math.max(...ps.map((p) => layer[p])) + 1 : 0
      const hi = Math.min(...ss.map((s) => layer[s])) - 1
      if (hi < lo) continue
      // Roots stay where the longest path put them unless they lead into a single later node (a root's long edge).
      const want = ss.length > ps.length ? hi : ss.length < ps.length ? lo : Math.round((lo + hi) / 2)
      const next = ps.length ? want : ss.length === 1 ? hi : layer[id]
      if (next !== layer[id]) {
        layer[id] = next
        moved = true
      }
    }
    if (!moved) break
  }
  return { layer, kept, dropped }
}

// ---- 3. crossings and order ---------------------------------------------------------------------------------------

type Seg = { from: string; to: string }

/** Crossings between two adjacent layers' segments, given each id's index. O(e²), fine for a skill tree. */
export function crossingsBetween(segs: Seg[], index: Map<string, number>): number {
  let n = 0
  for (let i = 0; i < segs.length; i++) {
    const a1 = index.get(segs[i].from)!
    const b1 = index.get(segs[i].to)!
    for (let j = i + 1; j < segs.length; j++) {
      const a2 = index.get(segs[j].from)!
      const b2 = index.get(segs[j].to)!
      if ((a1 - a2) * (b1 - b2) < 0) n++
    }
  }
  return n
}

/** Total crossings of an ordered layering, where `down[i]` are the segments from layer i to layer i + 1. */
export function countCrossings(layers: string[][], down: Seg[][]): number {
  const index = indexOf(layers)
  let n = 0
  for (let i = 0; i + 1 < layers.length; i++) n += crossingsBetween(down[i] ?? [], index)
  return n
}

function indexOf(layers: string[][]): Map<string, number> {
  const m = new Map<string, number>()
  for (const l of layers) l.forEach((id, i) => m.set(id, i))
  return m
}

function sortBy(layer: string[], key: (id: string) => number | undefined, group: (id: string) => number): string[] {
  const at = new Map(layer.map((id, i) => [id, i]))
  return [...layer].sort((a, b) => {
    const ka = key(a) ?? at.get(a)!
    const kb = key(b) ?? at.get(b)!
    return ka - kb || group(a) - group(b) || at.get(a)! - at.get(b)!
  })
}

/**
 * Order every layer to remove crossings: barycenter sweeps (each node to the mean index of its neighbours in the layer
 * just placed), then adjacent swaps that lower the count. The best order seen wins; stops early at zero.
 */
export function orderLayers(input: string[][], down: Seg[][], group: (id: string) => number, rounds = 24): string[][] {
  const preds = new Map<string, string[]>()
  const succs = new Map<string, string[]>()
  for (const segs of down)
    for (const s of segs) {
      preds.set(s.to, [...(preds.get(s.to) ?? []), s.from])
      succs.set(s.from, [...(succs.get(s.from) ?? []), s.to])
    }
  const bary = (ids: string[] | undefined, index: Map<string, number>): number | undefined =>
    ids && ids.length ? ids.reduce((a, id) => a + index.get(id)!, 0) / ids.length : undefined

  // Starts: (a) depth first from the roots, children by group, so each subtree is one contiguous run (a tree drawn this
  // way never crosses); (b) the same with children reversed; (c) each layer by its parents' places. Each start is
  // refined by sweeps and swaps; the order with the fewest crossings wins (ties: the earlier start).
  const dfsStart = (reverse: boolean): string[][] => {
    const rank = new Map<string, number>()
    const visit = (id: string): void => {
      if (rank.has(id)) return
      rank.set(id, rank.size)
      const kids = [...(succs.get(id) ?? [])].sort((a, b) => group(a) - group(b))
      for (const c of reverse ? kids.reverse() : kids) visit(c)
    }
    const roots = input.flat().filter((id) => !preds.get(id)?.length)
    for (const r of sortBy(roots, () => undefined, group)) visit(r)
    return input.map((l) => [...l].sort((a, b) => (rank.get(a) ?? 0) - (rank.get(b) ?? 0)))
  }
  const baryStart = (): string[][] => {
    const layers = input.map((l) => [...l])
    layers[0] = sortBy(layers[0], () => undefined, group)
    for (let i = 1; i < layers.length; i++) {
      const index = indexOf(layers)
      layers[i] = sortBy(layers[i], (id) => bary(preds.get(id), index), group)
    }
    return layers
  }
  let best: string[][] = []
  let bestN = Infinity
  for (const start of [dfsStart(false), dfsStart(true), baryStart()]) {
    const layers = start
    transpose(layers, down)
    let n = countCrossings(layers, down)
    if (n < bestN) {
      bestN = n
      best = layers.map((l) => [...l])
    }
    for (let r = 0; r < rounds && bestN > 0; r++) {
      const downward = r % 2 === 0
      if (downward)
        for (let i = 1; i < layers.length; i++) {
          const index = indexOf(layers)
          layers[i] = sortBy(layers[i], (id) => bary(preds.get(id), index), group)
        }
      else
        for (let i = layers.length - 2; i >= 0; i--) {
          const index = indexOf(layers)
          layers[i] = sortBy(layers[i], (id) => bary(succs.get(id), index), group)
        }
      transpose(layers, down)
      n = countCrossings(layers, down)
      if (n < bestN) {
        bestN = n
        best = layers.map((l) => [...l])
      }
    }
    if (bestN === 0) break
  }
  return best
}

/** Swap neighbours in a layer while it lowers the crossings with both adjacent layers. */
function transpose(layers: string[][], down: Seg[][]): void {
  for (let guard = 0; guard < 20; guard++) {
    let improved = false
    for (let i = 0; i < layers.length; i++) {
      const local = (): number => {
        const index = indexOf(layers)
        return (i > 0 ? crossingsBetween(down[i - 1] ?? [], index) : 0) + crossingsBetween(down[i] ?? [], index)
      }
      for (let j = 0; j + 1 < layers[i].length; j++) {
        const before = local()
        ;[layers[i][j], layers[i][j + 1]] = [layers[i][j + 1], layers[i][j]]
        if (local() < before) improved = true
        else [layers[i][j], layers[i][j + 1]] = [layers[i][j + 1], layers[i][j]]
      }
    }
    if (!improved) break
  }
}

// ---- 4. straighten ------------------------------------------------------------------------------------------------

/**
 * Pack one layer: positions as close to `want` as possible (weighted least squares), in order, each at least `gap[i]`
 * after the one before. Isotonic regression on want - offset (pool adjacent violators), then the offsets back.
 */
export function packLayer(want: number[], weight: number[], gap: number[]): number[] {
  const n = want.length
  const off: number[] = []
  for (let i = 0; i < n; i++) off.push(i ? off[i - 1] + gap[i - 1] : 0)
  const blocks: Array<{ sum: number; w: number; n: number }> = []
  for (let i = 0; i < n; i++) {
    blocks.push({ sum: (want[i] - off[i]) * weight[i], w: weight[i], n: 1 })
    while (blocks.length > 1) {
      const b = blocks[blocks.length - 1]
      const a = blocks[blocks.length - 2]
      if (a.sum / a.w <= b.sum / b.w) break
      blocks.splice(blocks.length - 2, 2, { sum: a.sum + b.sum, w: a.w + b.w, n: a.n + b.n })
    }
  }
  const out: number[] = []
  for (const b of blocks) for (let k = 0; k < b.n; k++) out.push(b.sum / b.w + off[out.length])
  return out
}

/** Integer positions in order with the gaps kept: round, then push right where a gap would shrink, then re-center. */
export function snapLayer(pos: number[], gap: number[]): number[] {
  const out: number[] = []
  for (let i = 0; i < pos.length; i++) {
    const r = Math.round(pos[i])
    out.push(i ? Math.max(r, out[i - 1] + gap[i - 1]) : r)
  }
  // The push only moves right: shift back by the mean drift (rounded), so a packed run stays centered on its wants.
  const drift = Math.round(out.reduce((a, x, i) => a + (x - pos[i]), 0) / Math.max(1, out.length))
  return out.map((x) => x - drift)
}

// ---- the whole layout ---------------------------------------------------------------------------------------------

const DUMMY = '\u0000'
export const isDummy = (id: string): boolean => id.startsWith(DUMMY)

/**
 * Route `drawn` through the layers (way points for long edges) and order them. Fresh arrays each call.
 */
function route(ids: string[], layerOf: Record<string, number>, drawn: LayoutLink[], groupOf: Map<string, number>, span: Map<string, number>) {
  const layer: Record<string, number> = { ...layerOf }
  const nLayers = ids.length ? Math.max(...ids.map((id) => layer[id])) + 1 : 0
  const layers: string[][] = Array.from({ length: nLayers }, () => [])
  for (const id of ids) layers[layer[id]].push(id)
  const edges: LayoutEdge[] = []
  const down: Seg[][] = Array.from({ length: Math.max(0, nLayers - 1) }, () => [])
  /** Which edge each segment belongs to (index into edges). */
  const segEdge = new Map<Seg, number>()
  let k = 0
  for (const l of drawn) {
    const chain = [l.from]
    for (let i = layer[l.from] + 1; i < layer[l.to]; i++) {
      const d = `${DUMMY}${l.from}>${l.to}#${k++}`
      layers[i].push(d)
      groupOf.set(d, groupOf.get(l.from) ?? 0)
      span.set(d, 1)
      layer[d] = i
      chain.push(d)
    }
    chain.push(l.to)
    for (let i = 0; i + 1 < chain.length; i++) {
      const seg = { from: chain[i], to: chain[i + 1] }
      down[layer[chain[i]]].push(seg)
      segEdge.set(seg, edges.length)
    }
    edges.push({ from: l.from, to: l.to, chain })
  }
  const ordered = nLayers ? orderLayers(layers, down, (id) => groupOf.get(id) ?? 0) : []
  // Crossings per edge.
  const index = indexOf(ordered)
  const per = edges.map(() => 0)
  for (const segs of down)
    for (let i = 0; i < segs.length; i++)
      for (let j = i + 1; j < segs.length; j++) {
        const a = segs[i]
        const b = segs[j]
        if ((index.get(a.from)! - index.get(b.from)!) * (index.get(a.to)! - index.get(b.to)!) < 0) {
          per[segEdge.get(a)!]++
          per[segEdge.get(b)!]++
        }
      }
  return { layer, ordered, down, edges, per, crossings: per.reduce((a, n) => a + n, 0) / 2 }
}

/**
 * The layout. Layers come from every link (columns by prerequisite depth). When no order draws every link without a
 * crossing (some prerequisite graphs can't be drawn flat in layers), the fewest links are set aside as `hidden`, one at
 * a time: the one in the most crossings, a link between two groups before one inside a group, and never a node's last
 * drawn way in. The view draws hidden links only for the node in focus, so the resting tree has zero crossings.
 */
export function layoutGraph(nodes: LayoutNode[], links: LayoutLink[]): Layout {
  const ids = nodes.map((n) => n.id)
  const { layer: layerOf, kept } = assignLayers(
    ids,
    links,
    nodes.filter((n) => n.last).map((n) => n.id)
  )
  const groupOf = new Map<string, number>(nodes.map((n) => [n.id, n.group ?? 0]))
  const span = new Map<string, number>(nodes.map((n) => [n.id, n.span ?? 2]))

  // 2 + 3. Way points and order, setting links aside until nothing crosses.
  let drawn = kept
  const hidden: LayoutLink[] = []
  let r = route(ids, layerOf, drawn, groupOf, span)
  for (let guard = 0; r.crossings > 0 && guard < kept.length; guard++) {
    const inDeg = (id: string): number => drawn.filter((l) => l.to === id).length
    const outDeg = (id: string): number => drawn.filter((l) => l.from === id).length
    const score = (i: number): number => {
      const l = drawn[i]
      if (!r.per[i]) return -Infinity
      const keepsWay = inDeg(l.to) > 1 ? 1000 : 0
      const keepsOut = outDeg(l.from) > 1 ? 20 : 0
      const across = (groupOf.get(l.from) ?? 0) !== (groupOf.get(l.to) ?? 0) ? 10 : 0
      return keepsWay + keepsOut + across + 3 * r.per[i] + (layerOf[l.to] - layerOf[l.from])
    }
    let pick = 0
    for (let i = 1; i < drawn.length; i++) if (score(i) > score(pick)) pick = i
    if (score(pick) === -Infinity) break
    hidden.push(drawn[pick])
    drawn = drawn.filter((_, i) => i !== pick)
    r = route(ids, layerOf, drawn, groupOf, span)
  }
  const { ordered, down, edges, crossings } = r

  // 4. Straighten. Neighbours per id, both ways.
  const up = new Map<string, string[]>()
  const dn = new Map<string, string[]>()
  for (const segs of down)
    for (const s of segs) {
      up.set(s.to, [...(up.get(s.to) ?? []), s.from])
      dn.set(s.from, [...(dn.get(s.from) ?? []), s.to])
    }
  const gapAfter = (row: string[]): number[] => row.slice(0, -1).map((id, i) => Math.ceil((span.get(id)! + span.get(row[i + 1])!) / 2))
  const pos = new Map<string, number>()
  for (const row of ordered) {
    const g = gapAfter(row)
    let x = 0
    const xs = row.map((_, i) => (i ? (x += g[i - 1]) : 0))
    const mid = xs.length ? (xs[0] + xs[xs.length - 1]) / 2 : 0
    row.forEach((id, i) => pos.set(id, xs[i] - mid))
  }
  const weight = (id: string): number => (isDummy(id) ? 4 : 1 + (up.get(id)?.length ?? 0) + (dn.get(id)?.length ?? 0))
  const mean = (xs: string[] | undefined): number | undefined => (xs && xs.length ? xs.reduce((a, id) => a + pos.get(id)!, 0) / xs.length : undefined)
  const sweep = (i: number, toward: 'up' | 'dn' | 'both'): void => {
    const row = ordered[i]
    const want = row.map((id) => {
      const a = toward !== 'dn' ? up.get(id) : undefined
      const b = toward !== 'up' ? dn.get(id) : undefined
      const m = mean([...(a ?? []), ...(b ?? [])])
      return m ?? pos.get(id)!
    })
    const placed = packLayer(
      want,
      row.map(weight),
      gapAfter(row)
    )
    row.forEach((id, j) => pos.set(id, placed[j]))
  }
  for (let it = 0; it < 10; it++) {
    for (let i = 1; i < ordered.length; i++) sweep(i, 'up')
    for (let i = ordered.length - 2; i >= 0; i--) sweep(i, 'dn')
  }
  for (let it = 0; it < 6; it++) for (let i = 0; i < ordered.length; i++) sweep(i, 'both')
  // Snap to the half-slot grid, layer by layer, then line single parents up with single children where that's free.
  for (const row of ordered) {
    const snapped = snapLayer(
      row.map((id) => pos.get(id)!),
      gapAfter(row)
    )
    row.forEach((id, j) => pos.set(id, snapped[j]))
  }
  straightenChains(ordered, pos, up, dn, gapAfter)

  // Center the whole thing on 0.
  const all = [...pos.values()]
  const lo = all.length ? Math.min(...all) : 0
  const hi = all.length ? Math.max(...all) : 0
  const shift = Math.round((lo + hi) / 2)
  const items: Record<string, LayoutItem> = {}
  ordered.forEach((row, li) =>
    row.forEach((id, order) => {
      items[id] = { id, dummy: isDummy(id), layer: li, order, pos: pos.get(id)! - shift, span: span.get(id)! }
    })
  )
  const ps = Object.values(items).map((i) => i.pos)
  return { items, layers: ordered, edges, hidden, crossings, min: ps.length ? Math.min(...ps) : 0, max: ps.length ? Math.max(...ps) : 0 }
}

/**
 * After snapping, an edge between two items that are each other's only neighbour on that side and sit within one half
 * slot of each other is made dead straight when the move keeps the layer's order and gaps (no wobble of a half slot).
 */
function straightenChains(
  ordered: string[][],
  pos: Map<string, number>,
  up: Map<string, string[]>,
  dn: Map<string, string[]>,
  gapAfter: (row: string[]) => number[]
): void {
  for (let pass = 0; pass < 3; pass++)
    for (const row of ordered) {
      const g = gapAfter(row)
      row.forEach((id, j) => {
        const ns = [...(up.get(id) ?? []), ...(dn.get(id) ?? [])]
        if (!ns.length) return
        // Target: a neighbour whose only link on this side is this item.
        const only = ns.filter((n) => (up.get(id)?.includes(n) ? (dn.get(n)?.length ?? 0) === 1 : (up.get(n)?.length ?? 0) === 1))
        const target = only.length === ns.length ? Math.round(only.reduce((a, n) => a + pos.get(n)!, 0) / only.length) : undefined
        if (target === undefined || Math.abs(target - pos.get(id)!) > 1) return
        const left = j > 0 ? pos.get(row[j - 1])! + g[j - 1] : -Infinity
        const right = j + 1 < row.length ? pos.get(row[j + 1])! - g[j] : Infinity
        if (target >= left && target <= right) pos.set(id, target)
      })
    }
}

// ---- 5. place in a box --------------------------------------------------------------------------------------------

export type Orientation = 'right' | 'up'

export type PlaceOptions = {
  orientation: Orientation
  /** The view's size (px). */
  box: { w: number; h: number }
  /** Free space kept around the tree (px). */
  pad: number
  /** Distance between layer centers along the flow (px): [min, max]. */
  flow: [number, number]
  /** One half slot across the flow (px): [min, max]. */
  half: [number, number]
  /** What a node needs around its center beyond the grid: before / after along the flow, and across it (px). */
  extent: { before: number; after: number; across: number; acrossBefore?: number; acrossAfter?: number }
  /** Extra flow distance into and out of a layer that holds a hero (px). */
  heroExtra?: number
  heroLayers?: number[]
  /** Widen across the flow only when the whole tree shows at this scale or more (below it the view opens zoomed in). */
  widenFrom?: number
}

export type Placed = {
  /** Centers in content px (before the view's scale). */
  at: Record<string, { x: number; y: number }>
  /** Content size (px). */
  w: number
  h: number
  /** Scale that fits the content into the box (<= 1). */
  scale: number
  flowGap: number
  half: number
}

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))

/**
 * Pixels for a layout in a box. The gaps stretch to fill the box between their min and max; when even the min overflows,
 * `scale` shrinks it to fit. Content coordinates have their origin at the content's top left.
 */
export function placeGraph(l: Layout, o: PlaceOptions): Placed {
  const vertical = o.orientation === 'up'
  const flowBox = (vertical ? o.box.h : o.box.w) - 2 * o.pad
  const crossBox = (vertical ? o.box.w : o.box.h) - 2 * o.pad
  const n = l.layers.length
  const heroSet = new Set(o.heroLayers ?? [])
  const extraAt = (i: number): number => (heroSet.has(i) || heroSet.has(i + 1) ? o.heroExtra ?? 0 : 0)
  let extras = 0
  for (let i = 0; i + 1 < n; i++) extras += extraAt(i)
  const flowSpan = o.extent.before + o.extent.after
  const flowGap = n > 1 ? clamp((flowBox - flowSpan - extras) / (n - 1), o.flow[0], o.flow[1]) : o.flow[0]
  const units = l.max - l.min
  const acrossBefore = o.extent.acrossBefore ?? o.extent.across
  const acrossAfter = o.extent.acrossAfter ?? o.extent.across
  const flowAt: number[] = []
  for (let i = 0; i < n; i++) flowAt.push(i ? flowAt[i - 1] + flowGap + extraAt(i - 1) : o.extent.before)
  const flowLen = (n ? flowAt[n - 1] : 0) + o.extent.after
  const fitScale = (w: number, h: number): number => Math.min(1, (o.box.w - 2 * o.pad) / Math.max(1, w), (o.box.h - 2 * o.pad) / Math.max(1, h))
  const build = (half: number): Placed => {
    const crossLen = units * half + acrossBefore + acrossAfter
    const at: Record<string, { x: number; y: number }> = {}
    for (const it of Object.values(l.items)) {
      const f = flowAt[it.layer]
      const c = (it.pos - l.min) * half + acrossBefore
      at[it.id] = vertical ? { x: c, y: flowLen - f } : { x: f, y: c }
    }
    const w = vertical ? crossLen : flowLen
    const h = vertical ? flowLen : crossLen
    return { at, w, h, scale: Math.max(0.2, fitScale(w, h)), flowGap, half }
  }
  let half = units > 0 ? clamp((crossBox - acrossBefore - acrossAfter) / units, o.half[0], o.half[1]) : o.half[1]
  let p = build(half)
  // Scaled down because the flow is long: widen across the flow to fill the view at that scale (never wider on screen
  // than the max), so a tall tree doesn't stand in a narrow column with empty sides.
  if (p.scale < 1 && p.scale >= (o.widenFrom ?? 0) && units > 0) {
    const wide = clamp((crossBox / p.scale - acrossBefore - acrossAfter) / units, half, o.half[1] / p.scale)
    if (wide > half + 0.5) {
      half = wide
      const q = build(half)
      p = q.scale >= p.scale - 1e-6 ? q : p
    }
  }
  return p
}

// ---- 6. edges -----------------------------------------------------------------------------------------------------

/**
 * One curve style: through every point of the chain, a cubic per gap whose handles run along the flow (half the gap
 * each way), so the curve leaves and enters each layer straight and every joint is smooth.
 */
export function edgePath(points: Array<{ x: number; y: number }>, orientation: Orientation): string {
  if (points.length < 2) return ''
  const f = (n: number): string => (Math.round(n * 10) / 10).toString()
  let d = `M${f(points[0].x)},${f(points[0].y)}`
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    if (orientation === 'right') {
      const m = (b.x - a.x) / 2
      d += ` C${f(a.x + m)},${f(a.y)} ${f(b.x - m)},${f(b.y)} ${f(b.x)},${f(b.y)}`
    } else {
      const m = (b.y - a.y) / 2
      d += ` C${f(a.x)},${f(a.y + m)} ${f(b.x)},${f(b.y - m)} ${f(b.x)},${f(b.y)}`
    }
  }
  return d
}

/** Length of a chain's straight segments (px): a stand-in for the curve's length in draw timing. */
export function chainLength(points: Array<{ x: number; y: number }>): number {
  let n = 0
  for (let i = 1; i < points.length; i++) n += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
  return n
}

/** Do any two placed boxes overlap? (Tests and a dev check: labels never collide.) */
export function overlaps(boxes: Array<{ id: string; x: number; y: number; w: number; h: number }>): Array<[string, string]> {
  const out: Array<[string, string]> = []
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i]
      const b = boxes[j]
      if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) out.push([a.id, b.id])
    }
  return out
}
