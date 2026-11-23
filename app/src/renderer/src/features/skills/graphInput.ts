/**
 * Feature: skills. What each tree view lays out (layout.ts input) and the sizes it places them with. Pure.
 *
 *   pathInput  the skills on the way to the goal and the goal itself, left to right, the goal alone at the right end
 *   mapInput   every skill and project, bottom to top by prerequisite depth, the goal alone at the top over the trunk;
 *              with more than one root, a trunk point joins them, so the Map is always one tree. Each track is one
 *              branch (layout `tracks`: the trunk's track and the goal's on the middle)
 *   labels     each name's line count, measured once (two lines at most; the state line is always one)
 *   geometry   per node: its radius, label block and where edges leave and arrive (`reach`); per layer: its band
 *   PLACE      per view: placeGraph's options (bands, the edge channel and the gap ranges it stretches to fill the view);
 *              the Map never opens below MAP_MIN_SCALE and pans up and down instead
 *   nodeBox    a node and its label block as one box (the label rule: centered under the node, the state line under it)
 *   edges      every edge's points with its own ports (edgePoints); a hidden link's while its node is in focus
 *   headers    the Map's track headers on free spots of the grid (trackHeaders)
 */
import { edgePorts, edgeRoute, edgeSamples, type Layout, type LayoutEdge, type LayoutLink, type LayoutNode, type LayoutOptions, type Orientation, type PlaceOptions, type Placed } from './layout'
import type { SkillGraph } from './model'

export type TreeView = 'path' | 'map'
export const TRUNK = '__trunk'

/** Width of a label in px (the browser measures; tests and the first paint estimate). */
export type Measure = (text: string, hero: boolean) => number

/** A rough width for the system font (13 px medium, 14 px semibold for the hero), on the wide side. */
export const estimate: Measure = (text, hero) => text.length * (hero ? 7.9 : 7.2)
/** The same for the state line (12 px). */
export const estimateState = (text: string): number => text.length * 6.6

/** Does a state line fit under this node, on its plate? */
export function stateFits(view: TreeView, input: TreeInput, id: string, text: string, measure: (t: string) => number = estimateState): boolean {
  return measure(text) <= geom(view, input, id).labelW - 2 * PLATE
}

export type TreeInput = {
  nodes: LayoutNode[]
  links: LayoutLink[]
  hero?: string
  /** Name lines per node (1 or 2). */
  lines: Record<string, number>
  /** Capstones other than the hero (a little larger). */
  caps: Set<string>
  options: LayoutOptions
}

export type Sizes = {
  orientation: Orientation
  nodeR: number
  heroR: number
  /** The widest a label may be (px). */
  labelW: number
  heroLabelW: number
  /** Node edge to the label's top. */
  labelGap: number
  heroLabelGap: number
  /** Label lines a name may wrap to. */
  lines: number
}

export const SIZES: Record<TreeView, Sizes> = {
  path: { orientation: 'right', nodeR: 22, heroR: 44, labelW: 104, heroLabelW: 156, labelGap: 10, heroLabelGap: 12, lines: 2 },
  // The Map's label takes its whole column (130 px at the tightest) less a 10 px gap.
  map: { orientation: 'up', nodeR: 22, heroR: 40, labelW: 120, heroLabelW: 208, labelGap: 8, heroLabelGap: 10, lines: 2 }
}

/** The Map never opens smaller than this (44 px nodes stay 38 px; labels stay 11 px and up). */
export const MAP_MIN_SCALE = 0.86

/** A name line and the state line (px), and the 1 px between them. */
export const LINE = 16
export const HERO_LINE = 18
export const STATE_LINE = 15
/** The focus ring around NEXT: 3 px out, 2 px wide. */
export const RING_OUT = 5
/** Plate padding each side of a label line (SkillNode). */
const PLATE = 4

/** Lines a name wraps to in `w` px (greedy, by words), at most `max`. */
export function labelLines(text: string, w: number, hero: boolean, measure: Measure, max: number): number {
  const words = text.split(/\s+/).filter(Boolean)
  const room = w - 2 * PLATE
  let lines = 1
  let cur = 0
  const space = measure(' ', hero)
  for (const word of words) {
    const ww = measure(word, hero)
    if (cur && cur + space + ww > room) {
      lines++
      cur = ww
    } else cur += (cur ? space : 0) + ww
  }
  return Math.min(max, lines)
}

function groups(g: SkillGraph): Map<string, number> {
  return new Map(g.tracks.map((t, i) => [t.id, i]))
}

