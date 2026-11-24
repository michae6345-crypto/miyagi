/**
 * Feature: shell. The redraft's small shared pieces (Adrian, Nov 21: Michael's brief "fewer boxes, more depth, more
 * pastel, calm copy"). Every page of the home window builds from these, so the pages read as one app:
 *
 *   PANEL       the content surface: one raised layer inset from the window, the sidebar sits on the window itself
 *   PageHeader  the page header every page gets from the shell: the title (and its actions) on the page column
 *   PageColumn  THE page column (the only one): centered in the pane, 720 or 1040 wide with its gutters, top-anchored
 *   PageBody    a PageColumn holding a page's content stack, with an optional 560 `form` measure inside it
 *   CARD        a card on the pane (radius 12)
 *   PageTitle   a title row inside a page (no hairline under it; spacing does the grouping)
 *   SectionHead a quiet section header with an optional right-hand action
 *   StepBar     "Step 4 of 7" as seven short segments: done in ink/white, the current one outlined, never green
 *   Row         a list row that lifts one level on hover (Linear / Notion rows, no border box)
 *   RowChevron  the trailing chevron on a Row that opens something: half strength at rest, full and nudged on hover
 *
 * Sleek and minimal (Adrian, Nov 21: "a lot seems very AI slop-ish"): type, spacing and one raised surface do the work.
 * No icon tiles or tool pills on rows; color stays for options (pastel chips) and passed (green). Tokens only.
 */
