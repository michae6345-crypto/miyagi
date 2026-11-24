/**
 * Feature: library. Home v4's small parts, drawn to Adrian's ui-next mock (v4.css, app.css): section heads with a quiet
 * link, hairline rows, thin bars, gray tags, the green check (passed, nothing else), the week's bars and the covers.
 * Neutral everywhere; the only hues on the page are the ask chips (options) and the green of passed and mastered.
 */
import { ChevronRight } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { brand, color, fill, radius2, surface } from '../../../core/theme'
import type { CoverKind, WeekBar } from './data'

/** The mock's sizes (app.css / v4.css), in one place. */
export const T = { h1: 32, body: 14, row: 14, meta: 13, sec: 12.5, small: 12.5 } as const
export const hair = color.hairline
export const tagBg = fill.chipHover

/** A section head: 12.5 semibold muted, an optional link on the right ("Browse plans ›"). */
export function Sec({ id, children, link, onLink, first }: { id?: string; children: ReactNode; link?: string; onLink?: () => void; first?: boolean }): ReactNode {
  return (
    <div className="flex items-center" style={{ margin: first ? '8px 0 8px' : '30px 0 10px', fontSize: T.sec, fontWeight: 550, color: color.label, minHeight: 18 }}>
      <h2 id={id} className="m-0" style={{ font: 'inherit' }}>
        {children}
      </h2>
      {link &&
        (onLink ? (
          <button type="button" onClick={onLink} className="ml-auto flex cursor-pointer items-center gap-[3px] rounded-[6px] outline-offset-2 hover:underline focus-visible:outline-2" style={{ fontWeight: 450, color: color.label, outlineColor: color.text, minHeight: 24, marginBlock: -3 }}>
            {link}
            <ChevronRight aria-hidden size={13} strokeWidth={1.8} />
          </button>
        ) : (
          <span className="ml-auto" style={{ fontWeight: 450 }}>
            {link}
          </span>
        ))}
    </div>
  )
}

/** A thin bar: ink, or green when it counts what's mastered. */
export function Bar({ fraction, green, width, label }: { fraction: number; green?: boolean; width?: number; label?: string }): ReactNode {
  const f = Math.max(0, Math.min(1, fraction))
  return (
    <span role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true} className="block shrink-0 overflow-hidden" style={{ width: width ?? '100%', height: 4, borderRadius: 2, background: fill.track }}>
      <span className="block h-full" style={{ width: `${f * 100}%`, borderRadius: 2, background: green ? color.green : color.text }} />
    </span>
  )
}

/** A gray tag (a skill's name): no hue, it's a label, not an option. */
export function Tag({ children }: { children: ReactNode }): ReactNode {
  return (
    <span className="inline-flex max-w-full items-center truncate" style={{ height: 20, padding: '0 6px', borderRadius: 4, fontSize: T.small, lineHeight: '20px', background: tagBg, color: color.text, whiteSpace: 'nowrap' }}>
      {children}
    </span>
  )
}

/** Passed: the green disc with the ink tick. */
export function Check({ size = 16 }: { size?: number }): ReactNode {
  return (
    <span aria-hidden className="inline-grid shrink-0 place-items-center" style={{ width: size, height: size, borderRadius: radius2.round, background: color.green }}>
      <svg viewBox="0 0 12 12" width={size * 0.62} height={size * 0.62} fill="none" stroke={color.onGreen} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
        <path d="m2.6 6.3 2.3 2.3 4.6-4.9" />
      </svg>
    </span>
  )
}

/** Not done yet: a hollow ring, no hue. */
export function Hollow(): ReactNode {
  return <span aria-hidden className="block shrink-0" style={{ width: 16, height: 16, borderRadius: radius2.round, boxShadow: `inset 0 0 0 1.6px ${fill.ring}` }} />
}

export function Chev(): ReactNode {
  return <ChevronRight aria-hidden size={14} strokeWidth={1.8} className="shrink-0" style={{ color: fill.ring }} />
}

