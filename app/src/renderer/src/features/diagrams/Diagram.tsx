/**
 * Intuition diagrams (the server sends the data; we only render).
 *   network   : the real model's layers + autograd arrows to u_t, u_x → residual
 *   gradients : gradient norm per layer over training (shows the PINN failure)
 *   heatmap   : predicted vs exact u(x,t)  (TODO F4: canvas)
 * Lines draw in (pathLength, 350ms, 30ms stagger per layer).
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Waypoints } from 'lucide-react'
import { color } from '../../core/theme'
import { CloseButton } from '../../core/ui/atoms'
import { useDiagram } from './store'

export function DiagramView(): ReactNode {
  const d = useDiagram((s) => s.diagram)
  if (!d) return null
  const title = d.kind === 'network' ? 'Architecture' : d.kind === 'gradients' ? 'Gradient flow' : 'Solution'
  return (
    <div className="px-[20px] pb-[16px] pt-[16px]">
      <div className="flex items-center gap-[8px]">
        <Waypoints size={15} style={{ color: color.accent }} />
        <span className="text-[14px] font-semibold">Intuition</span>
        <span className="text-[13px] text-white/45">· {title}</span>
        <span className="flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[10px]">
        {d.kind === 'network' && <Network data={d.data as Record<string, unknown>} />}
        {d.kind === 'gradients' && <Gradients data={d.data as Record<string, unknown>} />}
        {d.kind === 'heatmap' && <div className="grid h-[180px] place-items-center text-[13px] text-white/40">heatmap (coming)</div>}
      </div>
      <div className="mt-[8px] text-center text-[14px] leading-[20px] text-white/80">{d.caption}</div>
    </div>
  )
}

const draw = (i: number) => ({ initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration: 0.35, delay: i * 0.03 } })

function Network({ data }: { data: Record<string, unknown> }): ReactNode {
  const layers = (data.layers as number[]) ?? [2, 50, 50, 50, 50, 1]
  const act = (data.activation as string) ?? 'tanh'
  const inputs = (data.inputs as string[]) ?? ['x', 't']
  const derivs = (data.derivatives as string[]) ?? ['u_t', 'u_x']
  const residual = (data.residual as string) ?? 'residual'
  const W = 600
  const H = 196
  const netW = 420
  const colX = layers.map((_, i) => 24 + (i * (netW - 48)) / (layers.length - 1))
  const nodesOf = (n: number): (number | 'dots')[] => (n <= 5 ? Array.from({ length: n }, (_, i) => i) : [0, 1, 2, 'dots', 4])
  const nodeY = (count: number, i: number): number => {
    const shown = Math.min(count, 5)
    const gap = 28
    return 82 - ((shown - 1) * gap) / 2 + i * gap
  }
  const ux = netW + 50
  return (
    <svg width={W} height={H} className="mx-auto block overflow-visible">
      {/* edges */}
      {layers.slice(0, -1).map((n, li) => {
        const a = nodesOf(n).filter((x) => x !== 'dots') as number[]
        const b = nodesOf(layers[li + 1]).filter((x) => x !== 'dots') as number[]
        return a.flatMap((i) =>
          b.map((j) => (
            <motion.path
              key={`${li}-${i}-${j}`}
              d={`M${colX[li]},${nodeY(n, i)} L${colX[li + 1]},${nodeY(layers[li + 1], j)}`}
              stroke="rgba(255,255,255,.12)"
              strokeWidth="1"
              {...draw(li)}
            />
          ))
        )
      })}
      {/* nodes */}
      {layers.map((n, li) =>
        nodesOf(n).map((i, k) =>
          i === 'dots' ? (
            <text key={`${li}-d`} x={colX[li]} y={nodeY(n, k) + 4} textAnchor="middle" fill="rgba(255,255,255,.4)" fontSize="12">
              ⋮
            </text>
          ) : (
            <motion.circle
              key={`${li}-${i}`}
              cx={colX[li]}
              cy={nodeY(n, i)}
              r={li === 0 || li === layers.length - 1 ? 13 : 8}
              fill="#000"
              stroke={li === layers.length - 1 ? color.accent : 'rgba(255,255,255,.75)'}
              strokeWidth="1.3"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: li * 0.03, duration: 0.2 }}
            />
          )
        )
      )}
      {inputs.map((name, i) => (
        <text key={name} x={colX[0]} y={nodeY(layers[0], i) + 4} textAnchor="middle" fill="#fff" fontSize="12" fontStyle="italic">
          {name}
        </text>
      ))}
      <text x={colX[colX.length - 1]} y={nodeY(1, 0) + 4} textAnchor="middle" fill="#fff" fontSize="12" fontStyle="italic">
        {(data.output as string) ?? 'u'}
      </text>
      {/* labels */}
      {layers.map((n, li) => (
        <g key={`l${li}`}>
          <text x={colX[li]} y={172} textAnchor="middle" fill="#fff" fontSize="12" fontWeight="600">
            {n}
          </text>
          <text x={colX[li]} y={187} textAnchor="middle" fill="rgba(255,255,255,.45)" fontSize="10.5">
            {li === 0 ? 'inputs' : li === layers.length - 1 ? 'output' : act}
          </text>
        </g>
      ))}
      {/* autograd */}
      {derivs.map((name, i) => {
        const y = i === 0 ? 38 : 126
        return (
          <g key={name}>
            <motion.path
              d={`M${colX[colX.length - 1] + 14},${82 + (i ? 6 : -6)} L${ux + 34},${y}`}
              stroke={color.accent}
              strokeWidth="1.3"
              strokeDasharray="4 3"
              fill="none"
              {...draw(layers.length + 1)}
            />
            <rect x={ux + 34} y={y - 13} width={58} height={26} rx={8} fill="#000" stroke="rgba(255,255,255,.35)" />
            <text x={ux + 63} y={y + 4} textAnchor="middle" fill="#fff" fontSize="12" fontFamily="ui-monospace, monospace">
              {name}
            </text>
          </g>
        )
      })}
      <motion.rect x={ux + 20} y={68} width={92} height={28} rx={14} fill={color.accent} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }} />
      <text x={ux + 66} y={86} textAnchor="middle" fill="#fff" fontSize="11.5" fontFamily="ui-monospace, monospace">
        {residual.length > 13 ? 'residual' : residual}
      </text>
      <text x={ux + 66} y={187} textAnchor="middle" fill="rgba(255,255,255,.45)" fontSize="10.5">
        → 0 · residual
      </text>
    </svg>
  )
}

