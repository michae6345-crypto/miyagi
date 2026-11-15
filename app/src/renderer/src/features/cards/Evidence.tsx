/**
 * The off-track card's evidence panel (layout C, the right column). Two columns, yours | expected, built from
 * whatever the payload has, in this order:
 *   1. the diff, as code: "{file} · L{line}" on its caption, each side kept as written (never wrapped; a long
 *      line scrolls sideways, and the edge that hides text stops under a chevron that scrolls it), and the
 *      lines only the expected side has highlighted
 *   2. each failing check that has a real value of yours (not status text like "not seen in Code") and doesn't
 *      just repeat the diff: its label, then your value | the expected one (read from the label)
 *   3. the metric curve: a monochrome sparkline (yours white, tutorial faint) with both end values
 * No color at all (no pastel, no status hue): values in color.text, headers and labels in color.faint.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { CheckItem, Offtrack } from '../../core/lesson'
import { color, fill } from '../../core/theme'
import { isProse, LITERAL, NUMBER, readingValue, readsAsCode } from './code'
import { Curve, fmt, plotArray, plotPoints, type Line } from './Curve'
import { useSeries } from './store'

const PAD = 12
const GAP = 12
/** A code cell reaches this far into the gutter on each side, so a highlighted line has room around its text. */
const BLEED = 4
/** A non-breaking space: an empty row that still takes a line's height. */
const NBSP = String.fromCharCode(0xa0)

const thinScroll: CSSProperties = { scrollbarWidth: 'thin', scrollbarColor: `${fill.track} transparent` }

const PREFIX = /^\s*(yours|you|got|now)\b\s*[:=]?\s*/i

/**
 * Your value from a check's detail: "yours 2.50e-1" → "2.50e-1", "yours 1" → "1", "2.5" → "2.5", the engine's
 * "loss 0.25 at step 300, need < 0.01" → "0.25". Status text is never a value, even when it names a file or
 * holds a digit ("not in weather.py yet", "not seen in Code", "missing", "exited with code 1"): undefined.
 */
