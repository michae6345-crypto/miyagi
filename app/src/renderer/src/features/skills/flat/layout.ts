/**
 * Feature: skills. The flat (round 3, Notion-style) skill tree's layouts, pure: no React, no DOM.
 *
 *   pathLayout   the goal's path, left to right: a done base track folds into one card ("python 4"), each column is a
 *                prerequisite depth, rows are an even grid (2 in a column of a 3-row grid sit on the outer rows, so the
 *                middle stays free for a straight line), the project card closes the row at the right.
 *   mapLayout    everything, bottom up: the base track at the bottom center, every other track in its own lane next to
 *                what it builds on (goal-path tracks first, then outward), projects on top of what they need. A second
 *                tree (no link to the first) stands to its right.
 *   tracksLayout the Map zoomed out: one card per track, where its lane is, rows by track depth.
 *
 * Edges are hairlines with square turns (elbowH / elbowV, an 8 px rounded corner). Kinds: done (both ends mastered,
 * the only green), open (from mastered to startable), locked.
 */
import type { SkillGraph, SkillGraphNode } from '../model'

export type EdgeKind = 'done' | 'open' | 'locked'
export type Box = { id: string; x: number; y: number; w: number; h: number }
export type FlatEdge = { from: string; to: string; kind: EdgeKind; d: string }
export type TrackLabel = { track: string; text: string; x: number; y: number; align: 'left' | 'right' }
export type Fold = { id: string; track: string; label: string; ids: string[] }
export type FlatLayout = { w: number; h: number; boxes: Box[]; edges: FlatEdge[]; labels: TrackLabel[]; fold?: Fold }

export const CARD_H = 32
export const FOLD_ID = '__fold'
const isDone = (n: SkillGraphNode | undefined): boolean => !!n && n.state === 'mastered'
const startable = (n: SkillGraphNode | undefined): boolean => !!n && (n.state === 'ready' || n.state === 'practicing')

export function edgeKind(a: SkillGraphNode | undefined, b: SkillGraphNode | undefined): EdgeKind {
  if (isDone(a) && isDone(b)) return 'done'
  if (isDone(a) && startable(b)) return 'open'
  return 'locked'
}
export const EDGE_ORDER: Record<EdgeKind, number> = { locked: 0, open: 1, done: 2 }

const r1 = (v: number): number => Math.round(v * 10) / 10

/** Horizontal, then vertical at mx, then horizontal (the Path's edges). */
export function elbowH(x1: number, y1: number, x2: number, y2: number, mx?: number): string {
  if (y1 === y2) return `M${r1(x1)} ${r1(y1)}H${r1(x2)}`
  const m = mx ?? (x1 + x2) / 2
  const r = Math.min(8, Math.abs(y2 - y1) / 2, Math.abs(m - x1), Math.abs(x2 - m))
  const s = y2 > y1 ? 1 : -1
  return `M${r1(x1)} ${r1(y1)}H${r1(m - r)}Q${r1(m)} ${r1(y1)} ${r1(m)} ${r1(y1 + s * r)}V${r1(y2 - s * r)}Q${r1(m)} ${r1(y2)} ${r1(m + r)} ${r1(y2)}H${r1(x2)}`
}

/** Vertical, then horizontal at my, then vertical (the Map's edges, bottom up). */
export function elbowV(x1: number, y1: number, x2: number, y2: number, my?: number): string {
  if (Math.abs(x1 - x2) < 0.5) return `M${r1(x1)} ${r1(y1)}V${r1(y2)}`
  const m = my ?? (y1 + y2) / 2
  const r = Math.min(8, Math.abs(x2 - x1) / 2, Math.abs(m - y1), Math.abs(y2 - m))
  const s = x2 > x1 ? 1 : -1
  const v = y2 > y1 ? 1 : -1
  return `M${r1(x1)} ${r1(y1)}V${r1(m - v * r)}Q${r1(x1)} ${r1(m)} ${r1(x1 + s * r)} ${r1(m)}H${r1(x2 - s * r)}Q${r1(x2)} ${r1(m)} ${r1(x2)} ${r1(m + v * r)}V${r1(y2)}`
}