/** A full-width row with a hairline above the next one and a quiet hover. Grid columns come from the caller. */
export function RowBtn({ children, onClick, label, cols, minH = 46, style, data }: { children: ReactNode; onClick?: () => void; label?: string; cols: string; minH?: number; style?: CSSProperties; data?: Record<string, string> }): ReactNode {
  const s: CSSProperties = { display: 'grid', gridTemplateColumns: cols, alignItems: 'center', columnGap: 16, minHeight: minH, padding: '0 8px', margin: '0 -8px', borderRadius: 6, fontSize: T.row, textAlign: 'left', width: 'calc(100% + 16px)', ...style }
  if (!onClick)
    return (
      <div className="mg-h4-row" style={s} {...data}>
        {children}
      </div>
    )
  return (
    <button type="button" aria-label={label} onClick={onClick} className="mg-h4-row cursor-pointer outline-offset-[-2px] hover:bg-(--s-row-hover) focus-visible:outline-2" style={{ ...s, outlineColor: color.text }} {...data}>
      {children}
    </button>
  )
}

/** The rows' hairlines (a row after a row), one rule for the page. */
export const rowCss = `.mg-h4-list > .mg-h4-row + .mg-h4-row { box-shadow: 0 -1px 0 ${hair}; } .mg-h4-list > .mg-h4-row:hover + .mg-h4-row, .mg-h4-list > .mg-h4-row:hover { box-shadow: none; }`

/** A rail row: one line, a name and a quiet value. */
export function RailRow({ icon: I, children, right, onClick, label, tall }: { icon?: ReactNode; children: ReactNode; right?: ReactNode; onClick?: () => void; label?: string; tall?: boolean }): ReactNode {
  const lead = I ?? null
  const inner = (
    <>
      {lead}
      <span className="min-w-0 flex-1 truncate text-left" style={{ fontWeight: 520, color: color.text }}>
        {children}
      </span>
      {right}
    </>
  )
  const s: CSSProperties = { display: 'flex', alignItems: 'center', gap: 10, minHeight: tall ? 48 : 33, fontSize: 13.5, width: '100%' }
  return onClick ? (
    <button type="button" aria-label={label} onClick={onClick} className="mg-h4-row cursor-pointer rounded-[6px] outline-offset-2 focus-visible:outline-2" style={{ ...s, outlineColor: color.text }}>
      {inner}
    </button>
  ) : (
    <div className="mg-h4-row" style={s}>
      {inner}
    </div>
  )
}

export const muted: CSSProperties = { color: color.label, fontSize: T.meta, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }

