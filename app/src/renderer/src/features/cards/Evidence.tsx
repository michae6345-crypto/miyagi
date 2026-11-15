/**
 * The off-track card's evidence panel (layout C, the right column), built from whatever the payload has that is
 * real code or a real value (status text like "not in weather.py yet" is neither; with nothing left, no panel):
 *   1. the diff, one column (Michael, review A5: two side-by-side columns couldn't be read): "{file} · L{line}"
 *      on its caption, your lines (−) then the expected ones (+), lines both have as faint context. A line and its
 *      changed version are paired and only what changed is marked (`.json()`, `raise_for_status()`): in
 *      color.text on a neutral chip, the rest faint; a removed part is also struck. Never wrapped: a long line
 *      scrolls sideways, and the edge that hides text stops under a chevron that scrolls it.
 *   2. each failing check that has a real value of yours and doesn't just repeat the diff: its label, then
 *      yours | expected (read from the label), two columns
 *   3. the metric curve: a monochrome sparkline (yours white, tutorial faint) with both end values
 * No color at all (no pastel, no status hue, no red or green for − / +): values in color.text, headers and labels
 * in color.faint.
 */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useCallback, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useLesson, type CheckItem, type Offtrack } from '../../core/lesson'
import { color, fill } from '../../core/theme'
import { diffLines, fitRows, isProse, LITERAL, NUMBER, readingValue, readsAsCode, type DiffRow } from './code'
import { Curve, fmt, plotArray, plotPoints, type Line } from './Curve'
import { useSeries } from './store'
import { onMessage } from '../../core/bus'

/** When the current off-track arrived: a live series that stopped well before it is an earlier run's, not this error's. */
let offtrackAt = 0
onMessage('offtrack', () => {
  offtrackAt = Date.now()
})
const RECENT_MS = 45_000

/**
 * Michael, test 6: a NameError card showed an earlier run's loss sparkline. The live series is this card's evidence
 * only when the card names a curve, its text mentions the metric, or the series was still moving when it arrived.
 */
function seriesFits(o: Offtrack, name: string | undefined, at: number, last?: number): boolean {
  if (o.curve) return true
  // Michael's 5 AM shoot: the stuck run's card ("Loss is stuck at 0.49", yours 0.4900) ended its sparkline on 9.0e-4,
  // an earlier run's last value. A failing check on this metric that reads a different value means another run.
  if (name && last != null && Number.isFinite(last)) {
    const metric = name.toLowerCase()
    for (const c of useLesson.getState().checks) {
      if (c.status === 'pass' || !`${c.label ?? ''} ${c.detail ?? ''}`.toLowerCase().includes(metric)) continue
      const v = Number(yoursValue(c.detail)?.replace(/,/g, ''))
      if (!Number.isFinite(v)) continue
      const far = Math.abs(v - last) > Math.max(Math.abs(v), Math.abs(last)) * 0.25
      if (far) return false
    }
  }
  // The engine (7863fa6): a crashed run's failing check reads "no loss: the run stopped with an error". This run has no
  // curve, so an older run's points are not evidence for it.
  const none = name && `no ${name.toLowerCase()}`
  if (none && useLesson.getState().checks.some((c) => c.status !== 'pass' && (c.detail ?? '').trim().toLowerCase().startsWith(none))) return false
  const text = `${o.title ?? ''} ${o.body ?? ''} ${o.reason ?? ''}`.toLowerCase()
  if (name && text.includes(name.toLowerCase())) return true
  return at >= offtrackAt - RECENT_MS
}


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
  // "Loss falls below 0.01" → "< 0.01" (the engine's check labels, 7863fa6).
  const word = label.match(/\b(below|under|less than|above|over|more than|at least|at most)\s+(-?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?)\s*$/i)
  if (word) {
    const op: Record<string, string> = { below: '<', under: '<', 'less than': '<', above: '>', over: '>', 'more than': '>', 'at least': '≥', 'at most': '≤' }
    return `${op[word[1].toLowerCase()]} ${word[2]}`
  }
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
  const live = run && run.points.length > 1 && seriesFits(o, name, run.at, run.points[run.points.length - 1]?.value) ? run : undefined
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

