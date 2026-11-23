/**
 * Feature: skills. What each tree view lays out (layout.ts input) and the sizes it places them with. Pure.
 *
 *   pathInput  the skills on the way to the goal and the goal itself, left to right, the goal alone at the right end
 *   mapInput   every skill and project, bottom to top, the goal alone at the top; with more than one root, a trunk point
 *              joins them, so the Map is always one tree. A run of one track's skills lies flat as a branch (layout
 *              rows), which keeps the Map short enough for a wide window
 *   labels     each name's line count, measured once (two lines at most; the state line is always one)
 *   geometry   per node: its radius, label block and where edges leave and arrive (`reach`); per layer: its band
 *   PLACE      per view: placeGraph's options (bands, the edge channel and the gap ranges it stretches to fill the view)
 *   nodeBox    a node and its label block as one box (the label rule: centered under the node, the state line under it)
 */
import type { Layout, LayoutLink, LayoutNode, LayoutOptions, Orientation, PlaceOptions, Placed } from './layout'
import type { SkillGraph } from './model'

export type TreeView = 'path' | 'map'
export const TRUNK = '__trunk'

/** Width of a label in px (the browser measures; tests and the first paint estimate). */
export type Measure = (text: string, hero: boolean) => number

/** A rough width for the system font (13 px medium, 14 px semibold for the hero), on the wide side. */
export const estimate: Measure = (text, hero) => text.length * (hero ? 7.9 : 7.2)

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
  map: { orientation: 'up', nodeR: 21, heroR: 36, labelW: 112, heroLabelW: 208, labelGap: 7, heroLabelGap: 10, lines: 2 }
}

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
    options: { rows: true, maxRow: 5, maxDepth: 6 }
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
      roomGap: 16
    }
  },
  map: (box, l, input) => {
    const s = SIZES.map
    return {
      orientation: 'up',
      box,
      pad: 14,
      flow: [0, 150],
      half: [Math.ceil((s.labelW + 14) / 2), 124],
      extent: { before: 0, after: 0, across: s.labelW / 2 + 4 },
      bands: bandsOf('map', input, l),
      channel: 22
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
