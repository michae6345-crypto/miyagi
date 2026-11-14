/**
 * kind "graph": the diagram any lesson gets (React, git, pandas, a model...). The engine places nodes on a grid
 * (server/diagrams/layout.py); this maps (col,row) to pixels, per layout family:
 *   flow · data · architecture · tree : layered boxes + arrows. LR: columns sized to their labels, S-curves
 *                                      between them (a one-row chain puts edge labels above the arrows);
 *                                      TB (trees): rows, curves down. Back edges arc around.
 *   sequence : participants on top, lifelines, one arrow per message in `order`, top to bottom
 *   git      : a vertical log (like `git log --graph`): row = commit order (col), lanes = branches (row) as
 *              columns on the left, hash + message + branch tag on the right, so no line crosses a label
 * Emphasis = full white; everything else at label alpha. Groups are a faint cluster with their label.
 * Lines draw in (350 ms, 30 ms stagger). Every label comes from the data. Reference: server/diagrams/render_svg.py.
 */
import { motion } from 'motion/react'
import { useId, useMemo, type ReactNode } from 'react'
import type { GraphDiagramData } from '../../../../../../shared/contracts/events'
import { color, fill, font } from '../../core/theme'

type Node = GraphDiagramData['nodes'][number]
type Edge = GraphDiagramData['edges'][number]

/** Drawable width inside the 640 island (20 px padding each side). */
const W = 600
/** Taller graphs scale down to this. */
const MAX_H = 380
const DRAW = 0.35
const STAGGER = 0.03
/** Mask luminance (not a visible color): white = show. */
const MASK = 'white'
const LABEL = 10.5
const LH = 12.5

// ---------------------------------------------------------------------------------------------- text

let ctx2d: CanvasRenderingContext2D | null | undefined
function textW(s: string, size: number, weight = 400, mono = false): number {
  if (ctx2d === undefined) ctx2d = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d')
  if (!ctx2d) return s.length * size * (mono ? 0.62 : 0.56)
  ctx2d.font = `${weight} ${size}px ${mono ? font.mono : font.ui}`
  return ctx2d.measureText(s).width
}

type Fit = { text: string; size: number; cut: boolean }
/** Shrink from `size` to `min` in half steps until it fits, then cut with an ellipsis. */
function fit(s: string, maxW: number, size: number, min = size, weight = 400, mono = false): Fit {
  for (let z = size; z >= min - 1e-6; z -= 0.5) if (textW(s, z, weight, mono) <= maxW) return { text: s, size: z, cut: false }
  let lo = 0
  let hi = s.length
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (textW(s.slice(0, mid) + '…', min, weight, mono) <= maxW) lo = mid
    else hi = mid - 1
  }
  return { text: s.slice(0, lo).trimEnd() + '…', size: min, cut: true }
}

/** Greedy word wrap into at most `maxLines`; the last line is cut with an ellipsis. */
function wrap(s: string, maxW: number, size: number, maxLines: number): string[] {
  const words = s.split(/\s+/).filter(Boolean)
  let lines: string[] = []
  let cur = ''
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w
    if (!cur || textW(next, size) <= maxW) cur = next
    else {
      lines.push(cur)
      cur = w
    }
  }
  if (cur) lines.push(cur)
  if (lines.length > maxLines) lines = [...lines.slice(0, maxLines - 1), lines.slice(maxLines - 1).join(' ')]
  return lines.map((l) => fit(l, maxW, size).text)
}

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, v))

// --------------------------------------------------------------------------------------------- scene

type BoxText = { label: Fit; detail: string[]; dsize: number }
type CommitText = { hash: Fit; hashX: number; detail?: Fit; detailX: number; tag?: { x: number; w: number; text: string } }
type Box = { n: Node; x: number; y: number; w: number; h: number; hx: number; hy: number; rank: number; kind: 'box' | 'circle' | 'commit'; text?: BoxText; commit?: CommitText }
type Label = { x: number; y: number; lines: string[]; size: number; anchor: 'middle' | 'start'; bg: boolean }
type Line = { key: string; d: string; dashed: boolean; strong: boolean; head?: { x: number; y: number; a: number }; label?: Label; order: number; title: string }
type Group = { id: string; label: string; x: number; y: number; w: number; h: number }
type Scene = { boxes: Box[]; lines: Line[]; groups: Group[]; lifelines: { x: number; y1: number; y2: number }[]; minY: number; maxY: number }

