/**
 * Intuition diagrams (the server sends the data; we only render).
 *   network   : the real model's layers + autograd arrows to u_t, u_x → residual; with real weights (data.frames),
 *               a live network whose neurons light up and fire (NeuralNet.tsx)
 *   gradients : gradient norm per layer over training (shows the PINN failure)
 *   heatmap   : predicted vs exact field on a canvas (Heatmap.tsx)
 *   graph     : any topic's nodes + edges, every layout family (Graph.tsx); tabs when a step has several kinds (Tabs.tsx)
 * Lines draw in (pathLength, 350ms, 30ms stagger per layer).
 * Look: a sky tile (Diagram's option tone, same as its button) and the title; neutral lines; the
 * highlighted series in sky (understand), never amber (amber only means off track). Every label from the data.
 */
import { motion } from 'motion/react'
import type { ReactNode } from 'react'
import { Waypoints } from 'lucide-react'
import { actionTone, color, fill } from '../../core/theme'
import { CloseButton } from '../../core/ui/atoms'
import { useDiagram, type DiagramPayload } from './store'
import { Graph } from './Graph'
import { NeuralNet, WEIGHT_NEG, WEIGHT_POS } from './NeuralNet'
import { SafeDiagram } from './SafeDiagram'
import { Firing, isFiringNetwork } from './Firing'
import { Heatmap, type HeatmapData } from './Heatmap'
import { DiagramTabs, titleOf } from './Tabs'
import type { GraphDiagramData } from '../../../../../../shared/contracts/events'
import { draw as drawIn, duration, enter, fade, prefersReduced, stagger } from '../../core/ui/motion'

export function DiagramView(): ReactNode {
  const d = useDiagram((s) => s.diagram)
  if (!d) return null
  const title = titleOf(d)
  return (
    <div className="px-[20px] pb-[16px] pt-[16px]">
      <div className="flex items-center gap-[10px]">
        <span className="grid h-[24px] w-[24px] place-items-center rounded-[7px]" style={{ background: actionTone.diagram, color: color.onAccent }}>
          <Waypoints size={13} strokeWidth={1.9} />
        </span>
        <DiagramTabs fallback={<span className="text-[14px] font-semibold">{title}</span>} />
        <span className="flex-1" />
        <CloseButton />
      </div>
      <div className="mt-[10px]">
        <DiagramBody d={d} />
      </div>
      {/* Left-aligned under the left-aligned title (audit A23). */}
      {d.caption && (
        <div
          className="mt-[8px] overflow-hidden text-left text-[14px] leading-[20px]"
          style={{ color: color.label, display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2 }}
        >
          {d.caption}
        </div>
      )}
    </div>
  )
}

/** The drawing itself, at the island's 600 px content width, in island (dark) ink. The drawer's flyout reuses it. */
export function DiagramBody({ d }: { d: DiagramPayload }): ReactNode {
  return (
    <SafeDiagram resetKey={d.data}>
      {d.kind === 'network' &&
        ((d.data as Record<string, unknown>).frames ? (
          isFiringNetwork(d.data as Record<string, unknown>) ? <Firing data={d.data as Record<string, unknown>} /> : <NeuralNet data={d.data as Record<string, unknown>} />
        ) : (
          <Network data={d.data as Record<string, unknown>} />
        ))}
      {d.kind === 'gradients' && <Gradients data={d.data as Record<string, unknown>} />}
      {d.kind === 'heatmap' && <Heatmap data={d.data as HeatmapData} />}
      {d.kind === 'graph' && <Graph data={d.data as GraphDiagramData} />}
    </SafeDiagram>
  )
}

/** A diagram line drawing in as the i-th of its group (a fade with Reduce Motion). */
const draw = (i: number) => drawIn(prefersReduced(), { delay: i * stagger.each, length: duration.draw })