function linesFor(g: SkillGraph, ids: Iterable<string>, view: TreeView, hero: string | undefined, measure: Measure): Record<string, number> {
  const s = SIZES[view]
  const out: Record<string, number> = {}
  for (const id of ids) {
    const n = g.byId[id]
    if (!n) continue
    const h = id === hero
    out[id] = labelLines(n.label, h ? s.heroLabelW : s.labelW, h, measure, s.lines)
  }
  return out
}

export function pathInput(g: SkillGraph, measure: Measure = estimate): TreeInput {
  if (!g.goal) return { nodes: [], links: [], lines: {}, caps: new Set(), options: {} }
  const on = new Set([...g.goal.pathIds, g.goal.id])
  const tr = groups(g)
  const nodes: LayoutNode[] = g.nodes
    .filter((n) => on.has(n.id))
    .map((n) => ({ id: n.id, group: tr.get(n.track) ?? 0, last: n.id === g.goal!.id, span: 2 }))
  const links = g.links.filter((l) => l.kind === 'requires' && on.has(l.from) && on.has(l.to)).map((l) => ({ from: l.from, to: l.to }))
  // A path skill with no link into the goal's side still leads to the goal (the capstone requires it).
  const leads = new Set(links.map((l) => l.from))
  for (const id of on) if (id !== g.goal.id && !leads.has(id)) links.push({ from: id, to: g.goal.id })
  const caps = new Set(nodes.filter((n) => g.byId[n.id]?.kind === 'capstone' && n.id !== g.goal!.id).map((n) => n.id))
  return { nodes, links, hero: g.goal.id, lines: linesFor(g, on, 'path', g.goal.id, measure), caps, options: {} }
}

export function mapInput(g: SkillGraph, measure: Measure = estimate): TreeInput {
  const tr = groups(g)
  const hero = g.goal?.id
  const nodes: LayoutNode[] = g.nodes.map((n) => ({ id: n.id, group: tr.get(n.track) ?? 0, span: n.id === hero ? 3 : 2, last: n.id === hero }))
  const links = g.links.map((l) => ({ from: l.from, to: l.to }))
  const into = new Set(links.map((l) => l.to))
  const roots = nodes.filter((n) => !into.has(n.id))
  // The trunk's track: the one root's (with several roots a trunk point joins them and no track is the trunk).
  const center = roots.length === 1 ? roots[0].group : undefined
  if (roots.length > 1) {
    nodes.unshift({ id: TRUNK, group: -1, span: 1 })
    for (const r of roots) links.push({ from: TRUNK, to: r.id })
  }
  const caps = new Set(g.nodes.filter((n) => n.kind === 'capstone' && n.id !== hero).map((n) => n.id))
  return {
    nodes,
    links,
    hero,
    lines: linesFor(
      g,
      g.nodes.map((n) => n.id),
      'map',
      hero,
      measure
    ),
    caps,
    options: { tracks: { center, crown: hero ? tr.get(g.byId[hero]?.track ?? '') : undefined } }
  }
}

/** One node's geometry in a view (content px). */
export type Geom = { r: number; labelW: number; lines: number; labelGap: number; lineH: number; block: number; hero: boolean }

export function geom(view: TreeView, input: TreeInput, id: string): Geom {
  const s = SIZES[view]
  if (id === TRUNK) return { r: 5, labelW: 0, lines: 0, labelGap: 0, lineH: 0, block: 0, hero: false }
  const hero = id === input.hero
  const r = hero ? s.heroR : input.caps.has(id) ? s.nodeR + 2 : s.nodeR
  const lines = input.lines[id] ?? s.lines
  const lineH = hero ? HERO_LINE : LINE
  const labelGap = hero ? s.heroLabelGap : s.labelGap
  return { r, labelW: hero ? s.heroLabelW : s.labelW, lines, labelGap, lineH, block: labelGap + lines * lineH + 1 + STATE_LINE, hero }
}

/** Where an edge leaves (`out`, along the flow) and arrives (`in`, back along it), and a flat edge's rim (`side`). */
export function reach(view: TreeView, input: TreeInput, id: string): { out: number; in: number; side: number } {
  const g = geom(view, input, id)
  if (view === 'map') return { out: g.r, in: g.r + g.block + 2, side: g.r }
  return { out: g.r, in: g.r, side: g.r }
}

/**
 * Each layer's band: what its nodes (and on the Map their labels, which hang along the flow) reach before and after
 * their centers. Edges run straight through it. On the Path labels hang across the flow, under their nodes, so an edge
 * at the node's height never meets one: the band is the node; `room` keeps the labels of two layers apart.
 */