/** A column head (yours | expected); `top`: under the diff, so it keeps a section's distance from it. */
function Head({ children, top }: { children: ReactNode; top?: boolean }): ReactNode {
  return (
    <div className={`font-sans text-[11px] font-medium ${top ? 'mt-[12px]' : ''}`} style={{ color: color.faint }}>
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
 * A sideways scroller for code: whitespace kept, never wrapped (a long line scrolls sideways). The scrollbar's room
 * is always kept (its track is transparent), so a long line never changes the height. A line wider than the column
 * is never cut without a cue (Michael, desktop test 3: macOS overlay scrollbars stay hidden until you scroll, so
 * the code just stopped at the edge): the edge that hides text is cut clean under a chevron that scrolls it, and
 * hovering shows the whole of it (`title`) as a tooltip. Trackpad and shift-wheel scroll as usual.
 */
function Scroll({ title, children }: { title: string; children: ReactNode }): ReactNode {
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
  }, [measure, title])
  const scroll = (dir: 1 | -1) => (): void => {
    const el = ref.current
    el?.scrollBy({ left: dir * Math.max(CUE * 2, el.clientWidth - CUE * 2), behavior: reduce ? 'auto' : 'smooth' })
  }
  const hidden = edges.left || edges.right
  const mask = edgeMask(edges.left, edges.right)
  return (
    <div className="relative min-w-0 flex-1">
      <div
        ref={ref}
        data-code
        data-overflow={hidden ? [edges.left && 'left', edges.right && 'right'].filter(Boolean).join(' ') : undefined}
        className="overflow-x-scroll"
        style={{ ...thinScroll, maskImage: mask, WebkitMaskImage: mask }}
        title={hidden ? title : undefined}
        onScroll={measure}
      >
        <div className="w-max min-w-full whitespace-pre">{children}</div>
      </div>
      {edges.left && <Chevron side="left" bar={edges.bar} onClick={scroll(-1)} />}
      {edges.right && <Chevron side="right" bar={edges.bar} onClick={scroll(1)} />}
    </div>
  )
}

/** The sign gutter: − yours, + expected (a real minus, so it isn't read as a hyphen), nothing on context. */
const SIGN: Record<DiffRow['sign'], string> = { '-': '−', '+': '+', ' ': NBSP }
const SIGN_W = 10
/** A diff longer than this keeps the context next to its changes, then the first rows. */
const MAX_ROWS = 12

/**
 * One diff row. Context (both sides have it): faint. A line and its changed version: the rest faint on yours and
 * muted on expected, only the changed part in color.text on a neutral chip (on yours, also struck). A line with
 * no counterpart: yours muted and struck, expected in color.text (with a highlighted row when other rows are
 * around it). `solo`: yours alone (no expected code to compare with), just the lines as written.
 */
function DiffLine({ row, solo, mark }: { row: DiffRow; solo?: boolean; mark?: boolean }): ReactNode {
  const { sign, parts, text } = row
  const removed = sign === '-'
  const lone = sign === '+' && !parts && mark
  const tone = sign === ' ' ? (solo ? color.text : color.faint) : removed ? (parts ? color.faint : color.label) : parts ? color.label : color.text
  return (
    <div
      data-sign={sign === ' ' ? 'same' : removed ? 'removed' : 'added'}
      data-mark={lone || undefined}
      className={`rounded-[4px] ${removed && !parts ? 'line-through' : ''}`}
      style={{ paddingInline: BLEED, color: tone, background: lone ? fill.highlight : undefined }}
    >
      {parts
        ? parts.map((p, k) =>
            p.changed ? (
              <span key={k} data-changed className={`rounded-[3px] ${removed ? 'line-through' : ''}`} style={{ color: removed ? color.label : color.text, background: fill.button }}>
                {p.text}
              </span>
            ) : (
              <span key={k}>{p.text}</span>
            )
          )
        : text || ' '}
    </div>
  )
}