function Network({ data }: { data: Record<string, unknown> }): ReactNode {
  // Generality: everything comes from the data (no demo-lesson defaults).
  const layers = (data.layers as number[]) ?? []
  const act = (data.activation as string) ?? ''
  const inputs = (data.inputs as string[]) ?? []
  const derivs = (data.derivatives as string[]) ?? []
  const residual = (data.residual as string) ?? ''
  const output = typeof data.output === 'string' ? data.output : ''
  const H = 196
  const netW = 420
  // With nothing on the right (no autograd arrows, no combined output) the drawing ends at the output's name, written
  // in full: no empty right third, so it sits centred (test 10 judge review: "softm…", network in the left 420 of 600).
  const W = derivs.length || residual ? 600 : Math.round(netW - 24 + 19 + (output ? output.length * 6.6 + 4 : 0) + 16)
  // Node names sit OUTSIDE the circles (inputs to the left, the output to the right): inside, "X" covered the first
  // input and "output" overlapped its node (Michael's test 5). Room on the left grows with the longest input name.
  const short = (t: string): string => (t.length > 12 ? `${t.slice(0, 11)}…` : t)
  const left = 24 + Math.min(80, Math.max(0, ...inputs.map((t) => short(t).length * 6.6 + 8)))
  const colX = layers.map((_, i) => left + (i * (netW - 24 - left)) / (layers.length - 1))
  // Optional real weights (extra field, like NeuralNet's frames): W[l] is layer l → l+1, row-major (from i, to j at
  // i*n+j). Thickness = |w|, hue = sign (the same blue / brown NeuralNet uses for weights only).
  const weights = Array.isArray(data.W) ? (data.W as number[][]) : Array.isArray(data.weights) ? (data.weights as number[][]) : undefined
  const wMax = Math.max(1e-9, ...(weights ?? []).flat().map((v) => Math.abs(Number(v) || 0)))
  const weightOf = (li: number, i: number, j: number): number | undefined => {
    const v = weights?.[li]?.[i * layers[li + 1] + j]
    return typeof v === 'number' && Number.isFinite(v) ? v : undefined
  }
  const nodesOf = (n: number): (number | 'dots')[] => (n <= 5 ? Array.from({ length: n }, (_, i) => i) : [0, 1, 2, 'dots', 4])
  const nodeY = (count: number, i: number): number => {
    const shown = Math.min(count, 5)
    const gap = 28
    return 82 - ((shown - 1) * gap) / 2 + i * gap
  }
  const ux = netW + 50
  if (layers.length < 2) return null
  return (
    <svg width={W} height={H} className="mx-auto block overflow-visible">
      {/* edges */}
      {layers.slice(0, -1).map((n, li) => {
        const a = nodesOf(n).filter((x) => x !== 'dots') as number[]
        const b = nodesOf(layers[li + 1]).filter((x) => x !== 'dots') as number[]
        return a.flatMap((i) =>
          b.map((j) => {
            const w = weightOf(li, i, j)
            return (
              <motion.path
                key={`${li}-${i}-${j}`}
                d={`M${colX[li]},${nodeY(n, i)} L${colX[li + 1]},${nodeY(layers[li + 1], j)}`}
                stroke={w === undefined ? color.hairline : w >= 0 ? WEIGHT_POS : WEIGHT_NEG}
                strokeWidth={w === undefined ? 1 : 0.6 + 2.6 * (Math.abs(w) / wMax)}
                strokeOpacity={w === undefined ? 1 : 0.35 + 0.65 * (Math.abs(w) / wMax)}
                {...draw(li)}
              />
            )
          })
        )
      })}
      {/* nodes */}
      {layers.map((n, li) =>
        nodesOf(n).map((i, k) =>
          i === 'dots' ? (
            <text key={`${li}-d`} x={colX[li]} y={nodeY(n, k) + 4} textAnchor="middle" fill={color.faint} fontSize="12">
              ⋮
            </text>
          ) : (
            <motion.circle
              key={`${li}-${i}`}
              cx={colX[li]}
              cy={nodeY(n, i)}
              r={li === 0 || li === layers.length - 1 ? 13 : 8}
              fill={color.island}
              stroke={li === layers.length - 1 ? color.accent : fill.chipText}
              strokeWidth="1.3"
              initial={{ scale: 0.6, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={enter(li * stagger.each)}
            />
          )
        )
      )}
      {/* One name per input node; a single name for several inputs ("X") sits at the column's middle. */}
      {inputs.map((name, i) => {
        const y = inputs.length === 1 && layers[0] > 1 ? 82 : nodeY(layers[0], i)
        return (
          <text key={`${name}-${i}`} x={colX[0] - 19} y={y + 4} textAnchor="end" fill={color.text} fontSize="12" fontStyle="italic">
            {short(name)}
          </text>
        )
      })}
      {output && (
        // With autograd arrows on the right (derivatives), the short output name stays in its node, clear of them;
        // without them it's written in full to the node's right (W makes room for it).
        <text
          x={colX[colX.length - 1] + (derivs.length ? 0 : 19)}
          y={82 + 4}
          textAnchor={derivs.length ? 'middle' : 'start'}
          fill={color.text}
          fontSize="12"
          fontStyle="italic"
        >
          {derivs.length ? short(output) : output}
        </text>
      )}
      {/* labels */}
      {layers.map((n, li) => (
        <g key={`l${li}`}>
          <text x={colX[li]} y={172} textAnchor="middle" fill={color.text} fontSize="12" fontWeight="600">
            {n}
          </text>
          <text x={colX[li]} y={187} textAnchor="middle" fill={color.faint} fontSize="10.5">
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
            <rect x={ux + 34} y={y - 13} width={58} height={26} rx={8} fill={color.island} stroke={fill.ring} />
            <text x={ux + 63} y={y + 4} textAnchor="middle" fill={color.text} fontSize="12" fontFamily="ui-monospace, monospace">
              {name}
            </text>
          </g>
        )
      })}
      {/* The combined output: an outline, not a filled pill (a filled white pill reads as a button). */}
      {residual && (
        <>
          <motion.rect x={ux + 20} y={68} width={92} height={28} rx={14} fill={color.island} stroke={color.text} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ ...fade.in, delay: duration.draw }} />
          <text x={ux + 66} y={86} textAnchor="middle" fill={color.text} fontSize="11.5" fontFamily="ui-monospace, monospace">
            {residual.length > 13 ? `${residual.slice(0, 12)}…` : residual}
          </text>
        </>
      )}
    </svg>
  )
}