function extents(): { add: (a: number, b: number) => void; get: () => { minY: number; maxY: number } } {
  let lo = Infinity
  let hi = -Infinity
  return {
    add: (a, b) => {
      lo = Math.min(lo, a, b)
      hi = Math.max(hi, a, b)
    },
    get: () => ({ minY: Math.floor((isFinite(lo) ? lo : 0) - 3), maxY: Math.ceil((isFinite(hi) ? hi : 0) + 3) })
  }
}

/** Pull a path's end back from the arrow tip so the line never pokes through the head. */
const back = (x: number, y: number, a: number, by = 4.5): [number, number] => [x - Math.cos(a) * by, y - Math.sin(a) * by]

const edgeTitle = (a: Node, b: Node, e: Edge): string => `${a.label}${a === b ? '' : ` → ${b.label}`}${e.label ? `: ${e.label}` : ''}`

function groupsOf(g: GraphDiagramData): { id: string; label: string }[] {
  const named = new Map((g.groups ?? []).map((x) => [x.id, x.label || x.id]))
  const ids: string[] = []
  for (const n of g.nodes) if (n.group && !ids.includes(n.group)) ids.push(n.group)
  // Clusters only when the engine named them in `groups`.
  return ids.filter((id) => named.has(id)).map((id) => ({ id, label: named.get(id)! }))
}

/** Label (12 semibold, shrinks to 10) and detail (one line, or up to `detailLines` wrapped) inside width w. */
function boxText(n: Node, w: number, detailLines: number): BoxText {
  const pad = n.shape === 'round' ? 16 : 12
  const label = fit(n.label, w - pad, 12, 10, 600)
  if (!n.detail) return { label, detail: [], dsize: LABEL }
  const one = fit(n.detail, w - pad, LABEL, 9.5)
  if (!one.cut || detailLines < 2) return { label, detail: [one.text], dsize: one.size }
  return { label, detail: wrap(n.detail, w - pad, 10, detailLines), dsize: 10 }
}

function boxShape(n: Node, x: number, y: number, w: number, h: number, rank: number, text: BoxText): Box {
  if (n.shape === 'circle') {
    const r = clamp(textW(text.label.text, text.label.size, 600) / 2 + 9, h / 2, Math.min(w / 2, h / 2 + 8))
    return { n, x, y, w: r * 2, h: r * 2, hx: r, hy: r, rank, kind: 'circle', text: { ...text, label: fit(n.label, r * 2 - 8, 12, 10, 600) } }
  }
  return { n, x, y, w, h, hx: w / 2, hy: h / 2, rank, kind: 'box', text }
}

/** Box height for the tallest text block. */
const boxH = (texts: BoxText[]): number => {
  const lines = Math.max(0, ...texts.map((t) => t.detail.length))
  return lines === 0 ? 30 : lines === 1 ? 40 : 52
}