/** The diff as one column: the sign gutter stays put while the code scrolls sideways next to it. */
function DiffView({ rows, more, solo }: { rows: DiffRow[]; more: number; solo?: boolean }): ReactNode {
  const whole = rows.map((r) => (solo ? r.text : `${SIGN[r.sign]} ${r.text}`)).join('\n')
  // Highlight whole new lines only next to other rows (an all-new block needs no highlight).
  const mark = rows.some((r) => r.sign !== '+')
  return (
    <div className="col-span-2 min-w-0" data-diff-view>
      <div className="flex min-w-0" style={{ marginInline: -BLEED }}>
        {!solo && (
          <div aria-hidden className="shrink-0 select-none whitespace-pre" style={{ width: SIGN_W + BLEED, paddingLeft: BLEED, color: color.faint }}>
            {rows.map((r, i) => (
              <div key={i}>{SIGN[r.sign]}</div>
            ))}
          </div>
        )}
        <Scroll title={whole}>
          {rows.map((r, i) => (
            <DiffLine key={i} row={r} solo={solo} mark={mark} />
          ))}
        </Scroll>
      </div>
      {more > 0 && (
        <div className="font-sans text-[11px]" style={{ color: color.faint }}>
          {more} more {more === 1 ? 'line' : 'lines'}
        </div>
      )}
    </div>
  )
}

/** The diff's caption: "{file} · L{line}", and on the right which sign is whose (only the signs it uses). */
function DiffCaption({ where, minus, plus }: { where?: string; minus: boolean; plus: boolean }): ReactNode {
  if (!where && !minus && !plus) return <div className="col-span-2 h-[2px]" />
  return (
    <div className="col-span-2 mb-[2px] flex min-w-0 items-center gap-[10px] font-sans text-[11px]" style={{ color: color.faint }}>
      <span className="min-w-0 flex-1 truncate" title={where}>
        {where}
      </span>
      {minus && <span className="shrink-0">− yours</span>}
      {plus && <span className="shrink-0">+ expected</span>}
    </div>
  )
}

/** A one-line change's rows: what `reserveDiff` keeps room for. */
const RESERVE: DiffRow[] = [
  { sign: '-', text: NBSP },
  { sign: '+', text: NBSP }
]

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
 * `reserveDiff`: while the off-track has no diff yet, keep the room a one-line change takes (an invisible caption
 * and two rows at the bottom), so the card doesn't grow when the diff arrives (it usually comes with the level-3
 * hint).
 */
export function Evidence({ o, failing, width, reserveDiff }: { o: Offtrack; failing: CheckItem[]; width: number; reserveDiff?: boolean }): ReactNode {
  const { diff, rows, spark } = useContent(o, failing)
  const yours = diff?.yours ?? ''
  const expected = diff?.expected ?? ''
  // Yours alone (no expected code): your lines as written, nothing to mark.
  const solo = !!yours && !expected
  const view = useMemo(
    () => fitRows(solo ? yours.split(/\r?\n/).map((text): DiffRow => ({ sign: ' ', text })) : diffLines(yours, expected), MAX_ROWS),
    [yours, expected, solo]
  )
  if (!diff && rows.length === 0 && !spark) return null
  const where = diff && [diff.file, diff.line ? `L${diff.line}` : undefined].filter(Boolean).join(' · ')
  // The yours | expected heads only above the two-column parts (check values, the curve and its end values).
  const pairs = rows.length > 0 || !!spark
  return (
    <div data-evidence className="shrink-0 rounded-[14px] font-mono text-[12px] leading-[17px]" style={{ background: fill.field, width, padding: PAD }}>
      <div className="grid grid-cols-2" style={{ columnGap: GAP, rowGap: 2 }}>
        {diff && (
          <>
            <DiffCaption where={where || undefined} minus={view.rows.some((r) => r.sign === '-')} plus={view.rows.some((r) => r.sign === '+')} />
            <DiffView rows={view.rows} more={view.more} solo={solo} />
          </>
        )}

        {pairs && (
          <>
            <Head top={!!diff}>yours</Head>
            <Head top={!!diff}>expected</Head>
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
            <DiffView rows={RESERVE} more={0} />
          </div>
        )}
      </div>
    </div>
  )
}
