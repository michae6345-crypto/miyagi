/**
 * kind "heatmap": predicted (and exact, when sent) field u(x,t) on a canvas. t runs left to right, x bottom to top.
 * One hue, a tad of color (Adrian, Sat): a value ramp from `fill.thumb` (low) to sky, the Diagram tone (high), one
 * scale shared by both panels. Hover a panel for the value under the pointer. Panels sweep in along t (350 ms, 30 ms stagger).
 * Data orientation follows the engine (server/orchestrator/stubs.py): grid[tIndex][xIndex]; a transposed
 * grid ([x][t]) is accepted too. Empty or malformed data renders nothing (never a placeholder).
 */
import { motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { actionTone, color, fill } from '../../core/theme'

export type HeatmapData = { x: number[]; t: number[]; predicted: number[][]; exact?: number[][] }

const W = 600
const GAP = 16

/** grid[t][x] with finite numbers, or undefined when the shape doesn't match the axes. */
function orient(grid: number[][] | undefined, nx: number, nt: number): number[][] | undefined {
  if (!Array.isArray(grid) || !grid.length || !nx || !nt) return undefined
  if (grid.length === nt && grid.every((r) => Array.isArray(r) && r.length === nx)) return grid
  if (grid.length === nx && grid.every((r) => Array.isArray(r) && r.length === nt)) return Array.from({ length: nt }, (_, j) => grid.map((r) => r[j]))
  return undefined
}

const hex = (h: string): [number, number, number] => {
  const m = h.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16)) as [number, number, number]
}
const LOW = hex(fill.thumb)
const HIGH = hex(actionTone.diagram)
const ramp = (f: number): [number, number, number] => [0, 1, 2].map((i) => Math.round(LOW[i] + (HIGH[i] - LOW[i]) * f)) as [number, number, number]

const num = (v: number): string => {
  if (!Number.isFinite(v)) return '–'
  const a = Math.abs(v)
  return a !== 0 && (a < 1e-2 || a >= 1e4) ? v.toExponential(1) : v.toFixed(a < 10 ? 2 : 1)
}

export function Heatmap({ data }: { data: HeatmapData }): ReactNode {
  const xs = Array.isArray(data?.x) ? data.x : []
  const ts = Array.isArray(data?.t) ? data.t : []
  const panels = useMemo(() => {
    const out: { name: string; grid: number[][] }[] = []
    const p = orient(data?.predicted, xs.length, ts.length)
    if (p) out.push({ name: 'Predicted', grid: p })
    const e = orient(data?.exact, xs.length, ts.length)
    if (p && e) out.push({ name: 'Exact', grid: e })
    return out
  }, [data, xs.length, ts.length])

  const [lo, hi] = useMemo(() => {
    let a = Infinity
    let b = -Infinity
    for (const { grid } of panels) for (const row of grid) for (const v of row) if (Number.isFinite(v)) (a = Math.min(a, v)), (b = Math.max(b, v))
    return Number.isFinite(a) ? [a, b] : [0, 1]
  }, [panels])

  const [hover, setHover] = useState<{ i: number; j: number } | undefined>()
  if (!panels.length) return null

  const two = panels.length > 1
  const pw = two ? (W - GAP) / 2 : W
  const ph = two ? 150 : 180
  const sig = `${xs.length}x${ts.length}|${panels.length}|${lo}|${hi}`

  return (
    <div key={sig} className="mx-auto" style={{ width: W }}>
      <div className="flex" style={{ gap: GAP }}>
        {panels.map((p, k) => (
          <div key={p.name} style={{ width: pw }}>
            {two && (
              <div className="mb-[5px] text-[11px] leading-[14px]" style={{ color: color.label }}>
                {p.name}
              </div>
            )}
            <motion.div
              className="overflow-hidden"
              style={{ width: pw, height: ph, borderRadius: 8 }}
              initial={{ clipPath: 'inset(0 100% 0 0)' }}
              animate={{ clipPath: 'inset(0 0% 0 0)' }}
              transition={{ duration: 0.35, delay: k * 0.03, ease: 'easeOut' }}
            >
              <Field grid={p.grid} lo={lo} hi={hi} w={pw} h={ph} onHover={setHover} />
            </motion.div>
          </div>
        ))}
      </div>
      <div className="mt-[8px] flex h-[14px] items-center gap-[10px] text-[11px] tabular-nums" style={{ color: color.label }}>
        <span className="min-w-0 flex-1 truncate">
          {hover && (
            <>
              t {num(ts[hover.i])} · x {num(xs[hover.j])}
              {panels.map((p) => (
                <span key={p.name} style={{ color: color.text }}>
                  {'  ·  '}
                  {two ? `${p.name.toLowerCase()} ` : ''}
                  {num(p.grid[hover.i]?.[hover.j])}
                </span>
              ))}
            </>
          )}
        </span>
        <span>{num(lo)}</span>
        <Legend />
        <span>{num(hi)}</span>
      </div>
    </div>
  )
}

/** The value ramp in 8 steps (a scale, not decoration). */
function Legend(): ReactNode {
  return (
    <span className="flex h-[6px] w-[72px] overflow-hidden rounded-[3px]">
      {Array.from({ length: 8 }, (_, i) => (
        <span key={i} className="flex-1" style={{ background: `rgb(${ramp(i / 7).join(',')})` }} />
      ))}
    </span>
  )
}

function Field({ grid, lo, hi, w, h, onHover }: { grid: number[][]; lo: number; hi: number; w: number; h: number; onHover: (p?: { i: number; j: number }) => void }): ReactNode {
  const ref = useRef<HTMLCanvasElement>(null)
  const nt = grid.length
  const nx = grid[0]?.length ?? 0

  useEffect(() => {
    const cv = ref.current
    if (!cv || !nt || !nx) return
    const dpr = Math.max(1, window.devicePixelRatio || 1)
    cv.width = Math.round(w * dpr)
    cv.height = Math.round(h * dpr)
    // One pixel per sample (t → right, x → up), then a smooth upscale.
    const src = document.createElement('canvas')
    src.width = nt
    src.height = nx
    const sctx = src.getContext('2d')
    const ctx = cv.getContext('2d')
    if (!sctx || !ctx) return
    const img = sctx.createImageData(nt, nx)
    const span = hi - lo || 1
    for (let i = 0; i < nt; i++)
      for (let j = 0; j < nx; j++) {
        const v = grid[i][j]
        const [r, g, b] = ramp(Number.isFinite(v) ? Math.min(1, Math.max(0, (v - lo) / span)) : 0)
        const o = ((nx - 1 - j) * nt + i) * 4
        img.data[o] = r
        img.data[o + 1] = g
        img.data[o + 2] = b
        img.data[o + 3] = 255
      }
    sctx.putImageData(img, 0, 0)
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.clearRect(0, 0, cv.width, cv.height)
    ctx.drawImage(src, 0, 0, cv.width, cv.height)
  }, [grid, lo, hi, w, h, nt, nx])

  const pick = (e: React.PointerEvent<HTMLCanvasElement>): void => {
    const r = e.currentTarget.getBoundingClientRect()
    const fx = (e.clientX - r.left) / r.width
    const fy = (e.clientY - r.top) / r.height
    onHover({ i: Math.min(nt - 1, Math.max(0, Math.floor(fx * nt))), j: Math.min(nx - 1, Math.max(0, Math.floor((1 - fy) * nx))) })
  }

  return <canvas ref={ref} style={{ width: w, height: h, display: 'block' }} onPointerMove={pick} onPointerLeave={() => onHover(undefined)} />
}