/** flow · data · architecture · tree (and any layered layout), LR or TB. */
function layered(g: GraphDiagramData): Scene {
  const tb = g.direction === 'TB'
  const nodes = g.nodes
  const clusters = groupsOf(g)
  const grouped = clusters.length > 0
  const single = !tb && new Set(nodes.map((n) => n.row)).size <= 1
  const natural = (n: Node): number =>
    clamp(Math.max(textW(n.label, 12, 600), n.detail ? Math.min(textW(n.detail, LABEL), single ? 100 : Infinity) : 0) + 22, 64, 172)
  const boxes: Box[] = []
  let above = false

  if (!tb) {
    const cols = Math.max(g.grid?.cols ?? 1, ...nodes.map((n) => Math.round(n.col) + 1), 1)
    const ci = (n: Node): number => clamp(Math.round(n.col), 0, cols - 1)
    const nat = Array.from({ length: cols }, () => 0)
    for (const n of nodes) nat[ci(n)] = Math.max(nat[ci(n)], natural(n))
    const columns = (minGap: number): { colW: number[]; cx: number[] } => {
      const room = W - minGap * (cols - 1)
      const sum0 = nat.reduce((a, b) => a + b, 0)
      const colW = sum0 > room ? nat.map((w) => (w * room) / sum0) : nat
      const sum = colW.reduce((a, b) => a + b, 0)
      const gap = cols > 1 ? Math.min(grouped ? 96 : 84, (W - sum) / (cols - 1)) : 0
      let x = (W - sum - gap * (cols - 1)) / 2
      const cx = colW.map((w) => {
        const c = x + w / 2
        x += w + gap
        return c
      })
      return { colW, cx }
    }
    let { colW, cx } = columns(grouped ? 48 : 34)
    // A one-row chain with labels too wide for the gaps: labels go above the arrows, gaps shrink to the arrow.
    if (single) {
      const byId = new Map(nodes.map((n) => [n.id, n]))
      above = g.edges.some((e) => {
        const a = byId.get(e.from)
        const b = byId.get(e.to)
        if (!e.label?.trim() || !a || !b) return false
        const room = Math.abs(cx[ci(b)] - cx[ci(a)]) - (colW[ci(a)] + colW[ci(b)]) / 2 - 10
        return textW(e.label.trim(), LABEL) > room
      })
      if (above) ({ colW, cx } = columns(grouped ? 40 : 24))
    }
    const at = (c: number): number => {
      const i = Math.floor(c)
      const f = c - i
      return f && i + 1 < cx.length ? cx[i] + (cx[i + 1] - cx[i]) * f : cx[clamp(Math.round(c), 0, cx.length - 1)]
    }
    const texts = nodes.map((n) => boxText(n, colW[ci(n)], single ? 2 : 1))
    const bh = boxH(texts)
    const rh = bh + (grouped ? 44 : 30)
    nodes.forEach((n, i) => boxes.push(boxShape(n, at(n.col), n.row * rh + bh / 2, colW[ci(n)], bh, ci(n), texts[i])))
  } else {
    const cols = Math.max(g.grid?.cols ?? 1, ...nodes.map((n) => Math.floor(n.col) + 1), 1)
    const cw = W / cols
    const bw = clamp(Math.max(...nodes.map(natural)), 64, Math.min(172, cw - (grouped ? 28 : 16)))
    const texts = nodes.map((n) => boxText(n, bw, 1))
    const bh = boxH(texts)
    const rh = bh + (grouped ? 50 : 40)
    nodes.forEach((n, i) => boxes.push(boxShape(n, cw * (n.col + 0.5), n.row * rh + bh / 2, bw, bh, Math.round(n.row), texts[i])))
  }

  const byId = new Map(boxes.map((b) => [b.n.id, b]))
  const ext = extents()
  for (const b of boxes) ext.add(b.y - b.hy, b.y + b.hy + (b.kind === 'circle' && b.n.detail ? 16 : 0))

  const lines: Line[] = []
  g.edges.forEach((e, i) => {
    const a = byId.get(e.from)
    const b = byId.get(e.to)
    if (!a || !b || a === b) return
    const route = tb ? routeTB(a, b) : routeLR(a, b, above)
    const text = e.label?.trim()
    let label: Label | undefined
    if (text && route.room.w >= 26) {
      const ls = route.room.lines > 1 ? wrap(text, route.room.w, LABEL, route.room.lines) : [fit(text, route.room.w, LABEL, 9.5).text]
      const size = route.room.lines > 1 ? LABEL : fit(text, route.room.w, LABEL, 9.5).size
      const h = ls.length * LH
      // first baseline: centered blocks sit on the line's midpoint, others start at ly
      const top = route.room.center ? route.ly - h / 2 + LH - 3 : route.ly
      label = { x: route.lx, y: top, lines: ls, size, anchor: route.room.anchor, bg: route.room.bg }
      ext.add(top - LH, top + h - LH + 4)
    }
    ext.add(route.minY, route.maxY)
    lines.push({ key: `${e.from}-${e.to}-${i}`, d: route.d, dashed: e.style === 'dashed', strong: !!e.emphasis, head: route.head, label, order: Math.min(a.rank, b.rank) * 4 + i * 0.01, title: edgeTitle(a.n, b.n, e) })
  })
  lines.sort((p, q) => p.order - q.order).forEach((l, i) => (l.order = i))

  const groups: Group[] = []
  for (const c of clusters) {
    const m = boxes.filter((b) => b.n.group === c.id)
    if (!m.length) continue
    const x1 = Math.min(...m.map((b) => b.x - b.hx)) - 10
    const x2 = Math.max(...m.map((b) => b.x + b.hx)) + 10
    const y1 = Math.min(...m.map((b) => b.y - b.hy)) - 24
    const y2 = Math.max(...m.map((b) => b.y + b.hy)) + 10
    groups.push({ id: c.id, label: fit(c.label, x2 - x1 - 20, LABEL).text, x: x1, y: y1, w: x2 - x1, h: y2 - y1 })
    ext.add(y1, y2)
  }
  return { boxes, lines, groups, lifelines: [], ...ext.get() }
}