export function yoursValue(detail?: string): string | undefined {
  const d = (detail ?? '').trim()
  const prefix = d.match(PREFIX)
  const rest = prefix ? d.slice(prefix[0].length).trim() : d
  if (!rest) return undefined
  const reading = readingValue(rest)
  if (reading) return reading
  if (NUMBER.test(rest) || LITERAL.test(rest)) return rest
  if (isProse(rest)) return undefined
  // "yours …" says it's a value; without the prefix it has to read as code on its own.
  return prefix || readsAsCode(rest) ? rest : undefined
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

/** A diff side as code: '' when it's empty or only status ("not in weather.py yet", "(missing)"). Blank end lines go. */
function codeOf(s?: string): string {
  const t = (s ?? '').replace(/^(?:[ \t]*\r?\n)+|(?:\r?\n[ \t]*)+$/g, '')
  const lines = t.split(/\r?\n/).filter((l) => l.trim())
  return lines.length > 0 && !lines.every(isProse) ? t : ''
}

/**
 * The diff's real code: your side and the expected one (a terminal-only fix: its command). Undefined when neither
 * side has any (both empty, or only status text), so the panel never shows an empty or prose-only diff.
 */
type Sides = { yours: string; expected: string; file?: string; line?: number }
function diffSides(diff: Offtrack['diff']): Sides | undefined {
  if (!diff) return undefined
  const yours = codeOf(diff.yours)
  const expected = codeOf(diff.expected) || codeOf(diff.command)
  return yours || expected ? { yours, expected, file: diff.file, line: diff.line } : undefined
}

/** A check row worth showing: your value is known and the row doesn't just repeat the diff. */
type Row = { id: string; label: string; yours: string; expected?: string }
function checkRows(failing: CheckItem[], diff: Sides | undefined): Row[] {
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

/** At an edge that hides code: the chevron's strip, with no text under it. */
const CUE = 14
/** Mask alpha, not a visible color: opaque shows the text, transparent hides it. */
const SHOW = 'black'
const HIDE = 'transparent'

/**
 * A hard cut at each edge that hides code: an alpha mask on the scroller with hard stops (no fade: BRAND.md, no
 * gradients), so it draws no color and stays put while the code scrolls under it. The text stops a chevron's width
 * from the edge, so the glyph never sits on text. Undefined when the whole line fits.
 */
function edgeMask(left: boolean, right: boolean): string | undefined {
  if (!left && !right) return undefined
  const start = left ? `${HIDE} ${CUE}px, ${SHOW} ${CUE}px` : `${SHOW} 0`
  const end = right ? `${SHOW} calc(100% - ${CUE}px), ${HIDE} calc(100% - ${CUE}px)` : `${SHOW} 100%`
  return `linear-gradient(to right, ${start}, ${end})`
}

/** Which edges of a sideways scroller hide text, and the height its scrollbar takes (0 for overlay scrollbars). */
type Edges = { left: boolean; right: boolean; bar: number }
const FITS: Edges = { left: false, right: false, bar: 0 }

/** The chevron on an edge that hides code: it scrolls that way by about a column. */
function Chevron({ side, bar, onClick }: { side: 'left' | 'right'; bar: number; onClick: () => void }): ReactNode {
  const I = side === 'left' ? ChevronLeft : ChevronRight
  return (
    <motion.button
      type="button"
      data-scroll-cue={side}
      aria-label={side === 'left' ? 'Scroll back' : 'Scroll to see the rest'}
      className="absolute top-0 flex cursor-pointer items-center justify-center"
      style={{ ...(side === 'left' ? { left: 0 } : { right: 0 }), bottom: bar, width: CUE, color: color.faint }}
      whileHover={{ color: color.text }}
      transition={{ duration: 0.12 }}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      <I size={12} strokeWidth={2} />
    </motion.button>
  )
}

/**
 * One side of the diff as written: whitespace kept, never wrapped (a long line scrolls sideways); `mark` highlights
 * a line. The scrollbar's room is always kept (its track is transparent), so a long line never changes the height.
 * A line wider than the column is never cut without a cue (Michael, desktop test 3: macOS overlay scrollbars stay
 * hidden until you scroll, so the code just stopped at the edge): the edge that hides text is cut clean under a
 * chevron that scrolls it, and hovering shows the whole side as a tooltip. Trackpad and shift-wheel scroll as usual.
 */
function Code({ text, mark }: { text: string; mark?: (line: string) => boolean }): ReactNode {
  const ref = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState<Edges>(FITS)
  const reduce = useReducedMotion()
  const measure = useCallback((): void => {
    const el = ref.current
    if (!el) return
    // 1px of slack: scrollLeft is fractional on a Retina display.
    const left = el.scrollLeft > 1
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 1
    const bar = Math.max(0, el.offsetHeight - el.clientHeight)
    setEdges((e) => (e.left === left && e.right === right && e.bar === bar ? e : { left, right, bar }))
  }, [])
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    measure()
    // The column's width and the code's (a new diff, a font that lands late) both decide what's hidden.
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => ro.disconnect()
  }, [measure, text])
  const scroll = (dir: 1 | -1) => (): void => {
    const el = ref.current
    el?.scrollBy({ left: dir * Math.max(CUE * 2, el.clientWidth - CUE * 2), behavior: reduce ? 'auto' : 'smooth' })
  }
  const hidden = edges.left || edges.right
  const mask = edgeMask(edges.left, edges.right)
  return (
    <div className="relative min-w-0" style={{ marginInline: -BLEED }}>
      <div
        ref={ref}
        data-code
        data-overflow={hidden ? [edges.left && 'left', edges.right && 'right'].filter(Boolean).join(' ') : undefined}
        className="overflow-x-scroll"
        style={{ ...thinScroll, maskImage: mask, WebkitMaskImage: mask }}
        title={hidden ? text : undefined}
        onScroll={measure}
      >
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
      {edges.left && <Chevron side="left" bar={edges.bar} onClick={scroll(-1)} />}
      {edges.right && <Chevron side="right" bar={edges.bar} onClick={scroll(1)} />}
    </div>
  )
}

/** What the panel has to show: the diff's real code, the check rows with a real value, the curve. */
function useContent(o: Offtrack, failing: CheckItem[]): { diff?: Sides; rows: Row[]; spark: ReturnType<typeof useSpark> } {
  const spark = useSpark(o)
  const diff = diffSides(o.diff)
  return { diff, rows: checkRows(failing, diff), spark }
}

/**
 * Whether the off-track card has an evidence panel at all: real code in the diff, a check with a real value, or
 * the curve. False = Evidence renders nothing and the card should take its one-column layout. Status text alone
 * ("not in weather.py yet", "not seen in Code") is no evidence.
 */
export function useHasEvidence(o: Offtrack, failing: CheckItem[]): boolean {
  const { diff, rows, spark } = useContent(o, failing)
  return !!diff || rows.length > 0 || !!spark
}

/**
 * Null when the payload has no evidence (see useHasEvidence): the left column then takes the whole card.
 * `reserveDiff`: while the off-track has no diff yet, keep the room a one-line diff takes (an invisible caption +
 * code row at the bottom), so the card doesn't grow when the diff arrives (it usually comes with the level-3 hint).
 */
export function Evidence({ o, failing, width, reserveDiff }: { o: Offtrack; failing: CheckItem[]; width: number; reserveDiff?: boolean }): ReactNode {
  const { diff, rows, spark } = useContent(o, failing)
  if (!diff && rows.length === 0 && !spark) return null
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

        {reserveDiff && !o.diff && (
          <div className="invisible contents" aria-hidden data-reserve>
            <Label>{NBSP}</Label>
            <Code text={NBSP} />
            <Code text={NBSP} />
          </div>
        )}
      </div>
    </div>
  )
}
