/**
 * Where everything on the skill map sits (pure: no React). Mockups 10 / 12: nodes left to right on a fixed grid over
 * the full width, labels under the nodes; the track's header sits above its first row. Other tracks' concepts
 * (map.cross, e.g. Math) get a lane above the track (header on the left when the first columns are free), each one
 * over the node it links to, with a dashed "shared idea" arrow down to it and its note beside the arrow. A track
 * longer than one row wraps; the last row is right-aligned (mockup 12: what's next hangs under the end of what you
 * learned) and the free cells on its left hold the selected concept. The wrapping edge runs back under the row.
 */
import type { SkillCross, SkillMap, SkillNode } from './types'

export const NODE = 40
const R = NODE / 2
/** A lane header placed above its nodes (tile + name + count). */
const HEAD_H = 36
const MIN_COL = 100
const MAX_COLS = 9
const LABEL_GAP = 8
export const LINE = 16
export const DETAIL_LINE = 15
const ROW_GAP = 20
/** Between a cross lane and the lane under it: the hairline, then the arrows' notes (2 lines). */
const CROSS_GAP = 46
export const NOTE_LINE = 14

export type Placed<T> = T & { x: number; y: number; row: number; col: number; lines: number }
export type Lane = { kind: 'cross' | 'track'; name: string; top: number; inline: boolean; done?: number; total?: number }
export type Path = { d: string; dashed?: boolean; faint?: boolean }
export type Note = { x: number; y: number; w: number; text: string }
export type Layout = {
  width: number
  height: number
  colW: number
  labelW: number
  lanes: Lane[]
  nodes: Placed<SkillNode>[]
  cross: Placed<SkillCross & { key: string }>[]
  paths: Path[]
  notes: Note[]
  rules: number[]
  /** The free cells at the start of the last row (two columns or more), for the selected concept. */
  detail?: { x: number; y: number; w: number; h: number }
}

/** How many lines a label takes at 13 px in a box this wide (a safe estimate: SF Pro / Segoe average ~0.56 em). */
export function lineCount(text: string, width: number, px = 13): number {
  const per = Math.max(4, Math.floor(width / (px * 0.58)))
  let lines = 1
  let used = 0
  for (const w of text.split(/\s+/).filter(Boolean)) {
    const len = w.length
    if (used === 0) used = len
    else if (used + 1 + len <= per) used += 1 + len
    else {
      lines += 1
      used = len
    }
    while (used > per) {
      lines += 1
      used -= per
    }
  }
  return lines
}

/** An orthogonal path through `pts` with rounded corners (radius r). */
function rounded(pts: Array<[number, number]>, r = 7): string {
  let d = `M${pts[0][0]},${pts[0][1]}`
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1]
    const [x, y] = pts[i]
    const [nx, ny] = pts[i + 1]
    const inLen = Math.hypot(x - px, y - py)
    const outLen = Math.hypot(nx - x, ny - y)
    const k = Math.min(r, inLen / 2, outLen / 2)
    const ax = x - ((x - px) / (inLen || 1)) * k
    const ay = y - ((y - py) / (inLen || 1)) * k
    const bx = x + ((nx - x) / (outLen || 1)) * k
    const by = y + ((ny - y) / (outLen || 1)) * k
    d += ` L${ax},${ay} Q${x},${y} ${bx},${by}`
  }
  const last = pts[pts.length - 1]
  return `${d} L${last[0]},${last[1]}`
}