/** A card's width for its label: 13.5 px text (~7.1 px a character), the 14 px mark, padding and a tail. */
export type Measure = (text: string) => number
export const estimate: Measure = (t) => t.length * 7.6
export function cardWidth(label: string, measure: Measure, tail = 0, min = 0): number {
  return Math.max(min, Math.ceil(10 + 14 + 7 + measure(label) + (tail ? 6 + tail : 0) + 12))
}

/** Longest chain of links into each id (within `ids`). Cycles are cut by a visit guard. */
export function longestDepth(ids: string[], req: (id: string) => string[]): Record<string, number> {
  const set = new Set(ids)
  const memo: Record<string, number> = {}
  const seen = new Set<string>()
  const visit = (id: string): number => {
    if (memo[id] !== undefined) return memo[id]
    if (seen.has(id)) return 0
    seen.add(id)
    const ps = req(id).filter((p) => set.has(p) && p !== id)
    memo[id] = ps.length ? Math.max(...ps.map(visit)) + 1 : 0
    return memo[id]
  }
  for (const id of ids) visit(id)
  return memo
}

// ---- Path ------------------------------------------------------------------------------------------------------

export const PATH = { colGap: 36, rowPitch: 82, top: 44, projW: 176, projH: 148, minGap: 16, maxGap: 72 } as const

/** The path's skills (no goal), and the fold: a fully mastered track that needs nothing from another track. */
export function pathFold(g: SkillGraph): { ids: string[]; fold?: Fold } {
  if (!g.goal) return { ids: [] }
  const ids = g.goal.pathIds.filter((id) => g.byId[id] && g.byId[id].kind === 'skill')
  const byTrack = new Map<string, string[]>()
  for (const id of ids) byTrack.set(g.byId[id].track, [...(byTrack.get(g.byId[id].track) ?? []), id])
  for (const t of g.tracks) {
    const mine = byTrack.get(t.id)
    if (!mine || mine.length < 2) continue
    const done = mine.every((id) => g.byId[id].state === 'mastered')
    const base = mine.every((id) => g.byId[id].requires.every((r) => !g.byId[r] || g.byId[r].track === t.id))
    // Fold only when something else stays on show.
    if (done && base && mine.length < ids.length) {
      const rest = ids.filter((id) => !mine.includes(id))
      return { ids: [FOLD_ID, ...rest], fold: { id: FOLD_ID, track: t.id, label: t.label, ids: mine } }
    }
  }
  return { ids }
}

/**
 * The Path. `width`: the column it fills (gaps grow up to maxGap, then it stays left-aligned at its natural width;
 * below its minimum it reports the larger `w` and the view scales it).
 */
