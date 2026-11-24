/**
 * Feature: plans. A plan's or lesson's picture (the mock's thumbnails): a few flat shapes per kind of work, drawn in
 * SVG so they scale from a 72 px row icon to a 340 px card. Neutral only (brand: pastels are for options, so the
 * mock's colored code lines are gray here); no gradients, no glow. Dark art sits on ink, light art on the row fill.
 */
import type { ReactNode } from 'react'
import { alpha, brand, color, radius2, surface } from '../../core/theme'
import { planById, type Plan } from './catalog'

export type Art = 'code' | 'mug' | 'plate' | 'web' | 'table' | 'plot' | 'network' | 'terminal'

const DARK: ReadonlySet<Art> = new Set(['code', 'mug', 'network', 'terminal'])

/** A plan's picture, from its tool and topic. */
export function artFor(p: Plan | undefined): Art {
  if (!p) return 'code'
  if (p.topic === '3d' || p.tool.id === 'blender' || p.tool.id === 'unity' || p.tool.id === 'godot') return 'mug'
  if (p.topic === 'cad') return 'plate'
  if (p.topic === 'ai') return 'network'
  if (p.id === 'plotting' || p.tool.id === 'rstudio') return 'plot'
  if (p.topic === 'data' || p.tool.id === 'excel' || p.tool.id === 'sheets') return 'table'
  if (p.tool.id === 'terminal' || p.tool.id === 'docker') return 'terminal'
  if (/javascript|html|react|typescript|figma/.test(p.id) || p.topic === 'design') return 'web'
  return 'code'
}
export const artForId = (id: string): Art => (isArt(id) ? id : artFor(planById(id)))
const isArt = (s: string): s is Art => ['code', 'mug', 'plate', 'web', 'table', 'plot', 'network', 'terminal'].includes(s)

/** On ink: the paper at an alpha (the art's strokes). */
const lit = (a: number): string => alpha(brand.paper, a)
/** On the row fill: the text color at an alpha (ink in light, paper in dark), so the art reads in both themes. */
const ink = (a: number): string => `color-mix(in srgb, currentColor ${Math.round(a * 100)}%, transparent)`