export function layout(map: SkillMap, width: number): Layout {
  const cols = Math.max(3, Math.min(MAX_COLS, Math.floor(width / MIN_COL)))
  const colW = width / cols
  const labelW = colW - 12
  const cx = (col: number): number => colW * (col + 0.5)
  const lanes: Lane[] = []
  const rules: number[] = []
  const paths: Path[] = []
  const notes: Note[] = []

  // Track nodes: row-major on the grid; a last row that isn't full is right-aligned. When what's learned and
  // what's next each fit in one row, they get a row each (mockup 12: the next concepts hang under the learned ones).
  const total = map.nodes.length
  const split = map.nodes.findIndex((n) => n.state === 'next')
  const starts =
    split > 0 && split <= cols && total - split <= cols && Math.ceil(total / cols) <= 2
      ? [0, split]
      : Array.from({ length: Math.ceil(total / cols) }, (_, r) => r * cols)
  const rowsN = starts.length
  const rowOf = (i: number): number => starts.filter((s0) => s0 <= i).length - 1
  const lastCount = total - starts[rowsN - 1]
  const shift = rowsN > 1 ? cols - lastCount : 0
  const grid = map.nodes.map((n, i) => {
    const row = rowOf(i)
    return { n, row, col: i - starts[row] + (row === rowsN - 1 ? shift : 0), first: starts.includes(i) }
  })
  const at = new Map(grid.map((g) => [g.n.id, g]))

  // Cross lanes (one per other track, in order of first appearance), each concept over the node it links to.
  const tracks: string[] = []
  for (const c of map.cross) if (!tracks.includes(c.track)) tracks.push(c.track)
  let y = 0
  const cross: Layout['cross'] = []
  const links: Array<{ from: Placed<SkillCross & { key: string }>; bottom: number }> = []
  for (const track of tracks) {
    const items = map.cross.filter((c) => c.track === track)
    const used = new Set<number>()
    const colsOf = items.map((c) => {
      const want = at.get(c.to)?.col ?? 0
      let col = want
      for (let d = 0; used.has(col) && d < cols * 2; d++) col = want + (d % 2 === 0 ? d / 2 + 1 : -(d + 1) / 2)
      col = Math.max(0, Math.min(cols - 1, col))
      used.add(col)
      return col
    })
    const inline = colsOf.every((c) => c >= 2)
    lanes.push({ kind: 'cross', name: track, top: inline ? y : y, inline, total: items.length })
    if (!inline) y += HEAD_H
    const placed = items.map((c, i) => ({ ...c, key: `${track}:${i}`, col: colsOf[i], row: -1, x: cx(colsOf[i]), y: y + R, lines: Math.min(2, lineCount(c.label, labelW)) }))
    const lines = Math.max(1, ...placed.map((p) => p.lines))
    const bottom = y + NODE + LABEL_GAP + lines * LINE
    cross.push(...placed)
    for (const p of placed) links.push({ from: p, bottom })
    rules.push(bottom + 12)
    y = bottom + CROSS_GAP
  }

  // The track: its header, then its rows.
  const done = map.nodes.filter((n) => n.state === 'mastered').length
  lanes.push({ kind: 'track', name: map.track, top: y, inline: false, done, total })
  y += HEAD_H
  const rowTop: number[] = []
  const rowBottom: number[] = []
  const nodes: Layout['nodes'] = []
  for (let r = 0; r < rowsN; r++) {
    const inRow = grid.filter((g) => g.row === r)
    const lines = Math.max(1, ...inRow.map((g) => Math.min(3, lineCount(g.n.label, labelW))))
    const detail = inRow.some((g) => g.n.state === 'learning' && g.n.detail) ? DETAIL_LINE + 2 : 0
    rowTop.push(y)
    for (const g of inRow) nodes.push({ ...g.n, row: r, col: g.col, x: cx(g.col), y: y + R, lines: Math.min(3, lineCount(g.n.label, labelW)) })
    rowBottom.push(y + NODE + LABEL_GAP + lines * LINE + detail)
    y = rowBottom[r] + (r < rowsN - 1 ? ROW_GAP : 0)
  }
  const firsts = new Set(grid.filter((g) => g.first).map((g) => g.n.id))

  // Edges: straight along a row; the one that wraps drops after the row's last node, runs back under the row and
  // comes in from the left of the next row's first node; anything else is a soft curve.
  const pos = new Map(nodes.map((n) => [n.id, n]))
  for (const e of map.edges) {
    const a = pos.get(e.from)
    const b = pos.get(e.to)
    if (!a || !b) continue
    const faint = b.state === 'next'
    if (a.row === b.row && b.col > a.col) {
      paths.push({ d: `M${a.x + R + 5},${a.y} L${b.x - R - 6},${b.y}`, faint })
    } else if (b.row === a.row + 1 && firsts.has(b.id)) {
      const xr = Math.min(width - 2, a.x + colW / 2 - 2)
      const xl = b.x - colW / 2 + 4
      const ym = rowBottom[a.row] + ROW_GAP / 2
      paths.push({ d: rounded([[a.x + R + 5, a.y], [xr, a.y], [xr, ym], [xl, ym], [xl, b.y], [b.x - R - 6, b.y]]), faint })
    } else {
      const mx = (a.x + b.x) / 2
      paths.push({ d: `M${a.x},${a.y + R + 4} C${a.x},${b.y - 40} ${mx},${b.y - R - 30} ${b.x},${b.y - R - 6}`, faint })
    }
  }

  // Shared ideas: a dashed arrow from under the concept's label down to its node; the note beside the arrow.
  const xs = links.map((l) => l.from.x)
  for (const { from, bottom } of links) {
    const b = pos.get(from.to)
    if (!b) continue
    const y0 = bottom + 4
    const y1 = b.y - R - 6
    paths.push({ d: from.x === b.x ? `M${from.x},${y0} L${b.x},${y1}` : rounded([[from.x, y0], [from.x, (y0 + y1) / 2], [b.x, (y0 + y1) / 2], [b.x, y1]]), dashed: true })
    if (from.note) {
      const right = Math.min(width, ...xs.filter((x) => x > from.x).map((x) => x - 10))
      notes.push({ x: from.x + 9, y: bottom + 20, w: Math.max(60, right - from.x - 12), text: from.note })
    }
  }

  const free = rowsN > 1 ? shift : cols - total
  const last = rowsN - 1
  const detail = free >= 2 && rowsN > 0 ? { x: 0, y: rowTop[last] - 2, w: free * colW - 16, h: rowBottom[last] - rowTop[last] + 4 } : undefined
  // One row with room at its end: the box goes after the nodes instead.
  if (detail && rowsN === 1) detail.x = total * colW + 16
  return { width, height: y, colW, labelW, lanes, nodes, cross, paths, notes, rules, detail }
}