type Room = { w: number; lines: number; anchor: 'middle' | 'start'; bg: boolean; center: boolean }
type Route = { d: string; head: { x: number; y: number; a: number }; lx: number; ly: number; room: Room; minY: number; maxY: number }

function curve(sx: number, sy: number, ex: number, ey: number, a: number, horizontal: boolean): string {
  const [bx, by] = back(ex, ey, a)
  if (Math.abs(horizontal ? ey - sy : ex - sx) < 0.5) return `M${sx},${sy} L${bx},${by}`
  if (horizontal) {
    const mx = (sx + bx) / 2
    return `M${sx},${sy} C${mx},${sy} ${mx},${by} ${bx},${by}`
  }
  const my = (sy + by) / 2
  return `M${sx},${sy} C${sx},${my} ${bx},${my} ${bx},${by}`
}

function routeLR(a: Box, b: Box, above: boolean): Route {
  if (b.x - b.hx > a.x + a.hx + 4) {
    const sx = a.x + a.hx
    const ex = b.x - b.hx
    const room: Room = above
      ? { w: Math.abs(b.x - a.x) - 12, lines: 1, anchor: 'middle', bg: false, center: false }
      : { w: ex - sx - 8, lines: 3, anchor: 'middle', bg: true, center: true }
    const ly = above ? Math.min(a.y - a.hy, b.y - b.hy) - 8 : (a.y + b.y) / 2
    return { d: curve(sx, a.y, ex, b.y, 0, true), head: { x: ex, y: b.y, a: 0 }, lx: (sx + ex) / 2, ly, room, minY: Math.min(a.y, b.y), maxY: Math.max(a.y, b.y) }
  }
  if (b.x + b.hx < a.x - a.hx - 4) {
    // back edge: arc under both boxes
    const sy = a.y + a.hy
    const ey = b.y + b.hy
    const yb = Math.max(sy, ey) + 34
    const a2 = -Math.PI / 2
    const [bx, by] = back(b.x, ey, a2)
    const midY = (sy + 6 * yb + ey) / 8
    return { d: `M${a.x},${sy} C${a.x},${yb} ${bx},${yb} ${bx},${by}`, head: { x: b.x, y: ey, a: a2 }, lx: (a.x + b.x) / 2, ly: midY + 13, room: { w: Math.abs(a.x - b.x) - 24, lines: 1, anchor: 'middle', bg: false, center: false }, minY: sy, maxY: midY + 2 }
  }
  // same column: straight down / up, label beside the line
  const down = b.y > a.y
  const sy = down ? a.y + a.hy : a.y - a.hy
  const ey = down ? b.y - b.hy : b.y + b.hy
  const a2 = down ? Math.PI / 2 : -Math.PI / 2
  const [bx, by] = back(b.x, ey, a2)
  return { d: `M${a.x},${sy} L${bx},${by}`, head: { x: b.x, y: ey, a: a2 }, lx: a.x + 7, ly: (sy + ey) / 2 + 4, room: { w: Math.max(a.hx, 60), lines: 2, anchor: 'start', bg: false, center: false }, minY: sy, maxY: ey }
}

function routeTB(a: Box, b: Box): Route {
  if (b.y - b.hy > a.y + a.hy + 4) {
    const sy = a.y + a.hy
    const ey = b.y - b.hy
    const a2 = Math.PI / 2
    return { d: curve(a.x, sy, b.x, ey, a2, false), head: { x: b.x, y: ey, a: a2 }, lx: (a.x + b.x) / 2, ly: (sy + ey) / 2, room: { w: Math.max(56, Math.abs(b.x - a.x) + Math.min(a.hx, b.hx) * 1.2), lines: 1, anchor: 'middle', bg: true, center: true }, minY: sy, maxY: ey }
  }
  if (b.y + b.hy < a.y - a.hy - 4) {
    // back edge (child calls up): arc on the right of both boxes
    const sx = a.x + a.hx
    const ex = b.x + b.hx
    const xr = Math.max(sx, ex) + 30
    const a2 = Math.PI
    const [bx, by] = back(ex, b.y, a2)
    const midX = (sx + 6 * xr + ex) / 8
    return { d: `M${sx},${a.y} C${xr},${a.y} ${xr},${by} ${bx},${by}`, head: { x: ex, y: b.y, a: a2 }, lx: midX + 6, ly: (a.y + b.y) / 2 + 4, room: { w: Math.max(40, W - midX - 10), lines: 2, anchor: 'start', bg: false, center: false }, minY: b.y, maxY: a.y }
  }
  // same row: straight across, label above
  const right = b.x > a.x
  const sx = right ? a.x + a.hx : a.x - a.hx
  const ex = right ? b.x - b.hx : b.x + b.hx
  const a2 = right ? 0 : Math.PI
  const [bx, by] = back(ex, b.y, a2)
  return { d: `M${sx},${a.y} L${bx},${by}`, head: { x: ex, y: b.y, a: a2 }, lx: (sx + ex) / 2, ly: a.y - 6, room: { w: Math.abs(ex - sx) - 8, lines: 1, anchor: 'middle', bg: false, center: false }, minY: a.y - 16, maxY: a.y }
}

