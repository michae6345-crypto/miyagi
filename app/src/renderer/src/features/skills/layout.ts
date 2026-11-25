/**
 * Feature: skills. The skill tree's layered layout (Sugiyama style), pure: no React, no DOM, no layout library.
 *
 *   0  rows       (optional, no view uses it now) a run of one track's skills lies flat in one layer (`findRows`)
 *   1  layers     longest path from the roots (`assignLayers`); off the Map each node then slides to the layer that keeps
 *                 its edges shortest. On the Map every skill stays in the layer of its prerequisite depth
 *   2  dummies    an edge that spans k layers gets k-1 invisible way points, so it routes and orders like a node
 *   3  order      barycenter sweeps down and up, then adjacent swaps (`transpose`), keeping the order with the fewest
 *                 crossings (`countCrossings`); ties keep a track's skills together. On the Map (`tracks`) the tracks
 *                 come first: `trackOrder` picks their left-to-right order outward from the trunk (fewest tracks and
 *                 nodes passed by cross-track links, the trunk's and the goal's tracks on the middle, weight balanced)
 *                 and every layer keeps it, so each track grows as one branch. Links that still cross are set aside
 *                 (`hidden`) and the layers are taken again without them when that is shorter
 *   4  straighten each node moves toward the mean of its neighbours (a way point stays between its edge's ends), then
 *                 every layer is packed back into order with its minimum gaps by isotonic regression (pool adjacent
 *                 violators), so long edges run straight and a parent sits centered over its children; a lone root
 *                 (the trunk) and the lone goal sit on the middle; positions end on an integer grid of half slots
 *                 ("even rows"); two unlinked items never share a column in neighbouring layers. On the Map each track
 *                 also pulls its skills toward its own column, and among orders with no more crossings the one whose
 *                 edges pass the fewest nodes they don't touch wins (`passes`)
 *   5  place      `placeGraph` turns layers and slots into pixels for a box: the gaps stretch between a min and a max to
 *                 fill the view, and only past the min does the whole tree scale down (text stays crisp). Each layer
 *                 has a band (its nodes and labels); the space between two bands is the edges' channel
 *   6  edges      `edgeRoute` runs straight through bands and `edgePath` draws one curve style in every channel: a
 *                 cubic whose tangents run along the flow. So no edge ever crosses a node or a label. `edgePorts` gives
 *                 each edge its own port at both ends, so no two edges share a line
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
  /** Between two steps of a flat row (one layer): drawn side to side. */
  flat?: boolean
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
export function assignLayers(ids: string[], links: LayoutLink[], lastIds: string[] = [], balance = true): { layer: Record<string, number>; kept: LayoutLink[]; dropped: LayoutLink[] } {
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

  // Balance: slide toward the heavier side while it shortens the edges (a few passes, from the top down). Off for the
  // Map, where every skill sits in the layer of its prerequisite depth.
  for (let pass = 0; balance && pass < 4; pass++) {
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

/** A segment between two adjacent layers; a row's ports (half slots off its center) where the edge leaves or arrives. */
type Seg = { from: string; to: string; pf?: number; pt?: number }

/** Crossings between two adjacent layers' segments, given each id's index. O(e²), fine for a skill tree. */
export function crossingsBetween(segs: Seg[], index: Map<string, number>): number {
  let n = 0
  for (let i = 0; i < segs.length; i++) {
    const a1 = index.get(segs[i].from)! + (segs[i].pf ?? 0) / 100
    const b1 = index.get(segs[i].to)! + (segs[i].pt ?? 0) / 100
    for (let j = i + 1; j < segs.length; j++) {
      const a2 = index.get(segs[j].from)! + (segs[j].pf ?? 0) / 100
      const b2 = index.get(segs[j].to)! + (segs[j].pt ?? 0) / 100
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

/** A fixed rank that outranks every barycenter (tracks kept side by side on the Map), or none. */
type Rank = ((id: string) => number) | undefined

function sortBy(layer: string[], key: (id: string) => number | undefined, group: (id: string) => number, rank?: Rank): string[] {
  const at = new Map(layer.map((id, i) => [id, i]))
  return [...layer].sort((a, b) => {
    const ka = key(a) ?? at.get(a)!
    const kb = key(b) ?? at.get(b)!
    return (rank ? rank(a) - rank(b) : 0) || ka - kb || group(a) - group(b) || at.get(a)! - at.get(b)!
  })
}

/**
 * Order every layer to remove crossings: barycenter sweeps (each node to the mean index of its neighbours in the layer
 * just placed), then adjacent swaps that lower the count. The best order seen wins; stops early at zero.
 */
export function orderLayers(input: string[][], down: Seg[][], group: (id: string) => number, rounds = 24, rank?: Rank): string[][] {
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
    const seen = new Map<string, number>()
    const visit = (id: string): void => {
      if (seen.has(id)) return
      seen.set(id, seen.size)
      const kids = [...(succs.get(id) ?? [])].sort((a, b) => group(a) - group(b))
      for (const c of reverse ? kids.reverse() : kids) visit(c)
    }
    const roots = input.flat().filter((id) => !preds.get(id)?.length)
    for (const r of sortBy(roots, () => undefined, group, rank)) visit(r)
    return input.map((l) => sortBy(l, (id) => seen.get(id), group, rank))
  }
  const baryStart = (): string[][] => {
    const layers = input.map((l) => [...l])
    layers[0] = sortBy(layers[0], () => undefined, group, rank)
    for (let i = 1; i < layers.length; i++) {
      const index = indexOf(layers)
      layers[i] = sortBy(layers[i], (id) => bary(preds.get(id), index), group, rank)
    }
    return layers
  }
  let best: string[][] = []
  let bestN = Infinity
  for (const start of [dfsStart(false), dfsStart(true), baryStart()]) {
    const layers = start
    transpose(layers, down, rank)
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
          layers[i] = sortBy(layers[i], (id) => bary(preds.get(id), index), group, rank)
        }
      else
        for (let i = layers.length - 2; i >= 0; i--) {
          const index = indexOf(layers)
          layers[i] = sortBy(layers[i], (id) => bary(succs.get(id), index), group, rank)
        }
      transpose(layers, down, rank)
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
function transpose(layers: string[][], down: Seg[][], rank?: Rank, frozen = -1): void {
  for (let guard = 0; guard < 20; guard++) {
    let improved = false
    for (let i = 0; i < layers.length; i++) {
      if (i === frozen) continue
      const local = (): number => {
        const index = indexOf(layers)
        return (i > 0 ? crossingsBetween(down[i - 1] ?? [], index) : 0) + crossingsBetween(down[i] ?? [], index)
      }
      for (let j = 0; j + 1 < layers[i].length; j++) {
        if (rank && rank(layers[i][j]) !== rank(layers[i][j + 1])) continue
        const before = local()
        ;[layers[i][j], layers[i][j + 1]] = [layers[i][j + 1], layers[i][j]]
        if (local() < before) improved = true
        else [layers[i][j], layers[i][j + 1]] = [layers[i][j + 1], layers[i][j]]
      }
    }
    if (!improved) break
  }
}

/**
 * The Map's tracks, left to right (group numbers), so each track grows as one branch beside the next. Every order is
 * tried (seven tracks or fewer; else a greedy build outward from the middle) and the cheapest wins:
 *   - a link between two tracks costs the tracks it has to pass, and much more for each node of a passed track in the
 *     layers it spans (it would cross that branch or run under its nodes)
 *   - `center` (the trunk's track) and `crown` (the goal's) want the middle
 *   - the weight of the tracks (their node counts) balances left and right of the middle
 * Pure; ties keep the input order.
 */
export function trackOrder(ids: string[], links: LayoutLink[], layer: Record<string, number>, groupOf: (id: string) => number, center?: number, crown?: number): number[] {
  const groups = [...new Set(ids.map(groupOf).filter((g) => g >= 0))]
  const T = groups.length
  if (T <= 1) return groups
  const gi = new Map(groups.map((g, i) => [g, i]))
  const size = groups.map(() => 0)
  const occ: number[][] = groups.map(() => [])
  for (const id of ids) {
    const g = gi.get(groupOf(id))
    if (g === undefined) continue
    size[g]++
    occ[g][layer[id]] = (occ[g][layer[id]] ?? 0) + 1
  }
  const span = (g: number, a: number, z: number): number => {
    let n = 0
    for (let L = a; L <= z; L++) n += occ[g][L] ?? 0
    return n
  }
  const cross = links
    .map((l) => ({ a: gi.get(groupOf(l.from)), b: gi.get(groupOf(l.to)), la: layer[l.from], lb: layer[l.to] }))
    .filter((x): x is { a: number; b: number; la: number; lb: number } => x.a !== undefined && x.b !== undefined && x.a !== x.b)
  const total = size.reduce((a, n) => a + n, 0)
  const mid = (T - 1) / 2
  const ci = center !== undefined ? gi.get(center) : undefined
  const gk = crown !== undefined ? gi.get(crown) : undefined
  const cost = (pos: number[]): number => {
    let c = 0
    for (const x of cross) {
      const lo = Math.min(pos[x.a], pos[x.b])
      const hi = Math.max(pos[x.a], pos[x.b])
      c += hi - lo
      for (let g = 0; g < T; g++) if (pos[g] > lo && pos[g] < hi) c += 8 * span(g, Math.min(x.la, x.lb), Math.max(x.la, x.lb))
    }
    const c0 = ci !== undefined ? pos[ci] : mid
    if (ci !== undefined) c += 3 * Math.abs(pos[ci] - mid)
    if (gk !== undefined) c += 3 * Math.abs(pos[gk] - c0)
    let torque = 0
    for (let g = 0; g < T; g++) torque += size[g] * (pos[g] - c0)
    return c + (6 * Math.abs(torque)) / Math.max(1, total)
  }
  let best: number[] = groups.map((_, i) => i)
  let bestC = cost(best)
  if (T <= 7) {
    // Heap's algorithm over positions.
    const perm = groups.map((_, i) => i)
    const c = perm.map(() => 0)
    let i = 0
    while (i < T) {
      if (c[i] < i) {
        const j = i % 2 ? c[i] : 0
        ;[perm[j], perm[i]] = [perm[i], perm[j]]
        const k = cost(perm)
        if (k < bestC - 1e-9) {
          bestC = k
          best = [...perm]
        }
        c[i]++
        i = 0
      } else c[i++] = 0
    }
  } else {
    // Greedy: start from the trunk's track, add the track that costs least at either end.
    let seq = [ci ?? 0]
    const left = new Set(groups.map((_, i) => i).filter((i) => i !== seq[0]))
    while (left.size) {
      let pick: number[] = []
      let pc = Infinity
      for (const g of left)
        for (const s of [
          [g, ...seq],
          [...seq, g]
        ]) {
          const rest = [...left].filter((x) => x !== g)
          const full = [...s, ...rest]
          const pos = groups.map(() => 0)
          full.forEach((x, i) => (pos[x] = i))
          const k = cost(pos)
          if (k < pc) {
            pc = k
            pick = s
          }
        }
      seq = pick
      for (const g of seq) left.delete(g)
    }
    best = groups.map(() => 0)
    seq.forEach((x, i) => (best[x] = i))
  }
  // best[g] is the position of track g: back to groups in left-to-right order.
  return groups.map((g, i) => ({ g, p: best[i] })).sort((a, b) => a.p - b.p).map((x) => x.g)
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
const ROW = '\u0001'
export const isDummy = (id: string): boolean => id.startsWith(DUMMY)

type RouteLink = { from: string; to: string; pf?: number; pt?: number }

/**
 * Route `drawn` through the layers (way points for long edges) and order them. Fresh arrays each call; `edges[i]` is
 * `drawn[i]`'s.
 */
function route(ids: string[], layerOf: Record<string, number>, drawn: RouteLink[], groupOf: Map<string, number>, span: Map<string, number>, trackPos?: Map<number, number>) {
  /** With tracks: each item's rank (its track's place; a way point between its edge's two tracks, by layer). */
  const rankOf = new Map<string, number>()
  const mid = trackPos && trackPos.size ? (Math.min(...trackPos.values()) + Math.max(...trackPos.values())) / 2 : 0
  const trackRank = (id: string): number => trackPos?.get(groupOf.get(id) ?? -1) ?? mid
  if (trackPos) for (const id of ids) rankOf.set(id, trackRank(id))
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
      if (trackPos) {
        const a = trackRank(l.from)
        const z = trackRank(l.to)
        rankOf.set(d, a + ((z - a) * (i - layer[l.from])) / (layer[l.to] - layer[l.from]))
      }
      span.set(d, 1)
      layer[d] = i
      chain.push(d)
    }
    chain.push(l.to)
    for (let i = 0; i + 1 < chain.length; i++) {
      const seg: Seg = { from: chain[i], to: chain[i + 1], pf: i === 0 ? l.pf : undefined, pt: i + 2 === chain.length ? l.pt : undefined }
      down[layer[chain[i]]].push(seg)
      segEdge.set(seg, edges.length)
    }
    edges.push({ from: l.from, to: l.to, chain })
  }
  const ordered = nLayers ? orderLayers(layers, down, (id) => groupOf.get(id) ?? 0, 24, trackPos ? (id) => rankOf.get(id) ?? mid : undefined) : []
  // Crossings per edge.
  const index = indexOf(ordered)
  const per = edges.map(() => 0)
  const at = (id: string, port: number | undefined): number => index.get(id)! + (port ?? 0) / 100
  for (const segs of down)
    for (let i = 0; i < segs.length; i++)
      for (let j = i + 1; j < segs.length; j++) {
        const a = segs[i]
        const b = segs[j]
        if ((at(a.from, a.pf) - at(b.from, b.pf)) * (at(a.to, a.pt) - at(b.to, b.pt)) < 0) {
          per[segEdge.get(a)!]++
          per[segEdge.get(b)!]++
        }
      }
  return { layer, ordered, down, edges, per, crossings: per.reduce((a, n) => a + n, 0) / 2, nLayers, rank: trackPos ? rankOf : undefined }
}

export type LayoutOptions = {
  /**
   * Lay a run of one track's skills flat along one layer (a branch, not a tower), each step the only way into the next,
   * where that shortens the tree (findRows). Keeps a deep map short enough for a wide window.
   */
  rows?: boolean
  /** The longest flat run (nodes). */
  maxRow?: number
  /** Stop laying runs flat once the tree is this many layers or fewer. */
  maxDepth?: number
  /**
   * The Map: every skill in the layer of its prerequisite depth (no sliding), each track kept together as a branch,
   * tracks ordered outward from the trunk (trackOrder) and pulled into their own columns while straightening.
   */
  tracks?: { center?: number; crown?: number }
}

/**
 * The runs to lay flat (see LayoutOptions.rows), as paths of ids. A link u > v can lie flat when both are in one track,
 * v has no other way in, neither is `fixed` (the goal, a lone root, a node of another size) and the joined run stays
 * within `max`. Only links on a longest chain are laid flat (each one shortens the tree or nothing does), one at a time,
 * until the tree is `depth` layers or less. Pure.
 */
export function findRows(ids: string[], links: LayoutLink[], groupOf: (id: string) => number, fixed: Set<string>, max = 5, depth = 1): string[][] {
  const outs = new Map<string, string[]>()
  const ins = new Map<string, string[]>()
  for (const l of links) {
    outs.set(l.from, [...(outs.get(l.from) ?? []), l.to])
    ins.set(l.to, [...(ins.get(l.to) ?? []), l.from])
  }
  // Topological order (links are acyclic here).
  const order: string[] = []
  const deg = new Map(ids.map((id) => [id, ins.get(id)?.length ?? 0]))
  const queue = ids.filter((id) => !deg.get(id))
  while (queue.length) {
    const id = queue.shift()!
    order.push(id)
    for (const v of outs.get(id) ?? []) {
      deg.set(v, deg.get(v)! - 1)
      if (!deg.get(v)) queue.push(v)
    }
  }
  const next = new Map<string, string>()
  const prev = new Map<string, string>()
  const len = (id: string): number => {
    let a = id
    while (prev.has(a)) a = prev.get(a)!
    let n = 1
    while (next.has(a)) (a = next.get(a)!), n++
    return n
  }
  const cost = (u: string, v: string): number => (next.get(u) === v ? 0 : 1)
  for (let guard = 0; guard < links.length; guard++) {
    const lev = new Map<string, number>()
    for (const id of order) lev.set(id, Math.max(0, ...(ins.get(id) ?? []).map((u) => lev.get(u)! + cost(u, id))))
    const tail = new Map<string, number>()
    for (const id of [...order].reverse()) tail.set(id, Math.max(0, ...(outs.get(id) ?? []).map((v) => tail.get(v)! + cost(id, v))))
    const D = Math.max(0, ...lev.values()) + 1
    if (D <= depth) break
    const pick = links
      .filter((l) => {
        const { from: u, to: v } = l
        if (next.has(u) || prev.has(v) || fixed.has(u) || fixed.has(v)) return false
        if ((ins.get(v)?.length ?? 0) !== 1 || groupOf(u) !== groupOf(v) || len(u) + len(v) > max) return false
        if ((outs.get(u)?.length ?? 0) > 1 && (outs.get(v)?.length ?? 0) > 0) return false
        return lev.get(u)! + 1 + tail.get(v)! === D - 1
      })
      // A plain chain step first (v leads on to at most one), then input order.
      .sort((p, q) => Math.min(1, outs.get(p.to)?.length ?? 0) - Math.min(1, outs.get(q.to)?.length ?? 0) || (outs.get(p.to)?.length ?? 0) - (outs.get(q.to)?.length ?? 0))[0]
    if (!pick) break
    next.set(pick.from, pick.to)
    prev.set(pick.to, pick.from)
  }
  // Then every plain chain step of a track lies flat too (one way on, one way in, at most one way out after), so two
  // tracks shaped alike look alike whether or not they were on the longest chain.
  for (const { from: u, to: v } of links) {
    if (next.has(u) || prev.has(v) || fixed.has(u) || fixed.has(v) || groupOf(u) !== groupOf(v)) continue
    if ((outs.get(u)?.length ?? 0) !== 1 || (ins.get(v)?.length ?? 0) !== 1 || (outs.get(v)?.length ?? 0) > 1 || len(u) + len(v) > max) continue
    next.set(u, v)
    prev.set(v, u)
  }
  const rows: string[][] = []
  for (const u of order) {
    if (prev.has(u) || !next.has(u)) continue
    const run = [u]
    for (let c = u; next.has(c); ) run.push((c = next.get(c)!))
    rows.push(run)
  }
  return rows
}

type Built = {
  rows: string[][]
  rowOf: Map<string, { rid: string; i: number; k: number }>
  cIds: string[]
  ordered: string[][]
  down: Seg[][]
  /** Routed edges over the contracted ids; `origs[i]` is edges[i]'s link between real nodes. */
  edges: LayoutEdge[]
  origs: LayoutLink[]
  flat: LayoutLink[]
  hidden: LayoutLink[]
  crossings: number
  nLayers: number
  groupOf: Map<string, number>
  span: Map<string, number>
  trackPos?: Map<number, number>
  /** With tracks: each ordered item's rank (orderLayers keeps it). */
  rank?: Map<string, number>
}

/** Rows contracted to one wide item each, layered, routed and ordered; links set aside until nothing crosses. */
function build(ids: string[], links: LayoutLink[], lastIds: string[], baseGroup: Map<string, number>, baseSpan: Map<string, number>, fixed: Set<string>, opts: LayoutOptions): Built {
  const groupOf = new Map(baseGroup)
  const span = new Map(baseSpan)
  const rows = opts.rows ? findRows(ids, links, (id) => groupOf.get(id) ?? 0, fixed, opts.maxRow ?? 5, opts.maxDepth ?? 1) : []
  const rowOf = new Map<string, { rid: string; i: number; k: number }>()
  for (const r of rows) {
    const rid = ROW + r[0]
    r.forEach((id, i) => rowOf.set(id, { rid, i, k: r.length }))
    groupOf.set(rid, groupOf.get(r[0]) ?? 0)
    span.set(rid, 2 * r.length)
  }
  const c = (id: string): string => rowOf.get(id)?.rid ?? id
  /** A row's steps sit left to right, 2 half slots apart, around its center. */
  const port = (id: string): number | undefined => {
    const r = rowOf.get(id)
    return r ? 2 * r.i - (r.k - 1) : undefined
  }
  const cIds: string[] = []
  for (const id of ids) {
    const r = rowOf.get(id)
    if (!r) cIds.push(id)
    else if (r.i === 0) cIds.push(r.rid)
  }
  const flat = links.filter((l) => rowOf.has(l.from) && rowOf.get(l.from)!.rid === rowOf.get(l.to)?.rid)
  const ext = links.filter((l) => !flat.includes(l))
  const { layer } = assignLayers(
    cIds,
    ext.map((l) => ({ from: c(l.from), to: c(l.to) })),
    lastIds.map(c),
    !opts.tracks
  )
  // The Map's tracks left to right (the goal and the trunk point stay out of the weighing: they sit on the middle).
  let trackPos: Map<number, number> | undefined
  if (opts.tracks) {
    const real = cIds.filter((id) => !lastIds.includes(id) && (groupOf.get(id) ?? -1) >= 0)
    const order = trackOrder(
      real,
      ext.filter((l) => real.includes(l.from) && real.includes(l.to)),
      layer,
      (id) => groupOf.get(id) ?? -1,
      opts.tracks.center,
      opts.tracks.crown
    )
    trackPos = new Map(order.map((g, i) => [g, i]))
  }
  let drawn = ext
  const hidden: LayoutLink[] = []
  const go = () =>
    route(
      cIds,
      layer,
      drawn.map((l) => ({ from: c(l.from), to: c(l.to), pf: port(l.from), pt: port(l.to) })),
      groupOf,
      span,
      trackPos
    )
  let r = go()
  for (let guard = 0; r.crossings > 0 && guard < ext.length; guard++) {
    const inDeg = (id: string): number => drawn.filter((l) => l.to === id).length
    const outDeg = (id: string): number => drawn.filter((l) => l.from === id).length
    const score = (i: number): number => {
      const l = drawn[i]
      if (!r.per[i]) return -Infinity
      const keepsWay = inDeg(l.to) > 1 ? 1000 : 0
      const keepsOut = outDeg(l.from) > 1 ? 20 : 0
      const across = (groupOf.get(l.from) ?? 0) !== (groupOf.get(l.to) ?? 0) ? 10 : 0
      return keepsWay + keepsOut + across + 3 * r.per[i] + (layer[c(l.to)] - layer[c(l.from)])
    }
    let pick = 0
    for (let i = 1; i < drawn.length; i++) if (score(i) > score(pick)) pick = i
    if (score(pick) === -Infinity) break
    hidden.push(drawn[pick])
    drawn = drawn.filter((_, i) => i !== pick)
    r = go()
  }
  return { rows, rowOf, cIds, ordered: r.ordered, down: r.down, edges: r.edges, origs: drawn, flat, hidden, crossings: r.crossings, nLayers: r.nLayers, groupOf, span, trackPos, rank: r.rank }
}

type Nb = { other: string; mine: number; theirs: number }

/**
 * How many times an edge runs past a node it doesn't touch, in half slots: between two layers an edge's curve keeps to
 * its source's side for the lower half of the channel and its target's for the upper half, so a node of either layer
 * less than one half slot from that stretch has the edge running over or under it.
 */
export function passes(ordered: string[][], pos: Map<string, number>, edges: LayoutEdge[]): number {
  const layerOf = new Map<string, number>()
  ordered.forEach((row, i) => row.forEach((id) => layerOf.set(id, i)))
  let n = 0
  for (const e of edges)
    for (let i = 0; i + 1 < e.chain.length; i++) {
      const a = e.chain[i]
      const z = e.chain[i + 1]
      const L = layerOf.get(a)
      if (L === undefined || layerOf.get(z) !== L + 1) continue
      const pa = pos.get(a)!
      const pz = pos.get(z)!
      const mid = (pa + pz) / 2
      const by = (id: string, x: number, y: number): boolean => !isDummy(id) && id !== a && id !== z && pos.get(id)! > Math.min(x, y) - 1 && pos.get(id)! < Math.max(x, y) + 1
      for (const id of ordered[L]) if (by(id, pa, mid)) n++
      for (const id of ordered[L + 1] ?? []) if (by(id, mid, pz)) n++
    }
  return n
}

/**
 * The layout. Layers come from the links (columns by prerequisite depth). When no order draws every link without a
 * crossing (some prerequisite graphs can't be drawn flat in layers), the fewest links are set aside as `hidden`, one at
 * a time: the one in the most crossings, a link between two groups before one inside a group, and never a node's last
 * drawn way in; the layers are then taken again without them when that makes the tree shorter. The view draws hidden
 * links only for the node in focus, so the resting tree has zero crossings.
 */
export function layoutGraph(nodes: LayoutNode[], links: LayoutLink[], opts: LayoutOptions = {}): Layout {
  const ids = nodes.map((n) => n.id)
  const lastIds = nodes.filter((n) => n.last).map((n) => n.id)
  const { kept } = assignLayers(ids, links, lastIds)
  const group0 = new Map<string, number>(nodes.map((n) => [n.id, n.group ?? 0]))
  const span0 = new Map<string, number>(nodes.map((n) => [n.id, n.span ?? 2]))
  // Never flat: the goal, a node of another size, and a lone root (the trunk stays a trunk).
  const roots = ids.filter((id) => !kept.some((l) => l.to === id))
  const fixed = new Set([...lastIds, ...nodes.filter((n) => (n.span ?? 2) !== 2).map((n) => n.id), ...(roots.length === 1 ? roots : [])])

  // 1–3. Rows, layers, way points and order; again without the hidden links when that's shorter and still flat.
  let b = build(ids, kept, lastIds, group0, span0, fixed, opts)
  if (b.hidden.length) {
    const b2 = build(
      ids,
      kept.filter((l) => !b.hidden.includes(l)),
      lastIds,
      group0,
      span0,
      fixed,
      opts
    )
    if (b2.crossings === 0 && !b2.hidden.length && b2.nLayers <= b.nLayers) b = { ...b2, hidden: [...b.hidden, ...b2.hidden] }
  }
  const { rowOf, rows, span } = b

  /** Steps 4 (straighten) and the clean-ups after it, for one order of the layers: positions in half slots. */
  const solve = (ordered: string[][]): { pos: Map<string, number>; offset: (id: string) => number } => {

    // A row's steps run left to right as ordered; one in the left half of its layer turns to run leftward (away from the
    // middle, like a branch), when only one of its steps leads on (so turning it can't cross its own edges).
    const flip = new Set<string>()
    for (const row of ordered)
      row.forEach((id, j) => {
        if (!id.startsWith(ROW) || 2 * j >= row.length - 1) return
        const r = rows.find((x) => ROW + x[0] === id)!
        if (r.filter((m) => b.origs.some((o) => o.from === m)).length <= 1) flip.add(id)
      })
    const offset = (id: string): number => {
      const r = rowOf.get(id)
      return r ? (flip.has(r.rid) ? -1 : 1) * (2 * r.i - (r.k - 1)) : 0
    }

    // 4. Straighten. Neighbours per item with the ports the edge leaves and arrives at (a row's members), both ways.
    const up = new Map<string, Nb[]>()
    const dn = new Map<string, Nb[]>()
    const ends = new Map<string, { a: string; pa: number; b: string; pb: number }>()
    b.edges.forEach((e, k) => {
      const o = b.origs[k]
      const pf = offset(o.from)
      const pt = offset(o.to)
      for (let i = 0; i + 1 < e.chain.length; i++) {
        const x = e.chain[i]
        const y = e.chain[i + 1]
        const px = i === 0 ? pf : 0
        const py = i + 2 === e.chain.length ? pt : 0
        dn.set(x, [...(dn.get(x) ?? []), { other: y, mine: px, theirs: py }])
        up.set(y, [...(up.get(y) ?? []), { other: x, mine: py, theirs: px }])
      }
      for (const d of e.chain.slice(1, -1)) ends.set(d, { a: e.chain[0], pa: pf, b: e.chain[e.chain.length - 1], pb: pt })
    })
    const gapAfter = (row: string[]): number[] => row.slice(0, -1).map((id, i) => Math.ceil((span.get(id)! + span.get(row[i + 1])!) / 2))
    const pos = new Map<string, number>()
    for (const row of ordered) {
      const g = gapAfter(row)
      let x = 0
      const xs = row.map((_, i) => (i ? (x += g[i - 1]) : 0))
      const mid = xs.length ? (xs[0] + xs[xs.length - 1]) / 2 : 0
      row.forEach((id, i) => pos.set(id, xs[i] - mid))
    }
    /** A dummy stays between its edge's two ends (no loop out past either). */
    const within = (d: string): [number, number] | undefined => {
      const e = ends.get(d)
      if (!e) return undefined
      const a = pos.get(e.a)! + e.pa
      const z = pos.get(e.b)! + e.pb
      return [Math.min(a, z), Math.max(a, z)]
    }
    // Anchors: a lone root (the trunk) and a lone pinned last node (the goal) sit on the middle of everything else.
    const anchors = new Set<string>()
    const real = (row: string[]): string[] => row.filter((id) => !isDummy(id))
    if (ordered.length > 1 && real(ordered[0]).length === 1 && ordered[0].length === 1) anchors.add(ordered[0][0])
    for (const row of ordered) if (row.length === 1 && lastIds.includes(row[0])) anchors.add(row[0])
    const middle = (): number => {
      let lo = Infinity
      let hi = -Infinity
      for (const row of ordered)
        for (const id of row) {
          if (isDummy(id) || anchors.has(id)) continue
          const half = (span.get(id)! - 2) / 2
          lo = Math.min(lo, pos.get(id)! - half)
          hi = Math.max(hi, pos.get(id)! + half)
        }
      return lo <= hi ? (lo + hi) / 2 : 0
    }
    const weight = (id: string): number => (anchors.has(id) ? 40 : isDummy(id) ? 8 : 1 + (up.get(id)?.length ?? 0) + (dn.get(id)?.length ?? 0))
    // The Map: each track also pulls its skills toward its own column (the mean of its skills), so a track stands as one
    // branch instead of leaning after every link out of it.
    const groupOf = (id: string): number => b.groupOf.get(id) ?? -1
    const colOf = (): Map<number, number> => {
      const sum = new Map<number, [number, number]>()
      for (const row of ordered)
        for (const id of row) {
          if (isDummy(id) || anchors.has(id) || groupOf(id) < 0) continue
          const [a, n] = sum.get(groupOf(id)) ?? [0, 0]
          sum.set(groupOf(id), [a + pos.get(id)!, n + 1])
        }
      return new Map([...sum].map(([g, [a, n]]) => [g, a / n]))
    }
    const PULL = 2
    const sweep = (i: number, toward: 'up' | 'dn' | 'both', mid: number): void => {
      const row = ordered[i]
      const cols = b.trackPos ? colOf() : undefined
      const want = row.map((id) => {
        if (anchors.has(id)) return mid
        const nb = [...(toward !== 'dn' ? (up.get(id) ?? []) : []), ...(toward !== 'up' ? (dn.get(id) ?? []) : [])]
        const col = !isDummy(id) ? cols?.get(groupOf(id)) : undefined
        const sum = nb.reduce((a, n) => a + pos.get(n.other)! + n.theirs - n.mine, 0) + (col !== undefined ? PULL * col : 0)
        const cnt = nb.length + (col !== undefined ? PULL : 0)
        let w = cnt ? sum / cnt : pos.get(id)!
        const span = within(id)
        if (span) w = clamp(w, span[0], span[1])
        return w
      })
      const placed = packLayer(want, row.map(weight), gapAfter(row))
      row.forEach((id, j) => pos.set(id, placed[j]))
    }
    for (let it = 0; it < 10; it++) {
      const mid = middle()
      for (let i = 1; i < ordered.length; i++) sweep(i, 'up', mid)
      for (let i = ordered.length - 2; i >= 0; i--) sweep(i, 'dn', mid)
    }
    for (let it = 0; it < 6; it++) {
      const mid = middle()
      for (let i = 0; i < ordered.length; i++) sweep(i, 'both', mid)
    }
    // Snap to the half-slot grid, layer by layer, then line single parents up with single children where that's free.
    for (const row of ordered) {
      const snapped = snapLayer(
        row.map((id) => pos.get(id)!),
        gapAfter(row)
      )
      row.forEach((id, j) => pos.set(id, snapped[j]))
    }
    const mid = Math.round(middle())
    for (const id of anchors) {
      // Alone in its layer: free to sit exactly on the middle.
      pos.set(id, mid)
    }
    straightenChains(ordered, pos, up, dn, gapAfter, anchors)

    // Real items of two layers in one column with no edge between them read as linked: move one a half slot aside.
    const linked = new Set([...b.origs, ...b.flat].map((l) => `${l.from}>${l.to}`))
    const cols = (id: string): Array<[string, number]> => {
      if (isDummy(id)) return []
      const r = id.startsWith(ROW) ? rows.find((x) => ROW + x[0] === id) : undefined
      return r ? r.map((m) => [m, pos.get(id)! + offset(m)]) : [[id, pos.get(id)!]]
    }
    const clash = (lowerRow: string[] | undefined, upperRow: string[] | undefined): Array<[string, string]> => {
      const out: Array<[string, string]> = []
      for (const lo of lowerRow ?? [])
        for (const hi of upperRow ?? [])
          for (const [a, xa] of cols(lo)) for (const [z, xz] of cols(hi)) if (xa === xz && !linked.has(`${a}>${z}`)) out.push([lo, hi])
      return out
    }
    const room = (row: string[], j: number): [number, number] => {
      const g = gapAfter(row)
      return [j > 0 ? pos.get(row[j - 1])! + g[j - 1] : -Infinity, j + 1 < row.length ? pos.get(row[j + 1])! - g[j] : Infinity]
    }
    for (let pass = 0; pass < 3; pass++) {
      let moved = false
      for (let i = 0; i + 1 < ordered.length; i++)
        for (const [lo, hi] of clash(ordered[i], ordered[i + 1])) {
          // Try the upper one, then the lower one, each a half slot either way, keeping order, gaps and anchors.
          const tries: Array<[string, number]> = [
            [hi, i + 1],
            [lo, i]
          ]
          for (const [id, li] of tries) {
            if (anchors.has(id)) continue
            const row = ordered[li]
            const j = row.indexOf(id)
            const [a, z] = room(row, j)
            const x0 = pos.get(id)!
            const ok = [x0 + 1, x0 - 1].find((x) => {
              if (x < a || x > z) return false
              pos.set(id, x)
              const fine = !clash(ordered[li - 1], ordered[li]).length && !clash(ordered[li], ordered[li + 1]).length
              pos.set(id, x0)
              return fine
            })
            if (ok !== undefined) {
              pos.set(id, ok)
              moved = true
              break
            }
          }
        }
      if (!moved) break
    }
    // Way points back inside their edge's span where a move above left them out.
    for (let pass = 0; pass < 4; pass++)
      for (const row of ordered)
        row.forEach((id, j) => {
          const s = within(id)
          if (!s) return
          const x = pos.get(id)!
          if (x >= s[0] && x <= s[1]) return
          const t = Math.round(clamp(x, s[0], s[1]))
          // Move it there, pushing its neighbours on that side along when they're in the way; keep the move only when it
          // leaves every other way point inside its span and no unlinked pair sharing a column.
          const before = new Map(row.map((r) => [r, pos.get(r)!]))
          pos.set(id, t)
          const g = gapAfter(row)
          if (t > x) for (let k = j + 1; k < row.length; k++) pos.set(row[k], Math.max(pos.get(row[k])!, pos.get(row[k - 1])! + g[k - 1]))
          else for (let k = j - 1; k >= 0; k--) pos.set(row[k], Math.min(pos.get(row[k])!, pos.get(row[k + 1])! - g[k]))
          const li = ordered.indexOf(row)
          const fine =
            row.every((r) => {
              const w = within(r)
              return !w || (pos.get(r)! >= w[0] && pos.get(r)! <= w[1]) || pos.get(r) === before.get(r)
            }) &&
            !clash(ordered[li - 1], row).length &&
            !clash(row, ordered[li + 1]).length
          if (fine) return
          for (const [r, v] of before) pos.set(r, v)
          // Else bring one end of the edge over to the way point (an end free to move, by the same rules).
          const e = ends.get(id)!
          const allIn = (): boolean =>
            ordered.every((r) =>
              r.every((d) => {
                const w = within(d)
                return !w || (pos.get(d)! >= w[0] && pos.get(d)! <= w[1]) || d === id
              })
            )
          for (const end of [e.b, e.a]) {
            const er = ordered.find((r) => r.includes(end))!
            const k = er.indexOf(end)
            const [lo, hi] = room(er, k)
            const port = end === e.a ? e.pa : e.pb
            const want = x - port
            const ex = pos.get(end)!
            if (want < lo || want > hi || anchors.has(end)) continue
            pos.set(end, want)
            const li2 = ordered.indexOf(er)
            const inside = (() => {
              const w = within(id)!
              return x >= w[0] && x <= w[1]
            })()
            if (inside && allIn() && !clash(ordered[li2 - 1], er).length && !clash(er, ordered[li2 + 1]).length) return
            pos.set(end, ex)
          }
        })

    return { pos, offset }
  }

  // The Map: among the orders with no more crossings, prefer one where no edge passes over or under a node it doesn't
  // touch (a link that runs past a node reads as linked to it). One swap of neighbours of a track at a time, the other
  // layers re-settled around it; kept when it passes fewer nodes.
  let ordered = b.ordered
  let sol = solve(ordered)
  if (b.rank) {
    const rank = (id: string): number => b.rank!.get(id) ?? 0
    let best = passes(ordered, sol.pos, b.edges)
    for (let round = 0; round < 4 && best > 0; round++) {
      let improved = false
      for (let L = 0; L < ordered.length && best > 0; L++)
        for (let j = 0; j + 1 < ordered[L].length && best > 0; j++) {
          if (rank(ordered[L][j]) !== rank(ordered[L][j + 1])) continue
          const cand = ordered.map((row) => [...row])
          ;[cand[L][j], cand[L][j + 1]] = [cand[L][j + 1], cand[L][j]]
          transpose(cand, b.down, rank, L)
          if (countCrossings(cand, b.down) > b.crossings) continue
          const s2 = solve(cand)
          const n = passes(cand, s2.pos, b.edges)
          if (n < best) {
            best = n
            ordered = cand
            sol = s2
            improved = true
          }
        }
      if (!improved) break
    }
  }
  const { pos, offset } = sol

  // Center on 0, then lay each row's members out from its center.
  const all = [...pos.entries()].flatMap(([id, x]) => (id.startsWith(ROW) ? [x - (span.get(id)! - 2) / 2, x + (span.get(id)! - 2) / 2] : [x]))
  const lo = all.length ? Math.min(...all) : 0
  const hi = all.length ? Math.max(...all) : 0
  const shift = Math.round((lo + hi) / 2)
  const items: Record<string, LayoutItem> = {}
  const layers: string[][] = ordered.map((row) =>
    row.flatMap((id) => {
      const r = id.startsWith(ROW) ? rows.find((x) => ROW + x[0] === id) : undefined
      return r ? [...r].sort((p, q) => offset(p) - offset(q)) : [id]
    })
  )
  layers.forEach((row, li) =>
    row.forEach((id, order) => {
      const rid = rowOf.get(id)?.rid
      const x = rid ? pos.get(rid)! + offset(id) : pos.get(id)!
      items[id] = { id, dummy: isDummy(id), layer: li, order, pos: x - shift, span: rid ? 2 : span.get(id)! }
    })
  )
  const edges: LayoutEdge[] = [
    ...b.edges.map((e, k) => ({ from: b.origs[k].from, to: b.origs[k].to, chain: [b.origs[k].from, ...e.chain.slice(1, -1), b.origs[k].to] })),
    ...b.flat.map((l) => ({ from: l.from, to: l.to, chain: [l.from, l.to], flat: true }))
  ]
  const ps = Object.values(items).map((i) => i.pos)
  return { items, layers, edges, hidden: b.hidden, crossings: b.crossings, min: ps.length ? Math.min(...ps) : 0, max: ps.length ? Math.max(...ps) : 0 }
}

/**
 * After snapping, an edge between two items that are each other's only neighbour on that side and sit within one half
 * slot of each other is made dead straight when the move keeps the layer's order and gaps (no wobble of a half slot).
 */
function straightenChains(
  ordered: string[][],
  pos: Map<string, number>,
  up: Map<string, Nb[]>,
  dn: Map<string, Nb[]>,
  gapAfter: (row: string[]) => number[],
  anchors: Set<string>
): void {
  for (let pass = 0; pass < 3; pass++)
    for (const row of ordered) {
      const g = gapAfter(row)
      row.forEach((id, j) => {
        if (anchors.has(id)) return
        const ups = up.get(id) ?? []
        const dns = dn.get(id) ?? []
        const ns = [...ups.map((n) => ({ n, only: (dn.get(n.other)?.length ?? 0) === 1 })), ...dns.map((n) => ({ n, only: (up.get(n.other)?.length ?? 0) === 1 }))]
        if (!ns.length || ns.some((x) => !x.only)) return
        const target = Math.round(ns.reduce((a, { n }) => a + pos.get(n.other)! + n.theirs - n.mine, 0) / ns.length)
        if (Math.abs(target - pos.get(id)!) > 1) return
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
  /** Distance between layer centers along the flow (px): [min, max] (a pair of bands may need more than the min). */
  flow: [number, number]
  /** One half slot across the flow (px): [min, max]. */
  half: [number, number]
  /** What a node needs around its center beyond the grid: before / after along the flow, and across it (px). */
  extent: { before: number; after: number; across: number; acrossBefore?: number; acrossAfter?: number }
  /**
   * Per layer, what its items reach along the flow before and after their centers (px): the layer's band. Edges run
   * straight through bands and bend only in the free channel between two (at least `channel` px).
   */
  bands?: Array<{ before: number; after: number }>
  channel?: number
  /** Per layer, what must not touch the next layer's (labels wider than their bands), kept `roomGap` apart. */
  room?: Array<{ before: number; after: number }>
  roomGap?: number
  /** Extra flow distance into and out of a layer that holds a hero (px). */
  heroExtra?: number
  heroLayers?: number[]
  /** One pitch for every layer gap (the Map's even grid): the gaps stay equal, between `flow`'s min and max. */
  uniform?: boolean
  /** Widen across the flow only when the whole tree shows at this scale or more (omit to never widen). */
  widenFrom?: number
  /**
   * The smallest scale the view opens at (text stays readable). When the whole tree would need less, it opens at this
   * scale (its width in view, as many layers as fit) and the view pans along the flow; `whole` still shows all of it.
   */
  minScale?: number
}

export type Placed = {
  /** Centers in content px (before the view's scale). */
  at: Record<string, { x: number; y: number }>
  /** Per layer, its band's edges in content px along the flow: toward the layer before (`near`) and after (`far`). */
  bands: Array<{ near: number; far: number }>
  /** Content size (px). */
  w: number
  h: number
  /** Scale the view opens at: the whole content in the box (<= 1), or, below `minScale`, the width at that scale or more. */
  scale: number
  /** Scale that shows the whole content (Fit). Equal to `scale` unless minScale held it up. */
  whole: number
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
  const band = (i: number): { before: number; after: number } => o.bands?.[i] ?? { before: o.extent.before, after: o.extent.after }
  const minGap: number[] = []
  const room = (i: number): { before: number; after: number } => o.room?.[i] ?? band(i)
  for (let i = 0; i + 1 < n; i++) minGap.push(Math.max(o.flow[0], band(i).after + (o.channel ?? 0) + band(i + 1).before, room(i).after + (o.roomGap ?? 0) + room(i + 1).before) + extraAt(i))
  const ends = n ? Math.max(band(0).before, room(0).before) + Math.max(band(n - 1).after, room(n - 1).after) : o.extent.before + o.extent.after
  const free = flowBox - ends - minGap.reduce((a, g) => a + g, 0)
  // Every gap stretches by the same amount to fill the box, each up to the max (a gap that needs more keeps its min).
  const stretch = n > 1 ? Math.max(0, free / (n - 1)) : 0
  const same = n > 1 ? clamp((flowBox - ends) / (n - 1), Math.max(...minGap), Math.max(...minGap, o.flow[1])) : 0
  const gapAt = (i: number): number => (o.uniform ? same : Math.max(minGap[i], Math.min(o.flow[1] + extraAt(i), minGap[i] + stretch)))
  const units = l.max - l.min
  const acrossBefore = o.extent.acrossBefore ?? o.extent.across
  const acrossAfter = o.extent.acrossAfter ?? o.extent.across
  const flowAt: number[] = []
  for (let i = 0; i < n; i++) flowAt.push(i ? flowAt[i - 1] + gapAt(i - 1) : Math.max(band(0).before, room(0).before))
  const flowLen = n ? flowAt[n - 1] + Math.max(band(n - 1).after, room(n - 1).after) : ends
  const flowGap = n > 1 ? (flowAt[n - 1] - flowAt[0]) / (n - 1) : o.flow[0]
  const toScreen = (f: number): number => (vertical ? flowLen - f : f)
  const bands = flowAt.map((f, i) => ({ near: toScreen(f - band(i).before), far: toScreen(f + band(i).after) }))
  const fitScale = (w: number, h: number): number => Math.min(1, (o.box.w - 2 * o.pad) / Math.max(1, w), (o.box.h - 2 * o.pad) / Math.max(1, h))
  const build = (half: number): Placed => {
    const crossLen = units * half + acrossBefore + acrossAfter
    const at: Record<string, { x: number; y: number }> = {}
    for (const it of Object.values(l.items)) {
      const f = flowAt[it.layer]
      const c = (it.pos - l.min) * half + acrossBefore
      at[it.id] = vertical ? { x: c, y: toScreen(f) } : { x: f, y: c }
    }
    const w = vertical ? crossLen : flowLen
    const h = vertical ? flowLen : crossLen
    const whole = Math.max(0.2, fitScale(w, h))
    const scale = o.minScale && whole < o.minScale ? o.minScale : whole
    return { at, bands, w, h, scale, whole, flowGap, half }
  }
  let half = units > 0 ? clamp((crossBox - acrossBefore - acrossAfter) / units, o.half[0], o.half[1]) : o.half[1]
  let p = build(half)
  // Scaled down because the flow is long: widen across the flow to fill the view at that scale (never wider on screen
  // than the max), so a tall tree doesn't stand in a narrow column with empty sides.
  if (o.widenFrom !== undefined && p.scale < 1 && p.scale >= o.widenFrom && units > 0) {
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

type Pt = { x: number; y: number }

/**
 * The points an edge's curve passes (content px). It leaves its source at `reach(id).out` along the flow (the node's
 * edge), runs straight to its layer's band edge, bends through the channel, runs straight through each way point's
 * band, and arrives at `reach(id).in` before its target (on the Map: under the target's label block). A flat edge (one
 * layer, a row) runs side to side between the two nodes' rims at `reach(id).side`.
 */
export function edgeRoute(e: LayoutEdge, l: Layout, p: Placed, orientation: Orientation, reach: (id: string) => { out: number; in: number; side: number }, port?: { from: number; to: number }): Pt[] {
  const up = orientation === 'up'
  const at = (id: string): Pt => p.at[id]
  if (e.flat) {
    const a = at(e.from)
    const b = at(e.to)
    const s = Math.sign(up ? b.x - a.x : b.y - a.y) || 1
    return up
      ? [
          { x: a.x + s * reach(e.from).side, y: a.y },
          { x: b.x - s * reach(e.to).side, y: b.y }
        ]
      : [
          { x: a.x, y: a.y + s * reach(e.from).side },
          { x: b.x, y: b.y - s * reach(e.to).side }
        ]
  }
  /** A point d px further along the flow from c (later layers: up on the Map, right on the Path). */
  const along = (c: Pt, d: number): Pt => (up ? { x: c.x, y: c.y - d } : { x: c.x + d, y: c.y })
  const onFlow = (c: Pt, f: number): Pt => (up ? { x: c.x, y: f } : { x: f, y: c.y })
  /** A point moved d px across the flow (an edge's own port on a node shared with other edges). */
  const across = (c: Pt, d: number): Pt => (up ? { x: c.x + d, y: c.y } : { x: c.x, y: c.y + d })
  const pts: Pt[] = []
  const last = e.chain.length - 1
  e.chain.forEach((id, i) => {
    const d = i === 0 ? (port?.from ?? 0) : i === last ? (port?.to ?? 0) : 0
    const c = across(at(id), d)
    const band = p.bands[l.items[id].layer]
    if (i > 0) {
      pts.push(onFlow(c, band.near))
      if (i === last) pts.push(along(c, -reach(id).in))
    }
    if (i < last) {
      // Off center, the edge leaves the node's round rim, not a point above it.
      if (i === 0) pts.push(along(c, Math.sqrt(Math.max(0, reach(id).out ** 2 - d * d))))
      pts.push(onFlow(c, band.far))
    }
  })
  // Drop repeats (a node that fills its band) so no segment has zero length.
  return pts.filter((q, i) => i === 0 || Math.abs(q.x - pts[i - 1].x) + Math.abs(q.y - pts[i - 1].y) > 0.5)
}

/**
 * Each edge's own port at both ends (px across the flow from the node's center), so edges that share a node never
 * share a line: the edges leaving a node fan out over its rim, and those arriving under it spread the same way, each
 * ordered by where its other end lies (so ports never make two edges cross). `room(id)` is how far a port may sit
 * from the center; ports are at most `gap` px apart.
 */
export function edgePorts(l: Layout, p: Placed, orientation: Orientation, room: (id: string) => number, gap = 8): Map<string, { from: number; to: number }> {
  const across = (id: string): number => (orientation === 'up' ? p.at[id].x : p.at[id].y)
  const out = new Map<string, { from: number; to: number }>()
  const key = (e: LayoutEdge): string => `${e.from}>${e.to}`
  for (const e of l.edges) out.set(key(e), { from: 0, to: 0 })
  const spread = (es: LayoutEdge[], id: string, end: 'from' | 'to'): void => {
    if (es.length < 2) return
    const other = (e: LayoutEdge): number => across(end === 'from' ? e.chain[1] : e.chain[e.chain.length - 2])
    const sorted = [...es].sort((a, b) => other(a) - other(b))
    const step = Math.min(gap, (2 * room(id)) / (sorted.length - 1))
    sorted.forEach((e, i) => (out.get(key(e))![end] = (i - (sorted.length - 1) / 2) * step))
  }
  const real = l.edges.filter((e) => !e.flat)
  for (const id of Object.keys(l.items)) {
    if (l.items[id].dummy) continue
    spread(
      real.filter((e) => e.from === id),
      id,
      'from'
    )
    spread(
      real.filter((e) => e.to === id),
      id,
      'to'
    )
  }
  return out
}

/** Points along the curve edgePath draws through `points` (tests: edges against label boxes). */
export function edgeSamples(points: Pt[], orientation: Orientation, per = 16): Pt[] {
  const out: Pt[] = points.length ? [points[0]] : []
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]
    const b = points[i]
    const c1 = orientation === 'right' ? { x: a.x + (b.x - a.x) / 2, y: a.y } : { x: a.x, y: a.y + (b.y - a.y) / 2 }
    const c2 = orientation === 'right' ? { x: b.x - (b.x - a.x) / 2, y: b.y } : { x: b.x, y: b.y - (b.y - a.y) / 2 }
    for (let k = 1; k <= per; k++) {
      const t = k / per
      const u = 1 - t
      out.push({
        x: u * u * u * a.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * b.x,
        y: u * u * u * a.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * b.y
      })
    }
  }
  return out
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