export function pathLayout(g: SkillGraph, width: number, measure: Measure = estimate): FlatLayout {
  const { ids, fold } = pathFold(g)
  if (!g.goal || !ids.length) return { w: width, h: 0, boxes: [], edges: [], labels: [] }
  const folded = new Set(fold?.ids ?? [])
  const mapId = (id: string): string => (folded.has(id) ? FOLD_ID : id)
  const shown = new Set(ids)
  const req = (id: string): string[] => {
    if (id === FOLD_ID) return []
    return [...new Set(g.byId[id].requires.map(mapId).filter((r) => shown.has(r) && r !== id))]
  }
  const depth = longestDepth(ids, req)
  const cols: string[][] = []
  for (const id of ids) (cols[depth[id]] ??= []).push(id)
  const nCols = cols.length
  const most = Math.max(...cols.map((c) => c.length))
  const rows = most % 2 === 0 ? most + 1 : most
  const row: Record<string, number> = {}
  const trackIx = (id: string): number => g.tracks.findIndex((t) => t.id === (id === FOLD_ID ? fold!.track : g.byId[id].track))
  const mid = (rows - 1) / 2
  for (const col of cols) {
    const want = (id: string): number => {
      const ps = req(id)
      return ps.length ? ps.reduce((s, p) => s + row[p], 0) / ps.length : mid
    }
    const sorted = [...col].sort((a, b) => want(a) - want(b) || trackIx(a) - trackIx(b))
    const n = sorted.length
    const step = n > 1 ? Math.max(1, Math.floor((rows - 1) / (n - 1))) : 0
    const center = sorted.reduce((s, id) => s + want(id), 0) / n
    let start = Math.round(center - (step * (n - 1)) / 2)
    start = Math.max(0, Math.min(rows - 1 - step * (n - 1), start))
    sorted.forEach((id, i) => (row[id] = start + i * step))
  }
  const label = (id: string): string => (id === FOLD_ID ? fold!.label : g.byId[id].label)
  const tail = (id: string): number => (id === FOLD_ID ? measure(String(fold!.ids.length)) + 30 : g.byId[id].review ? 12 : 0)
  const colW = cols.map((c) => Math.max(...c.map((id) => cardWidth(label(id), measure, tail(id), 92))))
  const natural = colW.reduce((s, w) => s + w, 0) + PATH.projW
  const gap = Math.max(PATH.minGap, Math.min(PATH.maxGap, (width - natural) / nCols))
  const colX: number[] = []
  let x = 0
  for (let i = 0; i < nCols; i++) {
    colX.push(x)
    x += colW[i] + gap
  }
  const projX = x
  const w = Math.max(width, projX + PATH.projW)
  const Y = (r: number): number => PATH.top + r * PATH.rowPitch
  const midY = Y(mid)
  const boxes: Box[] = ids.map((id) => ({ id, x: colX[depth[id]], y: Y(row[id]) - CARD_H / 2, w: colW[depth[id]], h: CARD_H }))
  const goalBox: Box = { id: g.goal.id, x: projX, y: midY - PATH.projH / 2, w: PATH.projW, h: PATH.projH }
  const at = Object.fromEntries(boxes.map((b) => [b.id, b]))
  const node = (id: string): SkillGraphNode | undefined => (id === FOLD_ID ? ({ state: 'mastered' } as SkillGraphNode) : g.byId[id])
  const edges: FlatEdge[] = []
  for (const id of ids)
    for (const p of req(id)) {
      const a = at[p]
      const b = at[id]
      edges.push({ from: p, to: id, kind: edgeKind(node(p), node(id)), d: elbowH(a.x + a.w, a.y + CARD_H / 2, b.x, b.y + CARD_H / 2, b.x - gap / 2) })
    }
  // The goal's own prerequisites on the path (or the last column) run into the project card.
  const goalReq = new Set(g.byId[g.goal.id]?.requires.map(mapId).filter((r) => shown.has(r)) ?? [])
  const into = goalReq.size ? [...goalReq] : cols[nCols - 1]
  for (const p of into) {
    const a = at[p]
    edges.push({ from: p, to: g.goal.id, kind: edgeKind(node(p), g.byId[g.goal.id]), d: elbowH(a.x + a.w, a.y + CARD_H / 2, projX, midY, projX - gap / 2) })
  }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  // A track's name over its first card (the folded track's card says it already).
  const labels: TrackLabel[] = []
  const named = new Set<string>(fold ? [fold.track] : [])
  for (let c = 0; c < nCols; c++)
    for (const id of [...cols[c]].sort((a, b) => row[a] - row[b])) {
      if (id === FOLD_ID) continue
      const t = g.byId[id].track
      if (named.has(t)) continue
      named.add(t)
      const tr = g.tracks.find((x) => x.id === t)
      labels.push({ track: t, text: tr?.label ?? t, x: at[id].x, y: at[id].y - 24, align: 'left' })
    }
  return { w, h: Math.max(Y(rows - 1) + CARD_H / 2, goalBox.y + goalBox.h) + 8, boxes: [...boxes, goalBox], edges, labels, fold }
}

// ---- Map -------------------------------------------------------------------------------------------------------

export const MAP = { rowPitch: 74, gap: 24, colGap: 36, minCard: 92, projW: 150, projH: 48, goalW: 260, goalH: 76, labelGap: 10, top: 22 } as const