/** Participants left to right; messages top to bottom by `order`. */
function sequence(g: GraphDiagramData): Scene {
  const nodes = [...g.nodes].sort((p, q) => p.col - q.col)
  const cols = Math.max(g.grid?.cols ?? 1, nodes.length, 1)
  const cw = W / cols
  const widths = nodes.map((n) => clamp(Math.max(textW(n.label, 12, 600), n.detail ? textW(n.detail, LABEL) : 0) + 24, 72, Math.min(172, cw - 16)))
  const texts = nodes.map((n, i) => boxText(n, widths[i], 1))
  const bh = boxH(texts)
  const boxes = nodes.map((n, i) => boxShape(n, cw * ((Number.isFinite(n.col) ? n.col : i) + 0.5), bh / 2, widths[i], bh, 0, texts[i]))
  const byId = new Map(boxes.map((b) => [b.n.id, b]))
  const msgs = g.edges.map((e, i) => ({ e, i, o: e.order ?? i + 1 })).sort((p, q) => p.o - q.o || p.i - q.i)
  const step = 34
  const lines: Line[] = []
  let y = bh + 30
  msgs.forEach(({ e, i }, k) => {
    const a = byId.get(e.from)
    const b = byId.get(e.to)
    if (!a || !b) return
    const text = e.label?.trim()
    const base = { key: `${e.from}-${e.to}-${i}`, dashed: e.style === 'dashed', strong: !!e.emphasis, order: k, title: edgeTitle(a.n, b.n, e) }
    if (a === b) {
      // a call to itself: a small loop to the right, label beside it
      const x = a.x + 3
      const [bx] = back(x, y + 12, Math.PI)
      const f = text ? fit(text, Math.min(cw - 40, W - x - 34), 11, 9.5) : undefined
      lines.push({ ...base, d: `M${x},${y} H${x + 24} V${y + 12} H${bx}`, head: { x, y: y + 12, a: Math.PI }, label: f ? { x: x + 31, y: y + 10, lines: [f.text], size: f.size, anchor: 'start', bg: false } : undefined })
      y += step + 10
      return
    }
    const right = b.x > a.x
    const sx = a.x + (right ? 3 : -3)
    const ex = b.x + (right ? -3 : 3)
    const ang = right ? 0 : Math.PI
    const [bx] = back(ex, y, ang)
    const f = text ? fit(text, Math.abs(ex - sx) - 12, 11, 9.5) : undefined
    lines.push({ ...base, d: `M${sx},${y} L${bx},${y}`, head: { x: ex, y, a: ang }, label: f ? { x: (sx + ex) / 2, y: y - 7, lines: [f.text], size: f.size, anchor: 'middle', bg: false } : undefined })
    y += step
  })
  const end = Math.max(y - step + 18, bh + 30)
  return { boxes, lines, groups: [], lifelines: boxes.map((b) => ({ x: b.x, y1: bh + 1, y2: end })), minY: -3, maxY: end + 3 }
}

/**
 * Git, as a vertical log: one row per commit in order (node.col), one lane per branch (node.row) as a column on
 * the left. Parent → child lines stay in the lanes (they fork into the child's lane right after the parent, or
 * merge in right before the child); dashed edges (rewritten / copied) bend out between lanes and point at the
 * copy from the side. Hash, message and the branch tag (at each lane's newest commit) sit on the right.
 */
