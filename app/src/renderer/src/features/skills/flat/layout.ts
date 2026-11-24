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

export const MAP = { rowPitch: 74, gap: 30, laneGap: 24, minCard: 120, projW: 150, projH: 48, goalW: 260, goalH: 76, labelGap: 10, top: 22 } as const

type Lane = { track: string; x: number; rows: Map<number, string[]> }

/** Connected parts of the skill graph (requires links), the goal's first, then by size. */
function components(g: SkillGraph, ids: string[]): string[][] {
  const adj = new Map<string, Set<string>>(ids.map((id) => [id, new Set()]))
  for (const id of ids)
    for (const r of g.byId[id].requires)
      if (adj.has(r)) {
        adj.get(id)!.add(r)
        adj.get(r)!.add(id)
      }
  const seen = new Set<string>()
  const parts: string[][] = []
  for (const id of ids) {
    if (seen.has(id)) continue
    const part: string[] = []
    const stack = [id]
    seen.add(id)
    while (stack.length) {
      const cur = stack.pop()!
      part.push(cur)
      for (const n of adj.get(cur)!) if (!seen.has(n)) (seen.add(n), stack.push(n))
    }
    parts.push(ids.filter((x) => part.includes(x)))
  }
  const goalPath = new Set(g.goal?.pathIds ?? [])
  return parts.sort((a, b) => Number(b.some((id) => goalPath.has(id))) - Number(a.some((id) => goalPath.has(id))) || b.length - a.length)
}

type Part = { boxes: Box[]; minX: number; maxX: number; rows: number; lanes: Lane[]; labels: TrackLabel[] }

