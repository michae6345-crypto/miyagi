/**
 * The off-track card's evidence panel (layout C, the right column). One table, yours | expected, built from
 * whatever the payload has, in this order:
 *   1. the diff, as code (yours with "· L{line}" in faint)
 *   2. each failing check: its label, then your value (its detail) | the expected one (read from the label, or —)
 *   3. the metric curve: a monochrome sparkline (yours white, tutorial faint) with both end values
 * No color at all (no pastel, no status hue): values in color.text, headers and labels in color.faint.
 */
import type { ReactNode } from 'react'
import type { CheckItem, Offtrack } from '../../core/lesson'
import { color, fill } from '../../core/theme'
import { Curve, fmt, plotArray, plotPoints, type Line } from './Curve'
import { useSeries } from './store'

const PAD = 12
const GAP = 12

/** "yours 2.50e-1" → "2.50e-1", "yours 1" → "1". */
export function yoursValue(detail?: string): string {
  const v = (detail ?? '').replace(/^\s*(yours|you|got|now)\b\s*[:=]?\s*/i, '').trim()
  return v || '—'
}

/**
 * What a check wants, read from its label: a comparison ("Loss < 1e-2" → "< 1e-2"), else the label's last
 * standalone number ('"the" appears 1,804 times' → "1,804"), else "—".
 */
export function expectedValue(label: string): string {
  const cmp = label.match(/(<=|>=|==|!=|≤|≥|<|>|=)\s*([^<>=≤≥]+)$/)
  if (cmp) return `${cmp[1]} ${cmp[2].trim()}`
  const nums = label.match(/(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?(?![\w])/gi)
  return nums?.length ? nums[nums.length - 1] : '—'
}

/**
 * The curve as a sparkline: live `metric` events when there are any (tutorial = runId "tutorial"), else both
 * lines from the payload's optional `curve` (never mixed: they may not share units). End values only for live
 * data (the payload's arrays are plot units, not values).
 */
function useSpark(o: Offtrack): { lines: Line[]; name?: string; yours?: string; tutorial?: string; at?: number } | undefined {
  const { name, before: run, tutorial } = useSeries(o.curve?.label)
  const live = run && run.points.length > 1 ? run : undefined
  const yours = live ? plotPoints(live.points) : o.curve ? plotArray(o.curve.yours) : []
  if (yours.length < 2) return undefined
  const ref = live ? (tutorial && tutorial.length > 1 ? plotPoints(tutorial) : []) : o.curve ? plotArray(o.curve.tutorial) : []
  return {
    lines: [
      { key: 'yours', pts: yours, stroke: color.text },
      { key: 'tutorial', pts: ref, stroke: color.faint, reference: true }
    ],
    name: live ? name : o.curve?.label,
    yours: live ? fmt(live.points[live.points.length - 1].value) : undefined,
    tutorial: live && tutorial && tutorial.length > 1 ? fmt(tutorial[tutorial.length - 1].value) : undefined,
    at: live?.at
  }
}

function Head({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="font-sans text-[11px] font-medium" style={{ color: color.faint }}>
      {children}
    </div>
  )
}

/** A row label across both columns. */
function Label({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="col-span-2 mt-[10px] truncate font-sans text-[11px]" style={{ color: color.faint }} title={typeof children === 'string' ? children : undefined}>
      {children}
    </div>
  )
}

function Cell({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="min-w-0 whitespace-pre-wrap [overflow-wrap:anywhere]" style={{ color: color.text }}>
      {children}
    </div>
  )
}

/** Null when the payload has no evidence: the left column then takes the whole card. */
export function Evidence({ o, failing, width }: { o: Offtrack; failing: CheckItem[]; width: number }): ReactNode {
  const spark = useSpark(o)
  if (!o.diff && failing.length === 0 && !spark) return null
  return (
    <div data-evidence className="shrink-0 rounded-[14px] font-mono text-[12px] leading-[17px]" style={{ background: fill.field, width, padding: PAD }}>
      <div className="grid grid-cols-2" style={{ columnGap: GAP, rowGap: 2 }}>
        <Head>yours</Head>
        <Head>expected</Head>

        {o.diff && (
          <>
            {o.diff.file && <Label>{o.diff.file}</Label>}
            <div className="col-span-2 h-[6px]" />
            <Cell>
              {o.diff.yours}
              {o.diff.line ? <span style={{ color: color.faint }}> · L{o.diff.line}</span> : null}
            </Cell>
            <Cell>{o.diff.expected}</Cell>
          </>
        )}

        {failing.map((c) => (
          <div key={c.id} className="contents" data-evidence-check>
            <Label>{c.label}</Label>
            <Cell>{yoursValue(c.detail)}</Cell>
            <Cell>{expectedValue(c.label)}</Cell>
          </div>
        ))}

        {spark && (
          <>
            {spark.name && <Label>{spark.name}</Label>}
            <div className="col-span-2 mt-[6px]" data-curve title={spark.name}>
              <Curve lines={spark.lines} width={width - PAD * 2} height={30} end={{ at: spark.at }} />
            </div>
            {(spark.yours || spark.tutorial) && (
              <>
                <Cell>{spark.yours ?? '—'}</Cell>
                <Cell>{spark.tutorial ?? '—'}</Cell>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