function git(g: GraphDiagramData): Scene {
  const nodes = [...g.nodes].sort((p, q) => p.col - q.col)
  const lanes = Math.max(g.grid?.rows ?? 1, ...nodes.map((n) => Math.round(n.row) + 1), 1)
  const named = new Map((g.groups ?? []).map((x) => [x.id, x.label || x.id]))
  const lane = (n: Node): number => clamp(Math.round(n.row), 0, lanes - 1)
  const R = 5.5
  const LANE = 26
  const ROW = 28
  const rowOf = new Map(nodes.map((n, k) => [n.id, k]))
  const tipOf = new Map<number, string>()
  nodes.forEach((n) => tipOf.set(lane(n), n.id))

  // text column: hash | message | tag; then center the whole log in the island
  const hashW = Math.max(...nodes.map((n) => textW(n.label, LABEL, 400, true)))
  const graphW = (lanes - 1) * LANE + R * 2
  const textX = graphW + 16
  const detailX = textX + Math.min(hashW, 80) + 12
  const tagText = (n: Node): string => (tipOf.get(lane(n)) === n.id && n.group ? (named.get(n.group) ?? n.group) : '')
  const rowW = (n: Node): number => {
    const tag = tagText(n)
    return detailX - textX + (n.detail ? textW(n.detail, 12) : 0) + (tag ? textW(tag, LABEL, 400, true) + 24 : 0)
  }
  const contentW = Math.min(W, textX + Math.max(0, ...nodes.map(rowW)))
  const x0 = (W - contentW) / 2 + R
  const laneX = (r: number): number => x0 + r * LANE

  const boxes: Box[] = nodes.map((n, k) => {
    const y = R + 4 + k * ROW
    const tag = tagText(n)
    const tagW = tag ? Math.min(textW(tag, LABEL, 400, true) + 12, 170) : 0
    const room = W - (x0 - R + detailX) - (tag ? tagW + 10 : 0)
    const detail = n.detail ? fit(n.detail, room, 12, 10.5) : undefined
    const dW = detail ? textW(detail.text, detail.size) : 0
    const commit: CommitText = {
      hash: fit(n.label, Math.min(hashW, 80), LABEL, 9, 400, true),
      hashX: x0 - R + textX,
      detail,
      detailX: x0 - R + detailX,
      tag: tag ? { x: x0 - R + detailX + dW + (detail ? 10 : 0), w: tagW, text: fit(tag, tagW - 12, LABEL, 9, 400, true).text } : undefined
    }
    return { n, x: laneX(lane(n)), y, w: R * 2, h: R * 2, hx: R, hy: R, rank: k, kind: 'commit', commit }
  })
  const byId = new Map(boxes.map((b) => [b.n.id, b]))
  const busy = (r: number, k1: number, k2: number): boolean => nodes.some((n, k) => k > k1 && k < k2 && lane(n) === r)

  const lines: Line[] = []
  g.edges.forEach((e, i) => {
    let a = byId.get(e.from)
    let b = byId.get(e.to)
    if (!a || !b || a === b) return
    const base = { key: `${e.from}-${e.to}-${i}`, dashed: e.style === 'dashed', strong: !!e.emphasis, order: 0, title: edgeTitle(a.n, b.n, e) }
    const flip = rowOf.get(a.n.id)! > rowOf.get(b.n.id)!
    if (flip && !base.dashed) [a, b] = [b, a] // parent above child
    const ka = rowOf.get(a.n.id)!
    const kb = rowOf.get(b.n.id)!
    base.order = Math.min(ka, kb) + i * 0.01
    const down = kb > ka ? 1 : -1
    if (base.dashed && a.x !== b.x) {
      // original → copy: leave between the lanes, enter the copy from its side
      const dir = b.x > a.x ? 1 : -1
      const p0x = a.x + dir * R * 0.75
      const p0y = a.y + down * R * 0.75
      const tip = { x: b.x - dir * (R + 1.5), y: b.y, a: dir > 0 ? 0 : Math.PI }
      const [ex, ey] = back(tip.x, tip.y, tip.a)
      const d = `M${p0x},${p0y} C${p0x + dir * LANE * 0.4},${p0y + down * Math.min(24, Math.abs(b.y - a.y) * 0.45)} ${ex - dir * 12},${ey} ${ex},${ey}`
      lines.push({ ...base, d, head: tip })
      return
    }
    if (a.x === b.x) {
      const sy = a.y + down * (R + 2)
      const ey = b.y - down * (R + 2)
      lines.push({ ...base, d: `M${a.x},${sy} L${a.x},${ey}`, head: base.dashed ? { x: b.x, y: b.y - down * (R + 1), a: down > 0 ? Math.PI / 2 : -Math.PI / 2 } : undefined })
      return
    }
    const sy = a.y + R + 1
    const ey = b.y - R - 1
    let d: string
    if (!busy(lane(b.n), ka, kb)) {
      // fork: bend into the child's lane right after the parent, then straight down
      const y1 = a.y + ROW
      d = `M${a.x},${sy} C${a.x},${a.y + ROW * 0.55} ${b.x},${a.y + ROW * 0.45} ${b.x},${Math.min(y1, ey)}${y1 < ey ? ` L${b.x},${ey}` : ''}`
    } else if (!busy(lane(a.n), ka, kb)) {
      // merge: straight down the parent's lane, bend in right before the child
      const y1 = b.y - ROW
      d = `M${a.x},${sy}${y1 > sy ? ` L${a.x},${y1}` : ''} C${a.x},${b.y - ROW * 0.45} ${b.x},${b.y - ROW * 0.55} ${b.x},${ey}`
    } else d = `M${a.x},${sy} C${a.x},${(sy + ey) / 2} ${b.x},${(sy + ey) / 2} ${b.x},${ey}`
    lines.push({ ...base, d })
  })
  lines.sort((p, q) => p.order - q.order).forEach((l, i) => (l.order = i))
  const last = boxes[boxes.length - 1]
  return { boxes, lines, groups: [], lifelines: [], minY: -2, maxY: Math.ceil((last?.y ?? 0) + R + 6) }
}