/** One connected tree, centered on x = 0, row 0 at the bottom. Boxes' y is the row (converted later). */
function placePart(g: SkillGraph, ids: string[], width: (id: string) => number): Part {
  const req = (id: string): string[] => g.byId[id].requires.filter((r) => ids.includes(r))
  const depth = longestDepth(ids, req)
  const trackOf = (id: string): string => g.byId[id].track
  const trackIds = [...new Set(ids.map(trackOf))]
  // The base: the track holding the lowest skills (the most of them on a tie).
  const minD = (t: string): number => Math.min(...ids.filter((id) => trackOf(id) === t).map((id) => depth[id]))
  const base = [...trackIds].sort((a, b) => minD(a) - minD(b) || ids.filter((id) => trackOf(id) === b).length - ids.filter((id) => trackOf(id) === a).length)[0]
  const x: Record<string, number> = {}
  // A track's name sits left of its lowest card: its lane keeps that room.
  const labelW = (t: string): number => Math.ceil((g.tracks.find((k) => k.id === t)?.label ?? t).length * 6.6) + MAP.labelGap
  // Per row occupied intervals, to keep lanes apart.
  const occ = new Map<number, Array<[number, number]>>()
  const take = (r: number, a: number, b: number): void => void occ.set(r, [...(occ.get(r) ?? []), [a, b]])
  const free = (r: number, a: number, b: number): boolean => (occ.get(r) ?? []).every(([p, q]) => b + MAP.laneGap <= p || a >= q + MAP.laneGap)
  const spread = (r: number, list: string[], cx: number): void => {
    const total = list.reduce((s, id) => s + width(id), 0) + MAP.gap * (list.length - 1)
    let left = cx - total / 2
    for (const id of list) {
      x[id] = left + width(id) / 2
      left += width(id) + MAP.gap
    }
  }
  const want = (id: string): number | undefined => {
    const ps = req(id).filter((p) => x[p] !== undefined)
    return ps.length ? ps.reduce((s, p) => s + x[p], 0) / ps.length : undefined
  }
  const order = (list: string[]): string[] => [...list].sort((a, b) => (want(a) ?? 0) - (want(b) ?? 0) || ids.indexOf(a) - ids.indexOf(b))
  // The base track: each row spread around the center, in prerequisite order.
  const baseRows = new Map<number, string[]>()
  for (const id of ids) if (trackOf(id) === base) baseRows.set(depth[id], [...(baseRows.get(depth[id]) ?? []), id])
  const lanes: Lane[] = []
  for (const r of [...baseRows.keys()].sort((a, b) => a - b)) {
    const list = order(baseRows.get(r)!)
    const span = list.reduce((s, id) => s + width(id), 0) + MAP.gap * (list.length - 1)
    // Wide base rows keep an even pitch, so the lanes above them line up with their cards.
    spread(r, list, 0)
    take(r, -span / 2 - (r === Math.min(...baseRows.keys()) ? labelW(base) : 0), span / 2)
  }
  lanes.push({ track: base, x: 0, rows: baseRows })
  // Every other track: one lane each, as near what it builds on as it fits. Goal-path tracks first, then low ones.
  const goalPath = new Set(g.goal?.pathIds ?? [])
  const goalTrack = g.goal ? g.byId[g.goal.id]?.track : undefined
  const others = trackIds
    .filter((t) => t !== base)
    .sort((a, b) => {
      const pa = ids.some((id) => trackOf(id) === a && goalPath.has(id)) ? 0 : 1
      const pb = ids.some((id) => trackOf(id) === b && goalPath.has(id)) ? 0 : 1
      const ga = a === goalTrack ? 1 : 0
      const gb = b === goalTrack ? 1 : 0
      return ga - gb || minD(a) - minD(b) || pa - pb || g.tracks.findIndex((t) => t.id === a) - g.tracks.findIndex((t) => t.id === b)
    })
  for (const t of others) {
    const mine = ids.filter((id) => trackOf(id) === t)
    const rows = new Map<number, string[]>()
    for (const id of mine) rows.set(depth[id], [...(rows.get(depth[id]) ?? []), id])
    const pulls = mine.map(want).filter((v): v is number => v !== undefined)
    const desired = pulls.length ? pulls.reduce((s, v) => s + v, 0) / pulls.length : 0
    const half = (r: number): number => (rows.get(r)!.reduce((s, id) => s + width(id), 0) + MAP.gap * (rows.get(r)!.length - 1)) / 2
    const low = Math.min(...rows.keys())
    const lab = (r: number): number => (r === low ? labelW(t) : 0)
    const fits = (cx: number): boolean => [...rows.keys()].every((r) => free(r, cx - half(r) - lab(r), cx + half(r)))
    // Step out from the wanted spot, away from the center first.
    const dir = desired < 0 ? -1 : 1
    let cx = desired
    for (let k = 0; k < 400; k++) {
      const off = Math.ceil(k / 2) * 8 * (k % 2 ? dir : -dir)
      if (fits(desired + off)) {
        cx = desired + off
        break
      }
    }
    for (const r of rows.keys()) {
      spread(r, order(rows.get(r)!), cx)
      take(r, cx - half(r) - lab(r), cx + half(r))
    }
    lanes.push({ track: t, x: cx, rows })
  }
  const boxes: Box[] = ids.map((id) => ({ id, x: x[id] - width(id) / 2, y: depth[id], w: width(id), h: CARD_H }))
  const minX = Math.min(...boxes.map((b) => b.x))
  const maxX = Math.max(...boxes.map((b) => b.x + b.w))
  const rowsN = Math.max(...ids.map((id) => depth[id])) + 1
  // A track's name to the left of its lowest card.
  const labels: TrackLabel[] = lanes.map((l) => {
    const r = Math.min(...l.rows.keys())
    const first = l.rows.get(r)!.reduce((a, b) => (x[a] < x[b] ? a : b))
    const tr = g.tracks.find((t) => t.id === l.track)
    return { track: l.track, text: tr?.label ?? l.track, x: x[first] - width(first) / 2 - MAP.labelGap, y: r, align: 'right' as const }
  })
  return { boxes, minX, maxX, rows: rowsN, lanes, labels }
}