export function bandsOf(view: TreeView, input: TreeInput, l: Layout, part: 'band' | 'room' = 'band'): Array<{ before: number; after: number }> {
  return l.layers.map((row) => {
    let before = 0
    let after = 0
    for (const id of row) {
      if (l.items[id].dummy) continue
      const g = geom(view, input, id)
      if (view === 'map') {
        // Up: the label block hangs below (before), the node and its ring reach above (after).
        before = Math.max(before, g.r + g.block + 2)
        after = Math.max(after, g.r + RING_OUT)
      } else {
        const w = part === 'room' ? Math.max(g.labelW / 2, g.r + RING_OUT) : g.r + RING_OUT
        before = Math.max(before, w)
        after = Math.max(after, w)
      }
    }
    return { before, after }
  })
}

/** placeGraph's options for a view in a box. */
export const PLACE: Record<TreeView, (box: { w: number; h: number }, l: Layout, input: TreeInput) => PlaceOptions> = {
  path: (box, l, input) => {
    const s = SIZES.path
    const hero = input.hero ? geom('path', input, input.hero) : geom('path', input, '')
    const node = { r: s.nodeR, block: s.labelGap + 2 * LINE + 1 + STATE_LINE }
    return {
      orientation: 'right',
      box,
      pad: 16,
      flow: [0, 236],
      // A node, its label and the next one's focus ring, stacked: 2 half slots apart at least.
      half: [Math.ceil((2 * node.r + node.block + 12 + RING_OUT) / 2), 104],
      extent: { before: s.labelW / 2, after: s.heroLabelW / 2, across: hero.r, acrossBefore: Math.max(hero.r, node.r) + RING_OUT, acrossAfter: Math.max(hero.r + hero.block, node.r + node.block) },
      bands: bandsOf('path', input, l),
      channel: 24,
      room: bandsOf('path', input, l, 'room'),
      roomGap: 16,
      widenFrom: 0
    }
  },
  map: (box, l, input) => {
    const s = SIZES.map
    return {
      orientation: 'up',
      box,
      pad: 14,
      flow: [0, 150],
      // Columns a label and a 10 px gap apart, at most a little more: a compact tree, centered, never stretched thin.
      half: [Math.ceil((s.labelW + 10) / 2), Math.ceil((s.labelW + 36) / 2)],
      extent: { before: 0, after: 0, across: s.labelW / 2 + 4 },
      bands: bandsOf('map', input, l),
      channel: 36,
      minScale: MAP_MIN_SCALE
    }
  }
}

/** A node and its label as one box (content px). */
export function nodeBox(view: TreeView, input: TreeInput, id: string, p: Placed): { id: string; x: number; y: number; w: number; h: number } {
  const c = p.at[id]
  const g = geom(view, input, id)
  const w = Math.max(2 * g.r, g.labelW)
  return { id, x: c.x - w / 2, y: c.y - g.r, w, h: 2 * g.r + g.block }
}

type Pt = { x: number; y: number }

/**
 * Every drawn edge's points (content px), keyed `from>to`: its own ports at both ends (edgePorts), so no two edges share
 * a line; on the Map an edge leaves a node's rim and arrives under the label block of what it opens.
 */
export function edgePoints(view: TreeView, input: TreeInput, l: Layout, p: Placed): Map<string, Pt[]> {
  const o = SIZES[view].orientation
  // Ports spread over the node's rim (leaving) and under its name (arriving): within the smaller of the two.
  const ports = edgePorts(l, p, o, (id) => Math.max(2, geom(view, input, id).r * 0.6), 8)
  const out = new Map<string, Pt[]>()
  for (const e of l.edges) out.set(`${e.from}>${e.to}`, edgeRoute(e, l, p, o, (id) => reach(view, input, id), ports.get(`${e.from}>${e.to}`)))
  return out
}

/** A hidden link's points while its node is in focus (no ports: it is drawn alone over the rest). */
export function hiddenPoints(view: TreeView, input: TreeInput, l: Layout, p: Placed, link: LayoutLink): Pt[] {
  const a = l.items[link.from]
  const b = l.items[link.to]
  if (!a || !b) return []
  const e: LayoutEdge = { from: link.from, to: link.to, chain: [link.from, link.to] }
  return a.layer < b.layer ? edgeRoute(e, l, p, SIZES[view].orientation, (id) => reach(view, input, id)) : [p.at[link.from], p.at[link.to]]
}

/** A track's header on the Map: small caps, in content px (its box's top left); a long name may take two lines. */
export type TrackHeader = { track: string; text: string; lines: string[]; x: number; y: number; w: number; h: number }
export const HEADER_H = 14
/** The header's width: 12 px caps with 0.06 em tracking (the estimate runs wide). */
export const headerWidth = (text: string): number => Math.ceil(text.length * 8.2)