/** The week: seven plain bars, today in ink, the others a quiet gray, a value over each day that has one. */
export function WeekChart({ bars, unit }: { bars: WeekBar[]; unit: string }): ReactNode {
  const W = 284
  const H = 96
  const base = 70
  const top = 16
  const bw = 26
  const gap = (W - 7 * bw) / 6
  const max = Math.max(1, ...bars.map((b) => b.value))
  return (
    <svg role="img" aria-label={`This week: ${bars.map((b) => `${b.name} ${b.value} ${unit}`).join(', ')}`} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ maxWidth: W }}>
      <path d={`M0 ${base}H${W}`} stroke={surface.border} />
      {bars.map((b, i) => {
        const x = i * (bw + gap)
        const h = (b.value / max) * (base - top)
        return (
          <g key={i}>
            {b.value > 0 ? (
              <path d={`M${x} ${base}V${base - h + 3}a3 3 0 0 1 3-3h${bw - 6}a3 3 0 0 1 3 3V${base}z`} fill={b.today ? color.text : fill.ring} />
            ) : (
              <rect x={x} y={base - 2} width={bw} height={2} fill={fill.track} />
            )}
            {b.value > 0 && (
              <text x={x + bw / 2} y={base - h - 5} textAnchor="middle" style={{ fontSize: 11.5, fontWeight: b.today ? 600 : 550, fill: b.today ? color.text : color.label }}>
                {b.value}
              </text>
            )}
            <text x={x + bw / 2} y={base + 17} textAnchor="middle" style={{ fontSize: 11.5, fontWeight: b.today ? 600 : 400, fill: b.today ? color.text : color.faint }}>
              {b.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/** A cover's line grays (ink at fixed alphas, on the dark editor or on paper): named once, not inline. */
const COVER_LINE = { onDark: 'rgba(255,255,255,.78)', softOnDark: 'rgba(255,255,255,.34)', floorOnDark: 'rgba(255,255,255,.08)', onPaper: 'rgba(40,38,33,.55)', softOnPaper: 'rgba(40,38,33,.22)' } as const

/**
 * A cover: a small neutral drawing of the tool (16:9), never a photo or a hue. Code covers are dark like an editor,
 * the rest are paper; the lines are grays so the page keeps its two colors (ink and the green of passed).
 */
export function Cover({ kind, width, radius = 8 }: { kind: CoverKind; width: number | string; radius?: number }): ReactNode {
  const dark = kind === 'code' || kind === 'net' || kind === 'term' || kind === 'mug'
  const bg = dark ? brand.ink : brand.surface
  const ink = dark ? COVER_LINE.onDark : COVER_LINE.onPaper
  const soft = dark ? COVER_LINE.softOnDark : COVER_LINE.softOnPaper
  let art: ReactNode = null
  if (kind === 'code' || kind === 'term')
    art = (
      <g strokeLinecap="round" strokeWidth={5}>
        {[
          [44, 92],
          [58, 120],
          [72, 104],
          [58, 136],
          [44, 70],
          [58, 112],
          [72, 96]
        ].map(([x, w], i) => (
          <path key={i} d={`M${x} ${26 + i * 15}H${x + w}`} stroke={i % 3 === 0 ? ink : soft} />
        ))}
      </g>
    )
  else if (kind === 'net') {
    // 3, 5, 3 nodes, every node wired to the next layer: centered in the 200 x 112.5 frame.
    const cols: Array<[number, number[]]> = [
      [62, [36, 56, 76]],
      [100, [20, 38, 56, 74, 92]],
      [138, [36, 56, 76]]
    ]
    art = (
      <g>
        {cols.slice(0, 2).flatMap(([x1, ys1], ci) => ys1.flatMap((y1) => cols[ci + 1][1].map((y2) => <path key={`${ci}-${y1}-${y2}`} d={`M${x1} ${y1}L${cols[ci + 1][0]} ${y2}`} stroke={soft} strokeWidth={1} />)))}
        {cols.flatMap(([x, ys]) => ys.map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r={5.5} fill={brand.surface} />))}
      </g>
    )
  } else if (kind === 'plot')
    art = (
      <g fill="none">
        <path d="M24 92H176M24 92V20" stroke={soft} strokeWidth={1.2} />
        <path d="M28 84l10-4 8 2 10-8 9 3 10-9 9 2 10-10 9 1 10-9 10 2 10-11 9 2 10-9" stroke={ink} strokeWidth={1.6} />
      </g>
    )
  else if (kind === 'table' || kind === 'nb')
    art = (
      <g strokeLinecap="round" strokeWidth={kind === 'nb' ? 2 : 3}>
        {kind === 'nb' ? (
          <>
            <path d="M24 26H110" stroke={ink} />
            <path d="M24 36H80" stroke={soft} />
            <path d="M24 74c18-28 34-28 52 0s34 28 52 0 34-28 48-8" stroke={ink} fill="none" />
          </>
        ) : (
          [0, 1, 2, 3, 4, 5].flatMap((r) => [0, 1, 2, 3].map((c) => <path key={`${r}-${c}`} d={`M${24 + c * 40} ${20 + r * 14}H${50 + c * 40}`} stroke={r === 0 ? ink : soft} />))
        )}
      </g>
    )
  else if (kind === 'mug')
    art = (
      <g>
        <path d="M0 92L60 66M200 92L140 66M100 66V112M40 112L80 66M160 112L120 66M0 76H200" stroke={COVER_LINE.floorOnDark} />
        <path d="M70 34h52v44a10 10 0 0 1-10 10H80a10 10 0 0 1-10-10z" fill={brand.surface2} />
        <ellipse cx={96} cy={34} rx={26} ry={6} fill={brand.inkFaint} />
        <path d="M122 44h6a12 12 0 0 1 0 24h-6" fill="none" stroke={brand.surface2} strokeWidth={6} />
      </g>
    )
  else if (kind === 'cad')
    art = (
      <g fill="none" stroke={ink} strokeWidth={1.4}>
        <path d="M54 78l52-22 46 16-52 22z" fill={brand.surface} />
        <path d="M54 78v8l46 16v-8M100 102l52-22v-8" />
        <ellipse cx={82} cy={78} rx={6} ry={3} />
        <ellipse cx={118} cy={72} rx={6} ry={3} />
        <path d="M60 46l62-16M60 40v12M122 24v12" stroke={soft} />
      </g>
    )
  return (
    <span aria-hidden className="relative block shrink-0 overflow-hidden" style={{ width, aspectRatio: '16 / 9', borderRadius: radius, background: bg, boxShadow: `inset 0 0 0 1px ${hair}` }}>
      <svg viewBox="0 0 200 112.5" preserveAspectRatio="xMidYMid slice" className="block h-full w-full">
        {art}
      </svg>
    </span>
  )
}