/** A rounded square-turn polyline through `pts` (each turn an 8 px corner, smaller when a leg is short). */
export function orthoPath(pts: Array<[number, number]>): string {
  const p = pts.filter((q, i) => i === 0 || Math.abs(q[0] - pts[i - 1][0]) > 0.5 || Math.abs(q[1] - pts[i - 1][1]) > 0.5)
  if (p.length < 2) return ''
  let d = `M${r1(p[0][0])} ${r1(p[0][1])}`
  for (let i = 1; i < p.length; i++) {
    const [x, y] = p[i]
    if (i === p.length - 1) {
      d += x === p[i - 1][0] ? `V${r1(y)}` : `H${r1(x)}`
      break
    }
    const [px, py] = p[i - 1]
    const [nx, ny] = p[i + 1]
    const r = Math.min(8, Math.hypot(x - px, y - py) / 2, Math.hypot(nx - x, ny - y) / 2)
    const ax = x - Math.sign(x - px) * r
    const ay = y - Math.sign(y - py) * r
    const bx = x + Math.sign(nx - x) * r
    const by = y + Math.sign(ny - y) * r
    d += Math.abs(x - px) < 0.5 ? `V${r1(ay)}` : `H${r1(ax)}`
    d += `Q${r1(x)} ${r1(y)} ${r1(bx)} ${r1(by)}`
  }
  return d
}

/** Does a vertical segment at x from y1 to y2 run through a card (other than `skip`)? */
function hitsV(x: number, y1: number, y2: number, boxes: Box[], skip: Set<string>): boolean {
  const lo = Math.min(y1, y2)
  const hi = Math.max(y1, y2)
  return boxes.some((b) => !skip.has(b.id) && x > b.x - 4 && x < b.x + b.w + 4 && hi > b.y && lo < b.y + b.h)
}

/**
 * A bottom-up edge from `a` (lower) to `b` (higher): up from a's top center, along the shared bus in the gap under b's
 * row, up into b's bottom center. When the straight climb would run through a card, it leaves on the bus over a's own
 * row, climbs in the nearest free gutter between columns, then takes b's bus.
 */
export function routeUp(a: Box, b: Box, boxes: Box[], gutters: number[], halfGap: number): string {
  const xa = a.x + a.w / 2
  const xb = b.x + b.w / 2
  const busB = b.y + b.h + halfGap
  const skip = new Set([a.id, b.id])
  if (!hitsV(xa, a.y, busB, boxes, skip)) return orthoPath([[xa, a.y], [xa, busB], [xb, busB], [xb, b.y + b.h]])
  const busA = a.y - halfGap
  const free = gutters
    .filter((gx) => !hitsV(gx, busA, busB, boxes, skip))
    .sort((p, q) => Math.abs(p - xa) + Math.abs(p - xb) - (Math.abs(q - xa) + Math.abs(q - xb)))
  const gx = free[0] ?? Math.min(...boxes.map((x) => x.x)) - 16
  return orthoPath([[xa, a.y], [xa, busA], [gx, busA], [gx, busB], [xb, busB], [xb, b.y + b.h]])
}

/**
 * The Map's columns: one per track, left to right. The goal's track stands in the middle (over the base track), the
 * tracks it needs flank it, the rest go outward on the side of what they build on.
 */
export type MapPlan = {
  base: string
  order: string[]
  center: string
  row: Record<string, number>
  local: Record<string, number>
  tReq: Map<string, Set<string>>
  level: Record<string, number>
}