function build(g: GraphDiagramData): Scene {
  if (g.layout === 'sequence') return sequence(g)
  if (g.layout === 'git') return git(g)
  return layered(g)
}

// -------------------------------------------------------------------------------------------- render

const arrow = (x: number, y: number, a: number, L = 6.5, Wd = 5.5): string => {
  const c = Math.cos(a)
  const s = Math.sin(a)
  const bx = x - c * L
  const by = y - s * L
  return `M${x},${y} L${bx - s * (Wd / 2)},${by + c * (Wd / 2)} L${bx + s * (Wd / 2)},${by - c * (Wd / 2)} Z`
}

const ink = (strong: boolean): string => (strong ? color.text : color.label)

export function Graph({ data }: { data: GraphDiagramData }): ReactNode {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  const scene = useMemo(() => build(data), [data])
  const sig = `${data.layout}|${data.title}|${data.nodes.map((n) => n.id).join(',')}`
  const H = scene.maxY - scene.minY
  const scale = H > MAX_H ? MAX_H / H : 1
  const lineDelay = (l: Line): number => 0.08 + l.order * STAGGER

  return (
    <svg key={sig} width={W * scale} height={H * scale} viewBox={`0 ${scene.minY} ${W} ${H}`} className="mx-auto block overflow-visible" style={{ fontFamily: font.ui }}>
      {scene.groups.map((g) => (
        <motion.g key={`g-${g.id}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
          <rect x={g.x} y={g.y} width={g.w} height={g.h} rx={12} fill={fill.chip} />
          <text x={g.x + 10} y={g.y + 15} fill={color.faint} fontSize={LABEL}>
            {g.label}
          </text>
        </motion.g>
      ))}
      {scene.lifelines.map((l) => (
        <motion.line key={`life-${l.x}`} x1={l.x} x2={l.x} y1={l.y1} y2={l.y2} stroke={fill.track} strokeDasharray="2 4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }} />
      ))}

      {scene.lines.map((l) => {
        const stroke = l.strong ? color.text : color.faint
        const width = l.strong ? 1.6 : 1.25
        const t = { duration: DRAW, delay: lineDelay(l), ease: 'easeOut' as const }
        const mask = `${uid}-${l.key.replace(/[^a-zA-Z0-9-]/g, '')}`
        return (
          <g key={l.key}>
            <title>{l.title}</title>
            {l.dashed ? (
              // pathLength can't animate a dashed stroke: draw a solid mask in instead
              <>
                <mask id={mask} maskUnits="userSpaceOnUse" x={-40} y={scene.minY - 40} width={W + 80} height={H + 80}>
                  <motion.path d={l.d} fill="none" stroke={MASK} strokeWidth={8} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={t} />
                </mask>
                <path d={l.d} fill="none" stroke={stroke} strokeWidth={width} strokeDasharray="4 3" mask={`url(#${mask})`} />
              </>
            ) : (
              <motion.path d={l.d} fill="none" stroke={stroke} strokeWidth={width} initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }} transition={t} />
            )}
            {l.head && <motion.path d={arrow(l.head.x, l.head.y, l.head.a)} fill={stroke} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.12, delay: t.delay + DRAW * 0.85 }} />}
          </g>
        )
      })}

      {scene.lines.map((l) => l.label && <EdgeLabel key={`lab-${l.key}`} l={l.label} strong={l.strong} delay={lineDelay(l) + DRAW * 0.6} />)}

      {scene.boxes.map((b) => (
        <motion.g key={b.n.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2, delay: b.rank * STAGGER }}>
          <title>{b.n.detail ? `${b.n.label} · ${b.n.detail}` : b.n.label}</title>
          {b.kind === 'commit' ? <Commit b={b} /> : <NodeBox b={b} />}
        </motion.g>
      ))}
    </svg>
  )
}