/** The Map (Skills zoom). Coordinates start at 0,0; the view scales the whole to fit. */
export function mapLayout(g: SkillGraph, measure: Measure = estimate): FlatLayout {
  const skills = g.nodes.filter((n) => n.kind === 'skill').map((n) => n.id)
  if (!skills.length) return { w: 0, h: 0, boxes: [], edges: [], labels: [] }
  const width = (id: string): number => cardWidth(g.byId[id].label, measure, g.byId[id].review ? 12 : 0, MAP.minCard)
  const parts = components(g, skills).map((ids) => placePart(g, ids, width))
  const rows = Math.max(...parts.map((p) => p.rows))
  // Projects: a row above the top skill they need.
  const caps = g.nodes.filter((n) => n.kind === 'capstone')
  const capRow: Record<string, number> = {}
  const rowOf: Record<string, number> = {}
  for (const p of parts) for (const b of p.boxes) rowOf[b.id] = b.y
  for (const c of caps) {
    const rs = c.requires.filter((r) => rowOf[r] !== undefined).map((r) => rowOf[r])
    capRow[c.id] = rs.length ? Math.max(...rs) + 1 : rows
  }
  const top = Math.max(rows, ...Object.values(capRow).map((r) => r + 1))
  const goalId = g.goal?.id
  const extraTop = goalId && caps.some((c) => c.id === goalId) ? (MAP.goalH - CARD_H) / 2 + 8 : 0
  const Y = (r: number): number => MAP.top + extraTop + (top - 1 - r) * MAP.rowPitch + CARD_H / 2
  // Parts side by side, 80 apart.
  const boxes: Box[] = []
  const labels: TrackLabel[] = []
  let off = 0
  const shift: number[] = []
  parts.forEach((p, i) => {
    const dx = i === 0 ? 0 : off - p.minX + 80
    shift.push(dx)
    off = (i === 0 ? p.maxX : off + 80 + (p.maxX - p.minX))
    for (const b of p.boxes) boxes.push({ ...b, x: b.x + dx, y: Y(b.y) - CARD_H / 2 })
    for (const l of p.labels) labels.push({ ...l, x: l.x + dx, y: Y(l.y) - 8 })
  })
  const at: Record<string, Box> = Object.fromEntries(boxes.map((b) => [b.id, b]))
  // Place each project over its prerequisites' middle, clear of other projects on its row.
  const capBoxes: Box[] = []
  for (const c of caps) {
    const goal = c.id === goalId
    const w = goal ? MAP.goalW : MAP.projW
    const h = goal ? MAP.goalH : MAP.projH
    const xs = c.requires.filter((r) => at[r]).map((r) => at[r].x + at[r].w / 2)
    let cx = xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0
    const cy = Y(capRow[c.id])
    const hit = (x: number): boolean =>
      [...capBoxes, ...boxes].some((b) => x - w / 2 < b.x + b.w + MAP.laneGap && x + w / 2 > b.x - MAP.laneGap && cy - h / 2 < b.y + b.h && cy + h / 2 > b.y)
    for (let k = 0; k < 200 && hit(cx); k++) cx += (k % 2 ? -1 : 1) * Math.ceil(k / 2 + 0.5) * 16
    capBoxes.push({ id: c.id, x: cx - w / 2, y: cy - h / 2, w, h })
  }
  const all = [...boxes, ...capBoxes]
  const minX = Math.min(...all.map((b) => b.x), ...labels.map((l) => l.x - 110))
  const maxX = Math.max(...all.map((b) => b.x + b.w))
  const minY = Math.min(...all.map((b) => b.y))
  const dx = -minX
  const dy = MAP.top - minY
  for (const b of all) {
    b.x += dx
    b.y += dy
  }
  for (const l of labels) {
    l.x += dx
    l.y += dy
  }
  const byId: Record<string, Box> = Object.fromEntries(all.map((b) => [b.id, b]))
  const edges: FlatEdge[] = []
  const halfGap = (MAP.rowPitch - CARD_H) / 2
  for (const n of g.nodes) {
    const b = byId[n.id]
    if (!b) continue
    for (const r of n.requires) {
      const a = byId[r]
      if (!a) continue
      const x1 = a.x + a.w / 2
      const x2 = b.x + b.w / 2
      edges.push({ from: r, to: n.id, kind: edgeKind(g.byId[r], n), d: elbowV(x1, a.y, x2, b.y + b.h, b.y + b.h + halfGap) })
    }
  }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  return { w: maxX + dx, h: Math.max(...all.map((b) => b.y + b.h)) + 8, boxes: all, edges, labels }
}

