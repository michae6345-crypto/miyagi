/**
 * Feature: skills. What each tree view lays out (layout.ts input) and the sizes it places them with. Pure.
 *
 *   pathInput  the skills on the way to the goal and the goal itself, left to right, the goal alone at the right end
 *   mapInput   every skill and project, bottom to top; with more than one root, a trunk point joins them, so the Map is
 *              always one tree
 *   PLACE      per view: node and hero sizes, label measure and the gap ranges placeGraph stretches to fill the view
 *   nodeBox    a node and its label block as one box (the label rule: centered under the node, the state line under it)
 */
import type { LayoutLink, LayoutNode, Layout, Orientation, Placed, PlaceOptions } from './layout'
import type { SkillGraph } from './model'

export type TreeView = 'path' | 'map'
export const TRUNK = '__trunk'

export type TreeInput = { nodes: LayoutNode[]; links: LayoutLink[]; hero?: string }

function groups(g: SkillGraph): Map<string, number> {
  return new Map(g.tracks.map((t, i) => [t.id, i]))
}

export function pathInput(g: SkillGraph): TreeInput {
  if (!g.goal) return { nodes: [], links: [] }
  const on = new Set([...g.goal.pathIds, g.goal.id])
  const tr = groups(g)
  const nodes: LayoutNode[] = g.nodes
    .filter((n) => on.has(n.id))
    .map((n) => ({ id: n.id, group: tr.get(n.track) ?? 0, last: n.id === g.goal!.id, span: 2 }))
  const links = g.links.filter((l) => l.kind === 'requires' && on.has(l.from) && on.has(l.to)).map((l) => ({ from: l.from, to: l.to }))
  // A path skill with no link into the goal's side still leads to the goal (the capstone requires it).
  const leads = new Set(links.map((l) => l.from))
  for (const id of on) if (id !== g.goal.id && !leads.has(id)) links.push({ from: id, to: g.goal.id })
  return { nodes, links, hero: g.goal.id }
}

export function mapInput(g: SkillGraph): TreeInput {
  const tr = groups(g)
  const hero = g.goal?.id
  const nodes: LayoutNode[] = g.nodes.map((n) => ({ id: n.id, group: tr.get(n.track) ?? 0, span: n.id === hero ? 3 : 2 }))
  const links = g.links.map((l) => ({ from: l.from, to: l.to }))
  const into = new Set(links.map((l) => l.to))
  const roots = nodes.filter((n) => !into.has(n.id))
  if (roots.length > 1) {
    nodes.unshift({ id: TRUNK, group: -1, span: 1 })
    for (const r of roots) links.push({ from: TRUNK, to: r.id })
  }
  return { nodes, links, hero }
}

export type Sizes = {
  orientation: Orientation
  nodeR: number
  heroR: number
  /** The widest a label may be (px); the Map also keeps it inside one slot. */
  labelW: number
  heroLabelW: number
  /** Node edge to the label's top. */
  labelGap: number
  /** The label lines plus the state line. */
  labelH: number
  /** Label lines a name may wrap to. */
  lines: number
  /** The lowest scale the view opens at (below it, it opens on NEXT instead of fitting everything). */
  minScale: number
}

export const SIZES: Record<TreeView, Sizes> = {
  path: { orientation: 'right', nodeR: 22, heroR: 44, labelW: 152, heroLabelW: 184, labelGap: 10, labelH: 48, lines: 2, minScale: 0.74 },
  map: { orientation: 'up', nodeR: 22, heroR: 38, labelW: 140, heroLabelW: 176, labelGap: 8, labelH: 32, lines: 1, minScale: 0.7 }
}

/** The focus ring around NEXT: 3 px out, 2 px wide. */
export const RING_OUT = 5

/** placeGraph's options for a view in a box. */
export const PLACE: Record<TreeView, (box: { w: number; h: number }, l: Layout, input: TreeInput) => PlaceOptions & Sizes> = {
  path: (box, l, input) => {
    const s = SIZES.path
    const heroLayer = input.hero ? l.items[input.hero]?.layer : undefined
    return {
      ...s,
      orientation: 'right',
      box,
      pad: 24,
      flow: [s.labelW + 16, 236],
      // A node, its label and the next one's focus ring, stacked: 2 half slots apart at least.
      half: [Math.ceil((2 * s.nodeR + s.labelGap + s.labelH + 16 + RING_OUT) / 2), 84],
      extent: { before: s.labelW / 2, after: Math.max(s.heroLabelW / 2, s.heroR), across: s.heroR, acrossBefore: s.heroR, acrossAfter: s.heroR + s.labelGap + s.labelH },
      heroExtra: 24,
      heroLayers: heroLayer === undefined ? [] : [heroLayer]
    }
  },
  map: (box, l, input) => {
    const s = SIZES.map
    const heroLayer = input.hero ? l.items[input.hero]?.layer : undefined
    return {
      ...s,
      orientation: 'up',
      box,
      pad: 24,
      flow: [2 * s.nodeR + s.labelGap + s.labelH + 14 + RING_OUT, 136],
      half: [Math.ceil((s.labelW + 12) / 2), 100],
      extent: { before: s.nodeR + s.labelGap + s.labelH, after: s.heroR + RING_OUT, across: s.heroLabelW / 2 },
      heroExtra: 2 * (s.heroR - s.nodeR) + 8,
      heroLayers: heroLayer === undefined ? [] : [heroLayer]
    }
  }
}

/** The label's measure for a node in a placed view. */
export function labelWidth(view: TreeView, hero: boolean, p: Placed): number {
  const s = SIZES[view]
  const w = hero ? s.heroLabelW : s.labelW
  return view === 'map' ? Math.min(w, 2 * p.half - 12) : w
}

/** A node and its label as one box (content px). */
export function nodeBox(view: TreeView, id: string, hero: boolean, p: Placed): { id: string; x: number; y: number; w: number; h: number } {
  const s = SIZES[view]
  const c = p.at[id]
  const r = hero ? s.heroR : s.nodeR
  const lw = labelWidth(view, hero, p)
  const w = Math.max(2 * r, lw)
  return { id, x: c.x - w / 2, y: c.y - r, w, h: 2 * r + s.labelGap + s.labelH }
}