function EdgeLabel({ l, strong, delay }: { l: Label; strong: boolean; delay: number }): ReactNode {
  const w = Math.max(...l.lines.map((s) => textW(s, l.size))) + 8
  const h = l.lines.length * LH + 3
  const x0 = l.anchor === 'middle' ? l.x - w / 2 : l.x - 4
  return (
    <motion.g initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15, delay }}>
      {l.bg && <rect x={x0} y={l.y - LH + 2} width={w} height={h} rx={4} fill={color.island} />}
      {l.lines.map((s, i) => (
        <text key={i} x={l.x} y={l.y + i * LH} textAnchor={l.anchor} fill={strong ? color.text : color.label} fontSize={l.size}>
          {s}
        </text>
      ))}
    </motion.g>
  )
}

function NodeBox({ b }: { b: Box }): ReactNode {
  const { n, x, y } = b
  const t = b.text!
  const strong = !!n.emphasis
  const stroke = ink(strong)
  const sw = strong ? 1.6 : 1.2
  const dfill = strong ? color.label : color.faint
  if (b.kind === 'circle') {
    return (
      <>
        <circle cx={x} cy={y} r={b.hx} fill={color.island} stroke={stroke} strokeWidth={sw} />
        {strong && <circle cx={x} cy={y} r={b.hx} fill={fill.highlight} />}
        <text x={x} y={y + 4} textAnchor="middle" fill={ink(strong)} fontSize={t.label.size} fontWeight={600}>
          {t.label.text}
        </text>
        {n.detail && (
          <text x={x} y={y + b.hy + 13} textAnchor="middle" fill={dfill} fontSize={LABEL}>
            {fit(n.detail, Math.max(b.w, 90), LABEL, 9.5).text}
          </text>
        )}
      </>
    )
  }
  const { w, h } = b
  const data = n.shape === 'data'
  const rx = n.shape === 'round' ? Math.min(h / 2, 20) : data ? 6 : 8
  const dy = data ? 2 : 0
  // label + detail lines, centered as one block
  const block = 12 + t.detail.length * 12.5
  const ly = y - block / 2 + 10 + dy
  return (
    <>
      <rect x={x - w / 2} y={y - h / 2} width={w} height={h} rx={rx} fill={color.island} stroke={stroke} strokeWidth={sw} />
      {strong && <rect x={x - w / 2} y={y - h / 2} width={w} height={h} rx={rx} fill={fill.highlight} />}
      {/* data: a table-like header rule */}
      {data && <line x1={x - w / 2} x2={x + w / 2} y1={y - h / 2 + 6} y2={y - h / 2 + 6} stroke={stroke} strokeWidth={0.8} />}
      <text x={x} y={ly} textAnchor="middle" fill={ink(strong)} fontSize={t.label.size} fontWeight={600}>
        {t.label.text}
      </text>
      {t.detail.map((s, i) => (
        <text key={i} x={x} y={ly + 13.5 + i * 12.5} textAnchor="middle" fill={dfill} fontSize={t.dsize}>
          {s}
        </text>
      ))}
    </>
  )
}

function Commit({ b }: { b: Box }): ReactNode {
  const { n, x, y } = b
  const c = b.commit!
  const strong = !!n.emphasis
  return (
    <>
      <circle cx={x} cy={y} r={b.hx} fill={strong ? color.text : color.island} stroke={ink(strong)} strokeWidth={1.5} />
      <text x={c.hashX} y={y + 3.8} fill={strong ? color.text : color.faint} fontSize={c.hash.size} fontFamily={font.mono}>
        {c.hash.text}
      </text>
      {c.detail && (
        <text x={c.detailX} y={y + 4.2} fill={ink(strong)} fontSize={c.detail.size}>
          {c.detail.text}
        </text>
      )}
      {c.tag && (
        <>
          <rect x={c.tag.x} y={y - 8} width={c.tag.w} height={16} rx={4} fill={fill.chip} stroke={fill.chipBorder} />
          <text x={c.tag.x + 6} y={y + 3.6} fill={color.label} fontSize={LABEL} fontFamily={font.mono}>
            {c.tag.text}
          </text>
        </>
      )}
    </>
  )
}