// ---- Tracks (the Map zoomed out) -------------------------------------------------------------------------------

export const TRACKS = { w: 164, h: 54, rowPitch: 132 } as const

export function tracksLayout(g: SkillGraph, map: FlatLayout): FlatLayout {
  const skillBoxes = map.boxes.filter((b) => g.byId[b.id]?.kind === 'skill')
  const center = (t: string): number => {
    const bs = skillBoxes.filter((b) => g.byId[b.id].track === t)
    return bs.length ? bs.reduce((s, b) => s + b.x + b.w / 2, 0) / bs.length : 0
  }
  // Track links: a skill in one track needing a skill in another.
  const tReq = new Map<string, Set<string>>(g.tracks.map((t) => [t.id, new Set()]))
  for (const n of g.nodes)
    if (n.kind === 'skill')
      for (const r of n.requires) {
        const rt = g.byId[r]?.track
        if (rt && rt !== n.track) tReq.get(n.track)?.add(rt)
      }
  const ids = g.tracks.filter((t) => t.total > 0).map((t) => t.id)
  const depth = longestDepth(ids, (t) => [...(tReq.get(t) ?? [])])
  const rows = Math.max(0, ...ids.map((t) => depth[t])) + 1
  const goalId = g.goal?.id
  const goal = goalId ? map.boxes.find((b) => b.id === goalId) : undefined
  const top = goal ? MAP.top + MAP.goalH + 48 : MAP.top
  const Y = (r: number): number => top + (rows - 1 - r) * TRACKS.rowPitch
  const tw = (t: string): number => Math.max(TRACKS.w, Math.ceil((g.tracks.find((k) => k.id === t)?.label ?? t).length * 8 + 80))
  const boxes: Box[] = ids.map((t) => ({ id: `track:${t}`, x: center(t) - tw(t) / 2, y: Y(depth[t]), w: tw(t), h: TRACKS.h }))
  // Same-row cards that collide: push apart left to right.
  for (let r = 0; r < rows; r++) {
    const row = boxes.filter((b) => b.y === Y(r)).sort((a, b) => a.x - b.x)
    for (let i = 1; i < row.length; i++) row[i].x = Math.max(row[i].x, row[i - 1].x + row[i - 1].w + MAP.laneGap)
  }
  const all: Box[] = [...boxes]
  const tops = boxes.filter((b) => b.y === Math.min(...boxes.map((x) => x.y)))
  const gb: Box | undefined =
    goal && goalId ? { id: goalId, x: tops.reduce((s, b) => s + b.x + b.w / 2, 0) / Math.max(1, tops.length) - MAP.goalW / 2, y: MAP.top, w: MAP.goalW, h: MAP.goalH } : undefined
  if (gb) all.push(gb)
  const minX = Math.min(...all.map((b) => b.x))
  for (const b of all) b.x -= minX
  const at = Object.fromEntries(boxes.map((b) => [b.id, b]))
  const edges: FlatEdge[] = []
  const tr = (t: string): SkillGraph['tracks'][number] | undefined => g.tracks.find((x) => x.id === t)
  for (const t of ids)
    for (const r of tReq.get(t) ?? []) {
      const a = at[`track:${r}`]
      const b = at[`track:${t}`]
      if (!a || !b) continue
      const done = (tr(r)?.mastered ?? 0) >= (tr(r)?.total ?? 1)
      edges.push({ from: a.id, to: b.id, kind: done ? 'done' : 'locked', d: elbowV(a.x + a.w / 2, a.y, b.x + b.w / 2, b.y + b.h) })
    }
  if (gb && goalId) {
    const gt = g.byId[goalId]?.track
    const from = (gt && at[`track:${gt}`]) || tops[0]
    if (from) edges.push({ from: from.id, to: goalId, kind: 'locked', d: elbowV(from.x + from.w / 2, from.y, gb.x + gb.w / 2, gb.y + gb.h) })
  }
  edges.sort((a, b) => EDGE_ORDER[a.kind] - EDGE_ORDER[b.kind])
  return { w: Math.max(...all.map((b) => b.x + b.w)), h: Math.max(...all.map((b) => b.y + b.h)) + 8, boxes: all, edges, labels: [] }
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