/**
 * One header per track branch on the Map, on a free spot of the grid: above the branch's highest skill (a column
 * header), else beside its lowest one past its label column (outward from the trunk first), else above or beside any of
 * its skills; a two-word name that fits nowhere on one line tries the same spots on two. Free means clear of every node, every label block, every edge (4 px) and the other
 * headers, inside the content. A track with no free spot shows none (its name is still in each skill's panel). Pure.
 */
export function trackHeaders(
  tracks: Array<{ id: string; label: string }>,
  trackOf: (id: string) => string | undefined,
  input: TreeInput,
  l: Layout,
  p: Placed,
  edges: Pt[][],
  width: (text: string) => number = headerWidth
): TrackHeader[] {
  const view: TreeView = 'map'
  const boxes: Array<{ x: number; y: number; w: number; h: number }> = []
  for (const n of input.nodes) {
    const c = p.at[n.id]
    if (!c) continue
    const g = geom(view, input, n.id)
    // The node with its ring and its label column, top to bottom: a header beside a node never reads as its name.
    const w = Math.max(2 * (g.r + RING_OUT), g.labelW)
    boxes.push({ x: c.x - w / 2, y: c.y - g.r - RING_OUT, w, h: g.r + RING_OUT + g.r + g.block + 2 })
  }
  const samples = edges.flatMap((pts) => edgeSamples(pts, 'up', 24))
  const PAD = 4
  const free = (b: { x: number; y: number; w: number; h: number }): boolean => {
    if (b.x < 0 || b.x + b.w > p.w || b.y < 0 || b.y + b.h > p.h) return false
    const hit = (o: { x: number; y: number; w: number; h: number }): boolean => b.x < o.x + o.w + PAD && o.x < b.x + b.w + PAD && b.y < o.y + o.h + PAD && o.y < b.y + b.h + PAD
    if (boxes.some(hit)) return false
    return !samples.some((q) => q.x > b.x - PAD && q.x < b.x + b.w + PAD && q.y > b.y - PAD && q.y < b.y + b.h + PAD)
  }
  const out: TrackHeader[] = []
  const middle = p.w / 2
  for (const t of tracks) {
    const ids = input.nodes.map((n) => n.id).filter((id) => id !== input.hero && trackOf(id) === t.id && p.at[id])
    if (!ids.length) continue
    const text = t.label.toUpperCase()
    const byLayer = [...ids].sort((a, b) => l.items[a].layer - l.items[b].layer || p.at[a].x - p.at[b].x)
    const base = byLayer[0]
    const top = byLayer[byLayer.length - 1]
    const outward = (id: string): 1 | -1 => (p.at[id].x < middle ? -1 : 1)
    const words = text.split(' ')
    const split = words.length > 1 ? [words.slice(0, Math.ceil(words.length / 2)).join(' '), words.slice(Math.ceil(words.length / 2)).join(' ')] : undefined
    const spots = (lines: string[]): Array<{ x: number; y: number; w: number; h: number }> => {
      const w = Math.max(...lines.map(width))
      const h = lines.length * HEADER_H
      const beside = (id: string, side: 1 | -1): { x: number; y: number; w: number; h: number } => {
        const c = p.at[id]
        const gm = geom(view, input, id)
        const half = Math.max(gm.r + RING_OUT, gm.labelW / 2) + 6
        return { x: side > 0 ? c.x + half : c.x - half - w, y: c.y - h / 2, w, h }
      }
      /** Over the node: centered, or to one side of the edges that leave its top. */
      const above = (id: string, side: -1 | 0 | 1 = 0): { x: number; y: number; w: number; h: number } => {
        const c = p.at[id]
        const r = geom(view, input, id).r
        return { x: side === 0 ? c.x - w / 2 : side > 0 ? c.x + 12 : c.x - 12 - w, y: c.y - r - RING_OUT - 8 - h, w, h }
      }
      const both = (id: string): Array<{ x: number; y: number; w: number; h: number }> => [beside(id, outward(id)), beside(id, (-outward(id)) as 1 | -1)]
      return [
        above(top),
        ...both(base),
        ...[...byLayer].reverse().flatMap((id) => [above(id), ...both(id)]),
        ...[...byLayer].reverse().flatMap((id) => [above(id, outward(id)), above(id, (-outward(id)) as 1 | -1)])
      ]
    }
    let lines = [text]
    let spot = spots(lines).find(free)
    if (!spot && split) {
      lines = split
      spot = spots(lines).find(free)
    }
    if (!spot) continue
    out.push({ track: t.id, text, lines, ...spot })
    boxes.push(spot)
  }
  return out
}