export function mapPlan(g: SkillGraph): MapPlan | undefined {
  const skills = g.nodes.filter((n) => n.kind === 'skill').map((n) => n.id)
  if (!skills.length) return undefined
  const trackOf = (id: string): string => g.byId[id].track
  const known = new Set(g.tracks.map((t) => t.id))
  const trackIds = [...new Set([...g.tracks.map((t) => t.id).filter((t) => skills.some((id) => trackOf(id) === t)), ...skills.map(trackOf).filter((t) => !known.has(t))])]
  const tReq = new Map<string, Set<string>>(trackIds.map((t) => [t, new Set()]))
  for (const id of skills)
    for (const r of g.byId[id].requires) {
      const rt = g.byId[r]?.kind === 'skill' ? trackOf(r) : undefined
      if (rt && rt !== trackOf(id)) tReq.get(trackOf(id))!.add(rt)
    }
  const level = longestDepth(trackIds, (t) => [...tReq.get(t)!])
  const count = (t: string): number => skills.filter((id) => trackOf(id) === t).length
  const base = [...trackIds].sort((a, b) => level[a] - level[b] || count(b) - count(a))[0]
  // Rows: a track's cards stack by their depth inside the track, the track starting one row over what it needs.
  const local: Record<string, number> = {}
  for (const t of trackIds) {
    const mine = skills.filter((id) => trackOf(id) === t)
    const d = longestDepth(mine, (id) => g.byId[id].requires.filter((r) => mine.includes(r)))
    for (const id of mine) local[id] = d[id]
  }
  const row: Record<string, number> = {}
  for (const t of [...trackIds].sort((a, b) => level[a] - level[b])) {
    const mine = skills.filter((id) => trackOf(id) === t)
    let s = 0
    for (const id of mine)
      for (const r of g.byId[id].requires) if (row[r] !== undefined && trackOf(r) !== t) s = Math.max(s, row[r] + 1 - local[id])
    for (const id of mine) row[id] = s + local[id]
  }
  // Column order.
  const goalTrack = g.goal && g.byId[g.goal.id] ? g.byId[g.goal.id].requires.map((r) => g.byId[r]).find((n) => n?.kind === 'skill')?.track ?? g.byId[g.goal.id].track : undefined
  const center = goalTrack && goalTrack !== base && tReq.has(goalTrack) ? goalTrack : base
  const left: string[] = []
  const right: string[] = []
  const side: Record<string, number> = { [center]: 0, [base]: 0 }
  const put = (t: string, s: number): void => {
    side[t] = s
    if (s < 0) left.push(t)
    else right.push(t)
  }
  const flank = [...(tReq.get(center) ?? [])].filter((t) => t !== base).sort((a, b) => count(b) - count(a))
  flank.forEach((t, i) => put(t, i % 2 ? 1 : -1))
  const rest = trackIds.filter((t) => side[t] === undefined).sort((a, b) => level[a] - level[b] || trackIds.indexOf(a) - trackIds.indexOf(b))
  for (const t of rest) {
    const sides = [...tReq.get(t)!].map((r) => side[r]).filter((v): v is number => v !== undefined && v !== 0)
    const lean = sides.reduce((s, v) => s + v, 0)
    put(t, lean < 0 ? -1 : lean > 0 ? 1 : left.length <= right.length ? -1 : 1)
  }
  const order = [...[...left].reverse(), ...(center !== base ? [center] : []), ...right]
  // The base sits in the middle; with no goal track over it, it is the middle column itself.
  if (center === base) order.splice(left.length, 0, base)
  return { base, order, center, row, local, tReq, level }
}