function Art({ art }: { art: Art }): ReactNode {
  switch (art) {
    case 'code':
      return (
        <g strokeLinecap="round" strokeWidth={6}>
          <rect x={0} y={0} width={44} height={180} fill={lit(0.04)} />
          {[
            [70, 30, 120],
            [90, 48, 190],
            [110, 66, 170],
            [110, 84, 230],
            [70, 102, 140],
            [70, 120, 200],
            [110, 138, 200],
            [90, 156, 130]
          ].map(([x, y, x2], i) => (
            <line key={i} x1={x} y1={y} x2={x2} y2={y} stroke={lit([0.55, 0.38, 0.7, 0.45, 0.5, 0.35, 0.62, 0.4][i])} />
          ))}
        </g>
      )
    case 'terminal':
      return (
        <g strokeLinecap="round" strokeWidth={6}>
          {[
            [30, 30, 150],
            [30, 52, 210],
            [30, 74, 120],
            [30, 96, 180],
            [30, 118, 140],
            [30, 140, 90]
          ].map(([x, y, x2], i) => (
            <line key={i} x1={x} y1={y} x2={x2} y2={y} stroke={lit(i % 2 ? 0.4 : 0.75)} />
          ))}
        </g>
      )
    case 'mug':
      return (
        <g>
          {[0, 1, 2, 3, 4].map((i) => (
            <line key={`h${i}`} x1={0} y1={120 + i * 14} x2={320} y2={120 + i * 14} stroke={lit(0.08)} strokeWidth={1.5} />
          ))}
          {[-3, -2, -1, 0, 1, 2, 3].map((i) => (
            <line key={`v${i}`} x1={160 + i * 22} y1={120} x2={160 + i * 70} y2={180} stroke={lit(0.08)} strokeWidth={1.5} />
          ))}
          <path d="M186 78 h14 a22 22 0 0 1 0 44 h-14" fill="none" stroke={lit(0.82)} strokeWidth={10} />
          <path d="M122 62 v62 a32 10 0 0 0 66 0 v-62 z" fill={lit(0.86)} />
          <ellipse cx={155} cy={62} rx={33} ry={10} fill={lit(0.92)} />
          <ellipse cx={155} cy={63} rx={27} ry={7} fill={lit(0.42)} />
        </g>
      )
    case 'plate':
      return (
        <g fill="none" stroke={ink(0.75)} strokeWidth={2.5} strokeLinejoin="round">
          <path d="M96 104 L178 80 L252 104 L170 128 Z" fill={ink(0.06)} />
          <path d="M96 104 v12 L170 140 v-12 M170 140 L252 116 v-12" fill={ink(0.12)} />
          <ellipse cx={142} cy={104} rx={10} ry={4.5} />
          <ellipse cx={206} cy={98} rx={10} ry={4.5} />
          <path d="M100 66 L196 40 M100 58 v16 M196 32 v16" stroke={ink(0.5)} strokeWidth={1.6} />
          <text x={146} y={44} fontSize={12} fill={ink(0.6)} stroke="none" transform="rotate(-15 146 44)">
            60
          </text>
        </g>
      )
    case 'web':
      return (
        <g>
          <rect x={0} y={0} width={320} height={20} fill={ink(0.05)} />
          <circle cx={14} cy={10} r={3.5} fill={ink(0.2)} />
          <circle cx={26} cy={10} r={3.5} fill={ink(0.2)} />
          <g strokeLinecap="round">
            <line x1={36} y1={56} x2={132} y2={56} stroke={ink(0.8)} strokeWidth={10} />
            <line x1={36} y1={80} x2={190} y2={80} stroke={ink(0.22)} strokeWidth={5} />
            <line x1={36} y1={94} x2={168} y2={94} stroke={ink(0.22)} strokeWidth={5} />
            <line x1={42} y1={124} x2={68} y2={124} stroke={ink(0.8)} strokeWidth={14} />
          </g>
          <rect x={218} y={42} width={64} height={90} rx={6} fill={ink(0.05)} />
        </g>
      )
    case 'table':
      return (
        <g strokeLinecap="round">
          <rect x={0} y={0} width={320} height={24} fill={ink(0.05)} />
          {[0, 1, 2, 3, 4, 5].map((r) => (
            <g key={r}>
              {r > 0 && <line x1={0} y1={24 + r * 26 - 13} x2={320} y2={24 + r * 26 - 13} stroke={ink(0.06)} strokeWidth={1} />}
              {[22, 98, 172, 246].map((x, c) => (
                <line key={c} x1={x} y1={r === 0 ? 12 : 24 + r * 26} x2={x + [44, 40, 34, 48][(c + r) % 4]} y2={r === 0 ? 12 : 24 + r * 26} stroke={ink(r === 0 ? 0.45 : 0.2)} strokeWidth={5} />
              ))}
            </g>
          ))}
        </g>
      )
    case 'plot':
      return (
        <g fill="none">
          <path d="M44 24 V150 H292" stroke={ink(0.35)} strokeWidth={1.6} />
          <polyline points="56,140 70,130 84,136 100,122 114,128 130,114 146,118 160,104 176,108 192,94 208,98 222,84 238,88 252,70 266,74 280,58" stroke={ink(0.8)} strokeWidth={2.6} strokeLinejoin="round" />
          {[
            [76, 124],
            [102, 140],
            [134, 118],
            [168, 112],
            [200, 88],
            [232, 76],
            [262, 60],
            [286, 66]
          ].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={4} fill={ink(0.4)} />
          ))}
        </g>
      )
    case 'network': {
      const L = [
        [100, [54, 90, 126]],
        [160, [36, 72, 108, 144]],
        [220, [70, 110]]
      ] as const
      return (
        <g>
          {L.slice(0, 2).flatMap(([x, ys], li) => ys.flatMap((y) => L[li + 1][1].map((y2) => <line key={`${x}-${y}-${y2}`} x1={x} y1={y} x2={L[li + 1][0]} y2={y2} stroke={lit(0.22)} strokeWidth={1.2} />)))}
          {L.flatMap(([x, ys]) => ys.map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r={9} fill={lit(0.92)} />))}
        </g>
      )
    }
  }
}

/** The picture. `w` sets the width; height follows the mock's 16:9-ish card (or `h`). */
export function Thumb({ art, w, h, radius }: { art: Art; w: number | string; h?: number; radius?: number }): ReactNode {
  const dark = DARK.has(art)
  return (
    <span
      aria-hidden
      className="relative block shrink-0 overflow-hidden"
      style={{
        width: w,
        height: h,
        aspectRatio: h ? undefined : '16 / 9',
        borderRadius: radius ?? radius2.control,
        background: dark ? brand.ink : surface.row,
        boxShadow: `inset 0 0 0 1px ${surface.border}`,
        color: color.text
      }}
    >
      <svg viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full">
        <Art art={art} />
      </svg>
    </span>
  )
}