function Gradients({ data }: { data: Record<string, unknown> }): ReactNode {
  const layers = (data.layers as string[]) ?? []
  const norms = (data.norms as number[][]) ?? []
  const W = 600
  const H = 200
  const pad = { l: 34, r: 40, t: 10, b: 24 }
  const logs = norms.map((r) => r.map((v) => Math.log10(Math.max(v, 1e-6))))
  const flat = logs.flat()
  const lo = Math.min(...flat)
  const hi = Math.max(...flat)
  const x = (i: number, n: number): number => pad.l + (i / Math.max(1, n - 1)) * (W - pad.l - pad.r)
  const y = (v: number): number => pad.t + ((hi - v) / (hi - lo || 1)) * (H - pad.t - pad.b)
  const tone = (i: number): string => (i < 2 ? color.amber : i < 3 ? '#d8c27a' : color.accent)
  return (
    <svg width={W} height={H} className="mx-auto block overflow-visible">
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="rgba(255,255,255,.12)" />
      <text x={pad.l} y={H - 6} fill="rgba(255,255,255,.4)" fontSize="10.5">
        start
      </text>
      <text x={W - pad.r} y={H - 6} textAnchor="end" fill="rgba(255,255,255,.4)" fontSize="10.5">
        5k epochs
      </text>
      <text x={pad.l - 8} y={pad.t + 8} textAnchor="end" fill="rgba(255,255,255,.4)" fontSize="10.5">
        |∇|
      </text>
      {logs.map((row, li) => (
        <g key={li}>
          <motion.path
            d={row.map((v, i) => `${i ? 'L' : 'M'}${x(i, row.length).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}
            fill="none"
            stroke={tone(li)}
            strokeWidth={li < 2 ? 2.2 : 1.5}
            {...draw(li)}
          />
          <text x={W - pad.r + 6} y={y(row[row.length - 1]) + 4} fill={tone(li)} fontSize="11" fontWeight="600">
            {layers[li]}
          </text>
        </g>
      ))}
    </svg>
  )
}