import { Check, ChevronRight, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import type { CSSProperties, ReactNode } from 'react'
import { create } from 'zustand'
import { color, fill, layout, radius2, surface, type2, typeScale, v4, v4c, v4type } from '../../core/theme'
import { fade, press, spring } from '../../core/ui/motion'

// ---- the content panel ------------------------------------------------------------------------------------------

/** The gap between the window edge and the raised content panel (the sidebar fills the rest of the window). */
export const PANEL_INSET = layout.pane.inset

/**
 * The content pane (Linear's inverted L): one step lighter than the sidebar, inset 8 from the window's top, right and
 * bottom, radius 12, a faint outline and no shadow in dark (the tone step separates it from the sidebar; light adds a
 * hairline lift). The dot grid (PR #242) stays, quieter, as a halo under the page header that fades out before the
 * content's middle, so cards never sit on noise.
 */
// v4 (Adrian's ui-next mock): the page is flat, the window's own paper (cream in light), no inset pane and no dot grid.
// The keys stay so the spreads elsewhere (a lesson preview's ground, the Progress window) keep working.
export const PANEL: CSSProperties = {
  backgroundColor: v4c.page,
  backgroundImage: 'none',
  backgroundSize: 'auto',
  backgroundPosition: '0 0',
  borderRadius: 0,
  boxShadow: 'none'
}

/**
 * A card on the page (v4: "the only card is Continue"; the ask box and the setup groups use it too): white on cream,
 * radius 12, the mock's e2 lift (a ring and two soft shadows; dark: a white ring and black shadows).
 */
export const CARD: CSSProperties = {
  background: v4c.card,
  borderRadius: v4.radius.card,
  boxShadow: v4c.e2
}

/**
 * The page column's full width (content + both gutters), from core/theme.ts layout.page: 720 (640 of content) for every
 * page, 1040 (960) for the wide one (the Skills grid). Every number of the column lives in layout.page; this file is
 * the only place that turns them into a column, so a page's content and the shell's title share one left edge.
 */
export const COLUMN_W = layout.page.column + 2 * layout.page.gutter
export const WIDE_W = layout.page.wide + 2 * layout.page.gutter
export type ColumnWidth = 'page' | 'wide'
export const COLUMN_MAX: Record<ColumnWidth, number> = { page: COLUMN_W, wide: WIDE_W }
/**
 * `--page-inset`: how far the page column sits in from each side of the pane, set by the shell on every page frame for
 * the header. Zero until the pane is wider than the column, then half the spare room, so the title's left edge is the
 * column's left edge and never moves when you switch pages (it used to jump from x 272 to 656 at full screen).
 * The percentage resolves where the variable is used (the header's padding: the pane's width).
 */
export const pageInset = (w: number = COLUMN_W): string => `max(0px, calc((100% - ${w}px) / 2))`
/**
 * `--page-gutter`: 40, or 24 once the pane is under 760 (layout.page.tightBelow). styles.css switches it with a
 * container query on the page frame (.mg-page-frame, the pane's width), so the header and every column agree.
 */
const GUTTER = `var(--page-gutter, ${layout.page.gutter}px)`

/**
 * THE page column (layout lane, Nov 22: "one shared container for every page"). Centered in the pane (not the window),
 * top-anchored (never centered vertically, even in full screen), capped at 720 (`wide`: 1040) with the house gutters.
 * Its top is layout.page.bodyTop (8) under the shell's header, which with the header's titleGap puts the first section
 * 32 under the title; sections then sit `gap` apart and the page ends layout.page.bottom (64) under its last block.
 * Long text inside it caps at layout.page.form (560) and stays left: the column centers, its text never does.
 *
 * Pages that scroll in the shell's body and pages that scroll inside themselves use it alike: the shell never pads a
 * page's body, so the column always centers in the full pane and its scrollbar stays at the pane's edge.
 *
 * The column's top is `top` and nothing else (a `paddingTop` in `style` is ignored), so the 32 under the title is set
 * in one place. `wide` is the same as `width="wide"`.
 */
export function PageColumn({
  width,
  wide = false,
  gap,
  top = layout.page.bodyTop,
  bottom = layout.page.bottom,
  className = '',
  style,
  children,
  data
}: {
  width?: ColumnWidth
  wide?: boolean
  gap?: number
  top?: number
  bottom?: number
  className?: string
  style?: CSSProperties
  children: ReactNode
  data?: Record<string, string | boolean | undefined>
}): ReactNode {
  const w: ColumnWidth = width ?? (wide ? 'wide' : 'page')
  return (
    <div
      data-page-column={w}
      className={`flex w-full flex-col ${className}`}
      style={{ maxWidth: COLUMN_MAX[w], marginInline: 'auto', paddingInline: GUTTER, paddingBottom: bottom, gap, ...style, paddingTop: top }}
      {...data}
    >
      {children}
    </div>
  )
}

/**
 * A page's content stack on the page column (Settings, Account): sections `gap` apart (40), 64 at the bottom. `width`
 * 'form' keeps the stack at the 560 reading measure, left inside the column (forms and long text never center).
 */
export function PageBody({ children, width = 'column', gap = layout.page.section, style }: { children: ReactNode; width?: 'column' | 'form'; gap?: number; style?: CSSProperties }): ReactNode {
  return (
    <PageColumn gap={gap} style={style} data={{ 'data-page-body': '' }}>
      <div className="flex w-full flex-col" style={{ maxWidth: width === 'form' ? layout.page.form : undefined, gap }}>
        {children}
      </div>
    </PageColumn>
  )
}

export const caption: CSSProperties = { fontSize: type2.xs, lineHeight: '16px', color: color.label }

// ---- headers ----------------------------------------------------------------------------------------------------

/**
 * The header's top padding: the window's top to the title's top is layout.page.top (80; topFull 52 in macOS full
 * screen), less the pane's inset and the half-leading of the 32 px title line in its 36 px row. Handed to styles.css
 * (.mg-page-head) as variables, so the CSS never repeats the numbers.
 */
// v4: the legacy header sits under the shell's 44 px top bar, so its title's top is the v4 page top (44) like PageFrame's.
const TITLE_LEAD = (layout.page.titleRow - parseInt(v4type.title.lineHeight)) / 2
const HEAD_TOP = v4.page.top - TITLE_LEAD
const HEAD_TOP_FULL = v4.page.top - TITLE_LEAD

/**
 * The page header (the shell renders it above every page but Home): the title and the page's own actions, on the same
 * column as the page below it (its left edge is the content's left edge at every width). The strip above the title
 * drags the window; the title's top is 80 from the window's top (52 in full screen), the line Home's bonsai sits on.
 * The title row is 36 tall; the header ends layout.page.titleGap (24) under the title's line, and the page's column
 * starts layout.page.bodyTop (8) below that, so the first section sits 32 under the title on every page.
 */
export function LegacyPageHeader({ title, caption: sub, right }: { title: ReactNode; caption?: ReactNode; right?: ReactNode }): ReactNode {
  return (
    <header
      data-drag
      data-page-header
      data-legacy-header
      className="mg-page-head flex shrink-0 items-center gap-[16px]"
      style={{
        ['--page-head-top' as string]: `${HEAD_TOP}px`,
        ['--page-head-top-full' as string]: `${HEAD_TOP_FULL}px`,
        paddingInline: `calc(var(--page-inset, 0px) + ${GUTTER})`,
        paddingBottom: layout.page.titleGap - TITLE_LEAD
      }}
    >
      {/* 36 tall whatever sits on the right (a search field), so the title's top is the same on every page. */}
      <div className="flex min-w-0 items-center" style={{ minHeight: layout.page.titleRow }}>
        <div className="flex min-w-0 items-baseline gap-[12px]">
          <h1 className="m-0 shrink-0" style={{ ...v4type.title, color: color.text }}>
            {title}
          </h1>
          {sub && (
            <span className="truncate" style={{ ...typeScale.nav, fontWeight: 400, color: color.label }}>
              {sub}
            </span>
          )}
        </div>
      </div>
      {right && (
        <div data-no-drag className="ml-auto flex min-w-0 items-center gap-[12px]">
          {right}
        </div>
      )}
    </header>
  )
}

export function PageTitle({ children, right, sub }: { children: ReactNode; right?: ReactNode; sub?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[36px] items-center gap-[16px]">
      <div className="flex min-w-0 flex-col" style={{ gap: 2 }}>
        <h1 className="m-0 truncate" style={{ ...typeScale.pageTitle, color: color.text }}>
          {children}
        </h1>
        {sub && <span style={{ fontSize: type2.sm, color: color.label }}>{sub}</span>}
      </div>
      {right && <div className="ml-auto flex shrink-0 items-center gap-[10px]">{right}</div>}
    </div>
  )
}

export function SectionHead({ id, children, right }: { id?: string; children: ReactNode; right?: ReactNode }): ReactNode {
  return (
    <div className="flex min-h-[26px] items-center gap-[8px]" style={{ marginBottom: 8 }}>
      <h2 id={id} className="m-0" style={{ ...v4type.sec, color: color.label }}>
        {children}
      </h2>
      {right && <div className="ml-auto flex items-center">{right}</div>}
    </div>
  )
}

// ---- step bar -------------------------------------------------------------------------------------------------------

/**
 * Where a lesson stands, as its steps: one short bar per step. Passed steps are solid text color, the current one
 * outlined, the rest a faint track. Ink and white only (green stays for a passed check on the island and panel).
 */
export function StepBar({ done, total, width = 160, label }: { done: number; total: number; width?: number; label?: string }): ReactNode {
  const n = Math.max(1, Math.min(total, 24))
  const d = Math.max(0, Math.min(done, n))
  return (
    <div role="img" aria-label={label ?? `Step ${Math.min(d + 1, n)} of ${n}`} className="flex items-center" style={{ width, gap: 3 }}>
      {Array.from({ length: n }, (_, i) => (
        <span
          key={i}
          className="block flex-1"
          style={{
            height: 4,
            borderRadius: radius2.round,
            background: i < d ? color.text : i === d ? 'transparent' : fill.hairline,
            boxShadow: i === d ? `inset 0 0 0 1px ${fill.ring}` : undefined
          }}
        />
      ))}
    </div>
  )
}

// ---- rows ---------------------------------------------------------------------------------------------------------

/** A list row with no box: hover lays a soft wash under it and the press dips it on the house spring. */
export function Row({ children, onClick, label, style, data }: { children: ReactNode; onClick?: () => void; label?: string; style?: CSSProperties; data?: Record<string, string> }): ReactNode {
  if (!onClick)
    return (
      <div className="flex items-center gap-[12px]" style={{ padding: '8px 10px', ...style }} {...data}>
        {children}
      </div>
    )
  return (
    <motion.button
      type="button"
      aria-label={label}
      onClick={onClick}
      initial="rest"
      animate="rest"
      whileHover="hover"
      whileTap="press"
      variants={{ rest: { scale: 1, transition: spring }, hover: { scale: 1 }, press: { scale: press.scale, transition: spring } }}
      className="relative flex w-full cursor-pointer items-center gap-[12px] text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid"
      style={{ padding: '8px 10px', borderRadius: radius2.row, outlineColor: color.text, ...style }}
      {...data}
    >
      <motion.span
        aria-hidden
        variants={{ rest: { opacity: 0, transition: fade.tint }, hover: { opacity: 1, transition: fade.tint }, press: { opacity: 1, transition: fade.press } }}
        className="pointer-events-none absolute inset-0"
        style={{ background: surface.rowHover, borderRadius: 'inherit' }}
      />
      {children}
    </motion.button>
  )
}

/** A quiet text action ("See all"), chrome: neutral, never a hue. */
export function TextAction({ children, onClick }: { children: ReactNode; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="mg-press relative flex cursor-pointer items-center gap-[2px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ height: 26, padding: '0 8px', borderRadius: radius2.control, fontSize: type2.xs, color: color.label, outlineColor: color.text }}>
      {children}
    </button>
  )
}

/** A calm empty state: the bonsai's place, one line, one action. */
export function Empty({ mark, title, line, action }: { mark?: ReactNode; title: string; line?: string; action?: ReactNode }): ReactNode {
  return (
    <div className="flex flex-col items-center text-center" style={{ padding: '72px 24px', gap: 10 }}>
      {mark}
      <span className="font-semibold" style={{ fontSize: type2.lg, color: color.text, marginTop: mark ? 6 : 0 }}>
        {title}
      </span>
      {line && <span style={{ fontSize: type2.sm, color: color.label, maxWidth: 360 }}>{line}</span>}
      {action && <div style={{ marginTop: 10 }}>{action}</div>}
    </div>
  )
}

/**
 * The one "this row opens something" mark (redraft round 3: every clickable list reads the same on every page). Put it
 * last inside a <Row onClick>: it rides the Row's rest / hover / press variants, so it wakes up with the row.
 */
export function RowChevron(): ReactNode {
  return (
    <motion.span
      aria-hidden
      className="relative flex shrink-0 items-center"
      variants={{ rest: { opacity: 0.45, x: 0 }, hover: { opacity: 1, x: 2 }, press: { opacity: 1, x: 2 } }}
      transition={spring}
      style={{ color: color.label }}
    >
      <ChevronRight size={16} strokeWidth={1.8} />
    </motion.span>
  )
}

// =====================================================================================================================
// v4: the wide row-and-table pages (Adrian's ui-next mock, Nov 23-24; core/theme.ts `v4`, `v4c`, `v4type`).
//
//   PageFrame    a page's own scroll area and its 1040 column, 44 under the shell's top bar, 40 px gutters (24 narrow)
//   PageHeader   the page's title (32 / 700), its actions on the right, an optional one-line lede under it
//   Section      a quiet section label (12.5 / 550), an optional count and a quiet link on the right ("Browse plans >")
//   TwoCol       Home / Progress: a 684 main column and a 316 rail with one hairline; the rail drops under a 900 frame
//   Columns      Settings: two columns of groups 56 apart; one column under a 760 frame
//   Rows/ListRow a list with hairlines between rows (44 tall, 50 with a cover, 33 / 48 in a rail), hover wash, chevron
//   Table        a full-width table: head 32, rows 46, hairlines, first column flush left
//   Stats, Bar, Tag, PassedMark, ProgressRing   numbers on one line with hairlines, a 4 px bar, a quiet tag, the marks
//
// A page opts in by rendering <PageFrame>: the shell then hides its own (legacy) title for that page, so a page owns
// its title, its actions and its lede. Brand: green only for passed (Bar `passed`, Tag `passed`, PassedMark), pastels
// only on option chips (never here), one primary per surface (the page's, not these).
// =====================================================================================================================

/** The v4 gutter: 40, or 24 once the frame is under 760 (styles.css, container query on .mg-v4-frame). */
const V4_GUTTER = `var(--v4-gutter, ${v4.page.gutter}px)`
/** The column's full width (content + both gutters). */
export const V4_W = v4.page.w + 2 * v4.page.gutter

/**
 * A v4 page: its own scroll area (so it works whether the shell's body scrolls or not) holding the 1040 column,
 * centered in the main area, top-anchored 44 under the top bar.
 */
export function PageFrame({ children, top = v4.page.top, bottom = v4.page.bottom, style, data }: { children: ReactNode; top?: number; bottom?: number; style?: CSSProperties; data?: Record<string, string | boolean | undefined> }): ReactNode {
  return (
    <div data-v4-frame className="mg-v4-frame h-full min-h-0 w-full overflow-y-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: `${v4c.track} transparent` }} {...data}>
      <div data-v4-column className="flex w-full flex-col" style={{ maxWidth: V4_W, marginInline: 'auto', paddingInline: V4_GUTTER, paddingTop: top, paddingBottom: bottom, ...style }}>
        {children}
      </div>
    </div>
  )
}

/** A v4 page title: 32 / 700, the page's actions on its right, a one-line lede under it. */
export function PageHeader({ title, lede, caption, right, wrap = false }: { title: ReactNode; lede?: ReactNode; /** = lede */ caption?: ReactNode; right?: ReactNode; /** Wrap a long title onto a second line instead of cutting it with an ellipsis (a plan page beside its picture). */ wrap?: boolean }): ReactNode {
  const line = lede ?? caption
  return (
    <header data-v4-header className="flex flex-col">
      <div className="flex min-w-0 items-center gap-[16px]" style={{ minHeight: 38 }}>
        <h1 className={wrap ? 'm-0 min-w-0 line-clamp-2 break-words' : 'm-0 min-w-0 truncate'} style={{ ...v4type.title, color: color.text }}>
          {title}
        </h1>
        {right && (
          <div data-no-drag className="ml-auto flex shrink-0 items-center gap-[10px]">
            {right}
          </div>
        )}
      </div>
      {line && (
        <p className="m-0" style={{ ...v4type.lede, color: color.label, marginTop: 6 }}>
          {line}
        </p>
      )}
    </header>
  )
}

/** A quiet text link on the right of a section label ("Browse plans >"), chrome: neutral, never a hue. */
export function SectionLink({ children, onClick }: { children: ReactNode; onClick: () => void }): ReactNode {
  return (
    <button type="button" onClick={onClick} className="mg-v4-link ml-auto inline-flex cursor-pointer items-center gap-[3px] outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid" style={{ ...v4type.sec, fontWeight: 450, color: color.label, outlineColor: color.text, borderRadius: 4 }}>
      {children}
      <ChevronRight aria-hidden size={13} strokeWidth={1.8} />
    </button>
  )
}

/** A section: its label (and count, and link), then its content. `first`: 26 above instead of 30. */
export function Section({ title, count, link, first = false, id, children, style }: { title: ReactNode; count?: number | string; link?: { label: string; onClick: () => void }; first?: boolean; id?: string; children?: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <section aria-labelledby={id} className="flex flex-col" style={style}>
      <div className="flex items-center" style={{ marginTop: first ? v4.sec.first : v4.sec.top, marginBottom: v4.sec.bottom, minHeight: 18 }}>
        <h2 id={id} className="m-0" style={{ ...v4type.sec, color: color.label }}>
          {title}
          {count != null && <span style={{ fontWeight: 450, color: color.faint, marginLeft: 6 }}>{count}</span>}
        </h2>
        {link && <SectionLink onClick={link.onClick}>{link.label}</SectionLink>}
      </div>
      {children}
    </section>
  )
}

/** Home / Progress: a 684 main column and a 316 rail with one hairline; one column (rail under) in a narrow frame. */
export function TwoCol({ main, rail }: { main: ReactNode; rail: ReactNode }): ReactNode {
  return (
    <div data-v4-two className="mg-v4-two">
      <div data-v4-main className="flex min-w-0 flex-col">
        {main}
      </div>
      <aside data-v4-rail className="mg-v4-rail flex min-w-0 flex-col">
        {rail}
      </aside>
    </div>
  )
}

/** Settings: two columns of groups 56 apart (one under a 760 frame). */
export function Columns({ children }: { children: ReactNode }): ReactNode {
  return (
    <div data-v4-columns className="mg-v4-cols">
      {children}
    </div>
  )
}

/** A list of ListRows with a hairline between each (none around the hovered one). */
export function Rows({ children, label, style }: { children: ReactNode; label?: string; style?: CSSProperties }): ReactNode {
  return (
    <div role="list" aria-label={label} className="mg-v4-rows flex flex-col" style={style}>
      {children}
    </div>
  )
}

export type RowSize = 'row' | 'cover' | 'rail' | 'railTall'
const ROW_H: Record<RowSize, number> = { row: v4.row.h, cover: v4.row.cover, rail: v4.row.rail, railTall: v4.row.railTall }

/**
 * A v4 list row: no box, 8 px in (and 8 out, so its text lines up with the section label), a wash on hover and when
 * `current`. With `onClick` it is a button and ends in the ghost chevron (`chevron={false}` drops it).
 */
export function ListRow({ children, onClick, label, size = 'row', current = false, chevron = true, style, data }: { children: ReactNode; onClick?: () => void; label?: string; size?: RowSize; current?: boolean; chevron?: boolean; style?: CSSProperties; data?: Record<string, string> }): ReactNode {
  const rail = size === 'rail' || size === 'railTall'
  const base: CSSProperties = {
    ...(rail ? { fontSize: 13.5, lineHeight: '18px' } : v4type.body),
    minHeight: ROW_H[size],
    padding: `0 ${v4.row.padX}px`,
    margin: `0 -${v4.row.padX}px`,
    gap: rail ? 10 : 12,
    borderRadius: v4.radius.row,
    color: color.text,
    ...style
  }
  const cls = `mg-v4-row${current ? ' mg-v4-row-on' : ''} flex items-center`
  if (!onClick)
    return (
      <div role="listitem" className={cls} style={base} {...data}>
        {children}
      </div>
    )
  return (
    <button type="button" role="listitem" aria-label={label} aria-current={current || undefined} onClick={onClick} className={`${cls} mg-v4-row-btn cursor-pointer text-left outline-offset-2 focus-visible:outline-2 focus-visible:outline-solid`} style={{ ...base, outlineColor: color.text }} {...data}>
      {children}
      {chevron && <RowChev />}
    </button>
  )
}

/** The ghost chevron that ends a row that opens something (it wakes up with the row's hover, styles.css). */
export function RowChev(): ReactNode {
  return (
    <span aria-hidden className="mg-v4-chev ml-auto flex shrink-0 items-center" style={{ color: v4c.ghost }}>
      <ChevronRight size={14} strokeWidth={1.8} />
    </span>
  )
}

/** A row's name: 14 / 550 ink, one line. */
export function RowName({ children, style }: { children: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <span className="min-w-0 truncate" style={{ ...v4type.row, color: color.text, ...style }}>
      {children}
    </span>
  )
}

/** A row's quiet meta: 13 muted, tabular numbers, one line. */
export function RowMeta({ children, style }: { children: ReactNode; style?: CSSProperties }): ReactNode {
  return (
    <span className="shrink-0 truncate" style={{ ...v4type.meta, color: color.label, ...style }}>
      {children}
    </span>
  )
}

export type Column<T> = {
  key: string
  label: ReactNode
  /** px, or a CSS width ('30%'); the rest share what is left. */
  width?: number | string
  align?: 'left' | 'right'
  cell: (row: T) => ReactNode
}

/**
 * A v4 table (Notion table view): head 32 (12.5 muted), rows 46, a hairline under each, the first column flush left.
 * `onRow` makes each row open something (hover wash, Enter / Space); `current` washes one row; `fixed` = table-layout
 * fixed with ellipsis (give the columns widths).
 */
export function Table<T>({ columns, rows, rowKey, onRow, current, fixed = false, label, rowLabel, head = true, style }: { columns: Column<T>[]; rows: T[]; rowKey: (r: T) => string; onRow?: (r: T) => void; current?: (r: T) => boolean; fixed?: boolean; label?: string; rowLabel?: (r: T) => string; head?: boolean; style?: CSSProperties }): ReactNode {
  return (
    <table aria-label={label} className={`mg-v4-tbl${fixed ? ' mg-v4-tbl-fx' : ''}`} style={style}>
      <colgroup>
        {columns.map((c) => (
          <col key={c.key} style={{ width: c.width }} />
        ))}
      </colgroup>
      {head && (
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" style={{ textAlign: c.align ?? 'left' }}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
      )}
      <tbody>
        {rows.map((r) => (
          <tr
            key={rowKey(r)}
            className={`${onRow ? 'mg-v4-tr-btn' : ''}${current?.(r) ? ' mg-v4-tr-on' : ''}`}
            tabIndex={onRow ? 0 : undefined}
            aria-label={onRow ? rowLabel?.(r) : undefined}
            onClick={onRow ? () => onRow(r) : undefined}
            onKeyDown={
              onRow
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onRow(r)
                    }
                  }
                : undefined
            }
          >
            {columns.map((c) => (
              <td key={c.key} style={{ textAlign: c.align ?? 'left' }}>
                {c.cell(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Numbers on one line with hairlines between (no tiles): `sm` is the rail's size. */
export function Stats({ items, size = 'md', style }: { items: Array<{ value: ReactNode; unit?: ReactNode; label: ReactNode }>; size?: 'md' | 'sm'; style?: CSSProperties }): ReactNode {
  const sm = size === 'sm'
  return (
    <div data-v4-stats className="flex" style={style}>
      {items.map((s, i) => (
        <div key={i} className={sm ? 'flex-none' : 'min-w-0 flex-1'} style={{ padding: `0 ${sm ? 15 : 20}px`, paddingLeft: i === 0 ? 0 : undefined, borderLeft: i === 0 ? undefined : `1px solid ${v4c.hair2}` }}>
          <b className="block whitespace-nowrap" style={{ ...(sm ? v4type.statSm : v4type.stat), color: color.text }}>
            {s.value}
            {s.unit && <small style={{ fontSize: sm ? 12.5 : 14, fontWeight: 550, color: color.label, letterSpacing: 0, marginLeft: 2 }}>{s.unit}</small>}
          </b>
          <span className="block whitespace-nowrap" style={{ fontSize: sm ? 12 : 12.5, lineHeight: '16px', color: color.label }}>
            {s.label}
          </span>
        </div>
      ))}
    </div>
  )
}

/** A 4 px bar: ink on the track; `passed` (a skill mastered) is the only green one. `value` is 0..1. */
export function Bar({ value, width, passed = false, label }: { value: number; width?: number | string; passed?: boolean; label?: string }): ReactNode {
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0))
  return (
    <span role="img" aria-label={label ?? `${Math.round(v * 100)} percent`} className="block shrink-0 overflow-hidden" style={{ width, height: 4, borderRadius: 2, background: v4c.track }}>
      <span className="block h-full" style={{ width: `${v * 100}%`, borderRadius: 2, background: passed ? color.green : color.text }} />
    </span>
  )
}

/** A quiet tag (a skill, a tool): `passed` is green-tinted (passed only), `out` an outline, `plain` the gray fill. */
export function Tag({ children, tone = 'plain' }: { children: ReactNode; tone?: 'plain' | 'passed' | 'out' }): ReactNode {
  const bg = tone === 'plain' ? v4c.fill2 : tone === 'passed' ? 'var(--c-green-tint)' : 'transparent'
  return (
    <span className="inline-flex shrink-0 items-center whitespace-nowrap" style={{ ...v4type.tag, height: 20, padding: '0 6px', borderRadius: v4.radius.tag, background: bg, color: tone === 'passed' ? 'var(--c-green-text)' : tone === 'out' ? color.label : color.text, boxShadow: tone === 'out' ? `inset 0 0 0 1px ${v4c.hair2}` : undefined }}>
      {children}
    </span>
  )
}

/** The passed tick: a green disc with an ink check (green only means passed). */
export function PassedMark({ size = 16 }: { size?: number }): ReactNode {
  return (
    <span aria-label="Passed" role="img" className="inline-grid shrink-0 place-items-center" style={{ width: size, height: size, borderRadius: '50%', background: color.green }}>
      <Check size={Math.round(size * 0.62)} strokeWidth={3} style={{ color: 'var(--c-on-green)' }} />
    </span>
  )
}

/** A lesson in progress: the ink ring with its center dot; `todo` the ghost ring. */
export function ProgressRing({ todo = false, size = 16 }: { todo?: boolean; size?: number }): ReactNode {
  return (
    <span aria-hidden className="relative inline-block shrink-0" style={{ width: size, height: size, borderRadius: '50%', boxShadow: `inset 0 0 0 1.6px ${todo ? v4c.ghost : color.text}` }}>
      {!todo && <span className="absolute" style={{ inset: Math.round(size * 0.31), borderRadius: '50%', background: color.text }} />}
    </span>
  )
}

// ---- the sidebar's own list (Settings swaps the app sidebar for its own: "one sidebar on screen") ------------------

export type SidebarItem = { id: string; label: string; icon: LucideIcon }
export type SidebarList = {
  /** The row at the top that goes back to the app sidebar ("Settings" with a back arrow). */
  back: { label: string; onClick: () => void }
  groups: Array<{ label?: string; items: SidebarItem[] }>
  /** Pinned to the foot (About). */
  foot?: SidebarItem[]
  active: string
  onPick: (id: string) => void
}

/**
 * While a page shows its own list (Settings), the shell's sidebar renders it instead of the app's pages. A page sets it
 * while it is on show and clears it when it leaves: `useEffect(() => { setSidebarList(list); return () => setSidebarList(null) }, [...])`.
 */
export const useSidebarList = create<{ list: SidebarList | null }>(() => ({ list: null }))
export const setSidebarList = (list: SidebarList | null): void => useSidebarList.setState({ list })

// ---- the top bar's breadcrumb ---------------------------------------------------------------------------------------

/**
 * The shell's top bar shows the page's name; a page that goes deeper adds its trail after it ("Settings / General",
 * "Library / Intro to Blender"). Set it while the deeper view is on show, clear it (null) when it leaves. `page` says
 * whose trail it is, so a hidden page's trail never shows on another page.
 */
export const useCrumbs = create<{ page: string | null; trail: string[] }>(() => ({ page: null, trail: [] }))
export const setCrumbs = (page: string, trail: string[] | null): void => useCrumbs.setState(trail ? { page, trail } : { page: null, trail: [] })

/** The top bar over every page (44 tall, Notion's): the breadcrumb, the last part in text color; drags the window. */
export function TopBar({ crumbs, right }: { crumbs: string[]; right?: ReactNode }): ReactNode {
  return (
    <div data-drag data-v4-top className="flex shrink-0 items-center" style={{ height: v4.top, gap: 6, padding: '0 14px 0 18px' }}>
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center" style={{ ...v4type.crumb, color: color.label }}>
        {crumbs.map((c, i) =>
          i === crumbs.length - 1 ? (
            <span key={i} aria-current="page" className="truncate" style={{ fontWeight: 500, color: color.text }}>
              {c}
            </span>
          ) : (
            <span key={i} className="flex shrink-0 items-center">
              {c}
              <span aria-hidden style={{ color: v4c.ghost, margin: '0 6px' }}>
                /
              </span>
            </span>
          )
        )}
      </nav>
      {right && (
        <div data-no-drag className="ml-auto flex items-center gap-[6px]">
          {right}
        </div>
      )}
    </div>
  )
}

// ---- the sidebar's Plans and Recent (fed by the data lane once the ui-v4 contract lands) ---------------------------

export type SidebarPlan = { id: string; title: string; done: number; total: number; onOpen?: () => void }
export type SidebarRecent = { id: string; title: string; passed: boolean; onOpen?: () => void }
/**
 * The learner's plans and recent lessons for the sidebar. Until the ui-v4 contract (activity, plans) is wired, plans
 * stay empty (the section hides) and Recent comes from the library's lessons (Sidebar.tsx). A page or a data store can
 * fill these: `setSidebarFeed({ plans })`.
 */
export const useSidebarFeed = create<{ plans: SidebarPlan[] | null; recent: SidebarRecent[] | null }>(() => ({ plans: null, recent: null }))
export const setSidebarFeed = (feed: Partial<{ plans: SidebarPlan[] | null; recent: SidebarRecent[] | null }>): void => useSidebarFeed.setState(feed)