/** The Map (Skills zoom): one column per track, bottom up, projects over their column. Coordinates start at 0,0. */
export function mapLayout(g: SkillGraph, measure: Measure = estimate): FlatLayout {
  const plan = mapPlan(g)
  if (!plan) return { w: 0, h: 0, boxes: [], edges: [], labels: [] }
  const { base, order, row } = plan
  const width = (id: string): number => cardWidth(g.byId[id].label, measure, g.byId[id].review ? 12 : 0, MAP.minCard)
  const trackLabel = (t: string): string => g.tracks.find((k) => k.id === t)?.label ?? t
  const labelW = (t: string): number => Math.ceil(trackLabel(t).length * 6.6) + MAP.labelGap
  const skills = g.nodes.filter((n) => n.kind === 'skill').map((n) => n.id)
  const rowsOf = (t: string): Map<number, string[]> => {
    const m = new Map<number, string[]>()
    for (const id of skills) if (g.byId[id].track === t) m.set(row[id], [...(m.get(row[id]) ?? []), id])
    return m
  }
  const span = (list: string[]): number => list.reduce((s, id) => s + width(id), 0) + MAP.gap * (list.length - 1)
  // Each column's extent around its center: the widest row, and the track name left of its bottom card.
  type Col = { t: string; rows: Map<number, string[]>; l: number; r: number; cx: number }
  const col = (t: string): Col => {
    const rows = rowsOf(t)
    const low = Math.min(...rows.keys())
    let l = 0
    let r = 0
    for (const [k, list] of rows) {
      const h = span(list) / 2
      l = Math.max(l, h + (k === low ? labelW(t) : 0))
      r = Math.max(r, h)
    }
    return { t, rows, l, r, cx: 0 }
  }
  const cols = order.map(col)
  let x = 0
  cols.forEach((c, i) => {
    c.cx = i === 0 ? 0 : x + c.l
    x = c.cx + c.r + MAP.colGap
  })
  // The middle column (the goal's track, or the base) at x = 0; the base under it.
  const mid = cols.find((c) => c.t === plan.center)!
  const shift = mid.cx
  for (const c of cols) c.cx -= shift
  const baseCol = cols.find((c) => c.t === base) ?? col(base)
  baseCol.cx = 0
  // The base's wide rows (two cards side by side) push the columns beside them outward.
  const baseLow = Math.min(...baseCol.rows.keys())
  for (const c of [...cols].sort((a, b) => Math.abs(a.cx) - Math.abs(b.cx))) {
    if (c === baseCol || c.t === plan.center) continue
    const s = c.cx < 0 ? -1 : 1
    const low = Math.min(...c.rows.keys())
    let need = 0
    for (const [k, list] of c.rows) {
      const bl = baseCol.rows.get(k)
      if (!bl) continue
      // The gap between the base row's edge and this column's row, on this column's side (labels sit to the left).
      const bh = span(bl) / 2 + (s > 0 ? 0 : k === baseLow ? labelW(base) : 0)
      const ch = span(list) / 2 + (s > 0 && k === low ? labelW(c.t) : 0)
      need = Math.max(need, bh + MAP.colGap + ch - Math.abs(c.cx))
    }
    if (need > 0) for (const o of cols) if (o !== baseCol && o.t !== plan.center && Math.sign(o.cx) === s && Math.abs(o.cx) >= Math.abs(c.cx)) o.cx += s * need
  }
  const all = order.includes(base) ? cols : [...cols, baseCol]
  const x0: Record<string, number> = {}
  for (const c of all)
    for (const list of c.rows.values()) {
      let left = c.cx - span(list) / 2
      for (const id of list) {
        x0[id] = left
        left += width(id) + MAP.gap
      }
    }
  // Projects: the row over the top skill they need, centered over those skills.
  const caps = g.nodes.filter((n) => n.kind === 'capstone')
  const capRow: Record<string, number> = {}
  for (const c of caps) {
    const rs = c.requires.filter((r) => row[r] !== undefined).map((r) => row[r])
    capRow[c.id] = rs.length ? Math.max(...rs) + 1 : 0
  }
  const goalId = g.goal?.id
  const maxRow = Math.max(...skills.map((id) => row[id]), ...Object.values(capRow))
  const goalRow = goalId && capRow[goalId] !== undefined ? capRow[goalId] : undefined
  const extra = goalRow !== undefined ? MAP.goalH - CARD_H : 0
  // Row centers, top down; rows over the goal's give it room (it stands on its row's baseline).
  const Y = (r: number): number => MAP.top + (maxRow - r) * MAP.rowPitch + CARD_H / 2 + (goalRow !== undefined && r <= goalRow ? extra : 0)
  const boxes: Box[] = skills.map((id) => ({ id, x: x0[id], y: Y(row[id]) - CARD_H / 2, w: width(id), h: CARD_H }))
  const at: Record<string, Box> = Object.fromEntries(boxes.map((b) => [b.id, b]))
  for (const c of caps) {
    const goal = c.id === goalId
    const w = goal ? MAP.goalW : MAP.projW
    const h = goal ? MAP.goalH : MAP.projH
    const xs = c.requires.filter((r) => at[r]).map((r) => at[r].x + at[r].w / 2)
    let cx = xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0
    const bottom = Y(capRow[c.id]) + CARD_H / 2
    const hit = (x: number): boolean => boxes.some((b) => x - w / 2 < b.x + b.w + MAP.gap && x + w / 2 > b.x - MAP.gap && bottom - h < b.y + b.h && bottom > b.y)
    for (let k = 0; k < 200 && hit(cx); k++) cx += (k % 2 ? -1 : 1) * Math.ceil(k / 2 + 0.5) * 16
    const b = { id: c.id, x: cx - w / 2, y: bottom - h, w, h }
    boxes.push(b)
    at[c.id] = b
  }
  // Track names left of each column's bottom card.
  const labels: TrackLabel[] = all.map((c) => {
    const low = Math.min(...c.rows.keys())
    const first = c.rows.get(low)![0]
    return { track: c.t, text: trackLabel(c.t), x: at[first].x - MAP.labelGap, y: Y(low) - 8, align: 'right' as const }
  })
  // Everything from x = 0.
  const minX = Math.min(...boxes.map((b) => b.x), ...labels.map((l) => l.x - labelW(l.track)))
  const minY = Math.min(...boxes.map((b) => b.y))
  const dx = 8 - minX
  const dy = MAP.top - minY
  for (const b of boxes) (b.x += dx), (b.y += dy)
  for (const l of labels) (l.x += dx), (l.y += dy)
  // Gutters: halfway between neighbouring columns, and outside the outer ones.
  const sorted = [...all].sort((a, b) => a.cx - b.cx)
  const gutters = [sorted[0].cx - sorted[0].l - MAP.colGap / 2, ...sorted.slice(1).map((c, i) => (sorted[i].cx + sorted[i].r + c.cx - c.l) / 2), sorted[sorted.length - 1].cx + sorted[sorted.length - 1].r + MAP.colGap / 2].map((v) => v + dx)
  const halfGap = (MAP.rowPitch - CARD_H) / 2
  const edges: FlatEdge[] = []
  for (const n of g.nodes) {
    const b = at[n.id]
    if (!b) continue
    for (const r of n.requires) {
      const a = at[r]
      if (!a) continue
      edges.push({ from: r, to: n.id, kind: edgeKind(g.byId[r], n), d: routeUp(a, b, boxes, gutters, halfGap) })
    }
  }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  return { w: Math.max(...boxes.map((b) => b.x + b.w)) + 8, h: Math.max(...boxes.map((b) => b.y + b.h)) + 8, boxes, edges, labels }
}

