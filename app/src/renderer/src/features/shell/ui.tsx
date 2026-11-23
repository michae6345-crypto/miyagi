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
import { ChevronRight } from 'lucide-react'
import { motion } from 'motion/react'
import type { CSSProperties, ReactNode } from 'react'
import { color, elevation, fill, highlight, layout, radius2, surface, type2, typeScale } from '../../core/theme'
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
export const PANEL: CSSProperties = {
  backgroundColor: 'var(--l-raised)',
  backgroundImage: 'radial-gradient(ellipse 70% 60% at 50% 0%, transparent 0%, var(--l-raised) 100%), radial-gradient(var(--d-dot) 1px, transparent 1.4px)',
  backgroundSize: '100% 100%, 20px 20px',
  backgroundPosition: '0 0, 10px 10px',
  borderRadius: layout.pane.radius,
  boxShadow: `${highlight.card}, inset 0 0 0 1px var(--l-edge), ${elevation.pane}`
}

/**
 * A card on the pane (gallery tiles, ask boxes, Settings-style groups): one tone step up, a 1 px border and the faintest
 * top edge, radius 12 (layout.radius.card). No drop shadow in dark, a soft two-layer lift in light.
 */
export const CARD: CSSProperties = {
  background: 'var(--l-overlay)',
  borderRadius: layout.radius.card,
  boxShadow: `${highlight.card}, inset 0 0 0 1px var(--l-border), ${elevation.tile}`
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
const TITLE_LEAD = (layout.page.titleRow - parseInt(typeScale.pageTitle.lineHeight)) / 2
const HEAD_TOP = layout.page.top - layout.pane.inset - TITLE_LEAD
const HEAD_TOP_FULL = layout.page.topFull - layout.pane.inset - TITLE_LEAD

/**
 * The page header (the shell renders it above every page but Home): the title and the page's own actions, on the same
 * column as the page below it (its left edge is the content's left edge at every width). The strip above the title
 * drags the window; the title's top is 80 from the window's top (52 in full screen), the line Home's bonsai sits on.
 * The title row is 36 tall; the header ends layout.page.titleGap (24) under the title's line, and the page's column
 * starts layout.page.bodyTop (8) below that, so the first section sits 32 under the title on every page.
 */
export function PageHeader({ title, caption: sub, right }: { title: ReactNode; caption?: ReactNode; right?: ReactNode }): ReactNode {
  return (
    <header
      data-drag
      data-page-header
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
          <h1 className="m-0 shrink-0" style={{ ...typeScale.pageTitle, color: color.text }}>
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
      <h2 id={id} className="m-0" style={{ ...typeScale.section, color: color.label }}>
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