/** "5k epochs" from the data's epoch axis (or "end" when there is none). */
function xEndFrom(epochs: unknown): string {
  const last = Array.isArray(epochs) ? Number(epochs[epochs.length - 1]) : NaN
  if (!Number.isFinite(last)) return 'end'
  return `${last >= 1000 ? `${+(last / 1000).toFixed(1)}k` : last} epochs`
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
  // The highlighted layers (data.highlight, default the first two) in sky; the rest neutral. Amber only means off track.
  const hot = (data.highlight as number[]) ?? [0, 1]
  const tone = (i: number): string => (hot.includes(i) ? actionTone.diagram : i < 3 ? color.label : color.text)
  return (
    <svg width={W} height={H} className="mx-auto block overflow-visible">
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke={color.hairline} />
      <text x={pad.l} y={H - 6} fill={color.faint} fontSize="10.5">
        {(data.xStart as string) ?? 'start'}
      </text>
      <text x={W - pad.r} y={H - 6} textAnchor="end" fill={color.faint} fontSize="10.5">
        {(data.xEnd as string) ?? xEndFrom(data.epochs)}
      </text>
      {typeof data.yLabel === 'string' && (
        <text x={pad.l - 8} y={pad.t + 8} textAnchor="end" fill={color.faint} fontSize="10.5">
          {data.yLabel}
        </text>
      )}
      {logs.map((row, li) => (
        <g key={li}>
          <motion.path
            d={row.map((v, i) => `${i ? 'L' : 'M'}${x(i, row.length).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}
            fill="none"
            stroke={tone(li)}
            strokeWidth={hot.includes(li) ? 2.2 : 1.5}
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