// ---- Tracks (the Map zoomed out) -------------------------------------------------------------------------------

export const TRACKS = { w: 164, h: 54, rowPitch: 116, gap: 36 } as const

/** One card per track, in the Map's column order: the base at the bottom center, each track a row over what it needs. */
export function tracksLayout(g: SkillGraph): FlatLayout {
  const plan = mapPlan(g)
  if (!plan) return { w: 0, h: 0, boxes: [], edges: [], labels: [] }
  const { order, level, tReq, base, center } = plan
  const ids = [...new Set([base, ...order])].filter((t) => g.tracks.some((k) => k.id === t && k.total > 0))
  const tw = (t: string): number => Math.max(TRACKS.w, Math.ceil((g.tracks.find((k) => k.id === t)?.label ?? t).length * 8 + 80))
  const pitch = Math.max(...ids.map(tw)) + TRACKS.gap
  const mid = order.indexOf(center)
  const cx = (t: string): number => (t === base ? 0 : (order.indexOf(t) - mid) * pitch)
  const rows = Math.max(0, ...ids.map((t) => level[t])) + 1
  const goalId = g.goal?.id
  const hasGoal = !!goalId && !!g.byId[goalId]
  const top = MAP.top + (hasGoal ? MAP.goalH + TRACKS.rowPitch - TRACKS.h : 0)
  const Y = (r: number): number => top + (rows - 1 - r) * TRACKS.rowPitch
  const boxes: Box[] = ids.map((t) => ({ id: `track:${t}`, x: cx(t) - tw(t) / 2, y: Y(level[t]), w: tw(t), h: TRACKS.h }))
  if (hasGoal) {
    const gt = g.byId[goalId!].track
    const x = ids.includes(gt) ? cx(gt) : cx(center)
    boxes.push({ id: goalId!, x: x - MAP.goalW / 2, y: MAP.top, w: MAP.goalW, h: MAP.goalH })
  }
  const minX = Math.min(...boxes.map((b) => b.x)) - 8
  for (const b of boxes) b.x -= minX
  const at = Object.fromEntries(boxes.map((b) => [b.id, b]))
  const lo = Math.min(...ids.map(cx))
  const hi = Math.max(...ids.map(cx))
  const gutters: number[] = []
  for (let v = lo - pitch / 2; v <= hi + pitch / 2 + 1; v += pitch / 2) gutters.push(v - minX)
  const halfGap = (TRACKS.rowPitch - TRACKS.h) / 2
  const tr = (t: string): SkillGraph['tracks'][number] | undefined => g.tracks.find((x) => x.id === t)
  const edges: FlatEdge[] = []
  for (const t of ids)
    for (const r of tReq.get(t) ?? []) {
      const a = at[`track:${r}`]
      const b = at[`track:${t}`]
      if (!a || !b) continue
      const done = (tr(r)?.mastered ?? 0) >= (tr(r)?.total ?? 1)
      edges.push({ from: a.id, to: b.id, kind: done ? 'done' : 'locked', d: routeUp(a, b, boxes, gutters, halfGap) })
    }
  if (hasGoal) {
    const gb = at[goalId!]
    const gt = g.byId[goalId!].track
    const from = at[`track:${gt}`] ?? at[`track:${center}`]
    if (from) edges.push({ from: from.id, to: goalId!, kind: 'locked', d: routeUp(from, gb, boxes, gutters, (from.y - gb.y - gb.h) / 2) })
  }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  return { w: Math.max(...boxes.map((b) => b.x + b.w)) + 8, h: Math.max(...boxes.map((b) => b.y + b.h)) + 8, boxes, edges, labels: [] }
}

