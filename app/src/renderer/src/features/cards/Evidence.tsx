/**
 * The off-track card's evidence panel (layout C, the right column). Two columns, yours | expected, built from
 * whatever the payload has, in this order:
 *   1. the diff, as code: "{file} · L{line}" on its caption, each side kept as written (never wrapped; a long
 *      line scrolls sideways), and the lines only the expected side has highlighted
 *   2. each failing check that has a real value of yours (not status text like "not seen in Code") and doesn't
 *      just repeat the diff: its label, then your value | the expected one (read from the label)
 *   3. the metric curve: a monochrome sparkline (yours white, tutorial faint) with both end values
 * No color at all (no pastel, no status hue): values in color.text, headers and labels in color.faint.
 */
import type { CSSProperties, ReactNode } from 'react'
import type { CheckItem, Offtrack } from '../../core/lesson'
import { color, fill } from '../../core/theme'
import { Curve, fmt, plotArray, plotPoints, type Line } from './Curve'
import { useSeries } from './store'

const PAD = 12
const GAP = 12
/** A code cell reaches this far into the gutter on each side, so a highlighted line has room around its text. */
const BLEED = 4

const thinScroll: CSSProperties = { scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }

const PREFIX = /^\s*(yours|you|got|now)\b\s*[:=]?\s*/i
/** Unprefixed details that read as a value: a digit or a code character, or a bare literal. */
const CODEY = /[\d=()[\]{}<>"`_]|\.(?=\S)/
const LITERAL = /^(true|false|none|null|nan|undefined|inf)$/i

/**
 * Your value from a check's detail: "yours 2.50e-1" → "2.50e-1", "yours 1" → "1", "2.5" → "2.5". Status text
 * ("not seen in Code", "rerunning") is not a value: undefined.
 */
export function yoursValue(detail?: string): string | undefined {
  const d = (detail ?? '').trim()
  if (!d) return undefined
  const prefix = d.match(PREFIX)
  if (prefix) return d.slice(prefix[0].length).trim() || undefined
  return CODEY.test(d) || LITERAL.test(d) ? d : undefined
}

/**
 * What a check wants, read from its label: a comparison ("Loss < 1e-2" → "< 1e-2"), else the label's last
 * standalone number ('"the" appears 1,804 times' → "1,804"), else undefined.
 */
export function expectedValue(label: string): string | undefined {
  const cmp = label.match(/(<=|>=|==|!=|≤|≥|<|>|=)\s*([^<>=≤≥]+)$/)
  if (cmp) return `${cmp[1]} ${cmp[2].trim()}`
  const nums = label.match(/(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?(?![\w])/gi)
  return nums?.length ? nums[nums.length - 1] : undefined
}

const norm = (s: string): string => s.replace(/\s+/g, ' ').trim()

/** A check row worth showing: your value is known and the row doesn't just repeat the diff. */
type Row = { id: string; label: string; yours: string; expected?: string }
function checkRows(failing: CheckItem[], diff: Offtrack['diff']): Row[] {
  // The diff's code, whole and line by line: a check whose value is already in it adds nothing.
  const inDiff = new Set(diff ? [diff.yours, diff.expected, ...diff.yours.split(/\r?\n/), ...diff.expected.split(/\r?\n/)].map(norm).filter(Boolean) : [])
  const rows: Row[] = []
  for (const c of failing) {
    const yours = yoursValue(c.detail)
    if (!yours) continue
    const expected = expectedValue(c.label)
    if (inDiff.has(norm(yours)) || (expected && inDiff.has(norm(expected)))) continue
    rows.push({ id: c.id, label: c.label, yours, expected })
  }
  return rows
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

/** A section caption (the file, a check's label, the metric) above its yours | expected pair. */
function Label({ children, title }: { children: ReactNode; title?: string }): ReactNode {
  return (
    <div className="col-span-2 mt-[10px] truncate font-sans text-[11px]" style={{ color: color.faint }} title={title}>
      {children}
    </div>
  )
}

function Cell({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className="min-w-0 truncate" style={{ color: color.text }} title={typeof children === 'string' ? children : undefined}>
      {children}
    </div>
  )
}

/** One side of the diff as written: whitespace kept, never wrapped (a long line scrolls sideways); `mark` highlights a line. */
function Code({ text, mark }: { text: string; mark?: (line: string) => boolean }): ReactNode {
  return (
    <div data-code className="min-w-0 overflow-x-auto" style={{ ...thinScroll, marginInline: -BLEED }}>
      <div className="w-max min-w-full whitespace-pre">
        {text.split(/\r?\n/).map((l, i) => {
          const hit = mark?.(l) ?? false
          return (
            <div key={i} data-mark={hit || undefined} className="rounded-[4px]" style={{ paddingInline: BLEED, background: hit ? fill.highlight : undefined }}>
              {l || ' '}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Null when the payload has no evidence: the left column then takes the whole card. */
export function Evidence({ o, failing, width }: { o: Offtrack; failing: CheckItem[]; width: number }): ReactNode {
  const spark = useSpark(o)
  const rows = checkRows(failing, o.diff)
  if (!o.diff && rows.length === 0 && !spark) return null
  const diff = o.diff
  const where = diff && [diff.file, diff.line ? `L${diff.line}` : undefined].filter(Boolean).join(' · ')
  // Highlight only what the expected side adds: its lines that yours doesn't have.
  const yoursLines = new Set(diff ? diff.yours.split(/\r?\n/).map(norm) : [])
  const added = (l: string): boolean => norm(l) !== '' && !yoursLines.has(norm(l))
  return (
    <div data-evidence className="shrink-0 rounded-[14px] font-mono text-[12px] leading-[17px]" style={{ background: fill.field, width, padding: PAD }}>
      <div className="grid grid-cols-2" style={{ columnGap: GAP, rowGap: 2 }}>
        <Head>yours</Head>
        <Head>expected</Head>

        {diff && (
          <>
            {where ? <Label title={where}>{where}</Label> : <div className="col-span-2 h-[6px]" />}
            <Code text={diff.yours} />
            <Code text={diff.expected} mark={added} />
          </>
        )}

        {rows.map((r) => (
          <div key={r.id} className="contents" data-evidence-check>
            <Label title={r.label}>{r.label}</Label>
            <Cell>{r.yours}</Cell>
            <Cell>{r.expected ?? ''}</Cell>
          </div>
        ))}

        {spark && (
          <>
            {spark.name && <Label title={spark.name}>{spark.name}</Label>}
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