// ---- Steps (the Map zoomed in) ---------------------------------------------------------------------------------

export const STEPS = { w: 236, gap: 52, vgap: 24, head: 60, line: 28 } as const

/** The goal's path again, each skill a card listing its steps (`lines(id)` of them), left to right. */
export function stepsLayout(g: SkillGraph, lines: (id: string) => number): FlatLayout {
  const { ids, fold } = pathFold(g)
  const shown = ids.filter((id) => id !== FOLD_ID)
  if (!shown.length) return { w: 0, h: 0, boxes: [], edges: [], labels: [] }
  const folded = new Set(fold?.ids ?? [])
  const set = new Set(shown)
  const req = (id: string): string[] => g.byId[id].requires.filter((r) => set.has(r) && !folded.has(r))
  const depth = longestDepth(shown, req)
  const cols: string[][] = []
  for (const id of shown) (cols[depth[id]] ??= []).push(id)
  const hOf = (id: string): number => STEPS.head + Math.max(1, lines(id)) * STEPS.line
  const colH = cols.map((c) => c.reduce((s, id) => s + hOf(id), 0) + STEPS.vgap * (c.length - 1))
  const H = Math.max(...colH)
  const y: Record<string, number> = {}
  // Each column in the order of what it builds on; two or more spread over the tallest column's height.
  cols.forEach((c, ci) => {
    const want = (id: string): number => {
      const ps = req(id).filter((p) => y[p] !== undefined)
      return ps.length ? ps.reduce((s, p) => s + y[p] + hOf(p) / 2, 0) / ps.length : H / 2
    }
    c.sort((a, b) => want(a) - want(b))
    if (c.length > 1) {
      const room = (H - colH[ci]) / (c.length - 1)
      let top = 0
      for (const id of c) {
        y[id] = top
        top += hOf(id) + STEPS.vgap + room
      }
    } else y[c[0]] = Math.max(0, Math.min(H - hOf(c[0]), want(c[0]) - hOf(c[0]) / 2))
  })
  const boxes: Box[] = shown.map((id) => ({ id, x: depth[id] * (STEPS.w + STEPS.gap), y: y[id], w: STEPS.w, h: hOf(id) }))
  const at = Object.fromEntries(boxes.map((b) => [b.id, b]))
  const edges: FlatEdge[] = []
  for (const id of shown)
    for (const p of req(id)) {
      const a = at[p]
      const b = at[id]
      edges.push({ from: p, to: id, kind: edgeKind(g.byId[p], g.byId[id]), d: elbowH(a.x + a.w, a.y + a.h / 2, b.x, b.y + b.h / 2) })
    }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  return { w: cols.length * (STEPS.w + STEPS.gap) - STEPS.gap, h: H + 8, boxes, edges, labels: [] }
}
