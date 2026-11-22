/**
 * Feature: shell. The one page column every shell page sits in (layout spec, Nov 22: "one shared container for every
 * page"). Before this, each page set its own width and most were pinned left, so the content's left edge moved from
 * page to page and a full-screen window left 400 to 900 px empty on the right.
 *
 *   PageColumn   centered in the content panel (margin 0 auto inside the panel, not the window), top-anchored (never
 *                centered vertically, even in full screen), 40 px gutters (24 when the panel is narrower than 760)
 *   width        'page' 720 (Settings, Account, Progress) or 'wide' 1040 (the Skills grid), gutters included. Progress
 *                is lists since redraft round 3 (the graphs moved to Skills), so it takes the reading column, not the wide
 *                one: only Skills changes the left edge when you switch pages.
 *   FORM_MAX     long text inside a column caps at 560 and stays left-aligned: the column centers, the text inside it
 *                never does. Grouped rows (Settings, Account) fill the column, so their edges match page to page.
 *
 * Vertical rhythm (spec §4): 24 from the header to the first block, 40 between sections, 64 at the bottom.
 * PAGE_COLUMN says which width each page uses, so the page title row (Shell.tsx Header) can share the same column and
 * left edge: `columnBox(PAGE_COLUMN[page])`.
 */
import type { CSSProperties, ReactNode } from 'react'

export type ColumnWidth = 'page' | 'wide'

/** Outer width of the column, gutters included (so 640 / 960 of content at the 40 px gutter). */
export const COLUMN_MAX: Record<ColumnWidth, number> = { page: 720, wide: 1040 }
/** Gutters: 40, and 24 once the panel is under 760 wide. */
export const GUTTER = 40
export const GUTTER_NARROW = 24
export const GUTTER_BREAK = 760
/** Long text inside a column: left-aligned, capped. */
export const FORM_MAX = 560
/** Spacing between a page's sections, and its bottom padding (spec §4). */
export const SECTION_GAP = 40
export const PAGE_TOP = 24
export const PAGE_BOTTOM = 64

/** Which column each shell page uses (Home and Lessons belong to features/library; listed so the header can follow). */
export const PAGE_COLUMN = { home: 'page', lessons: 'page', skills: 'wide', progress: 'page', settings: 'page', account: 'page' } as const satisfies Record<string, ColumnWidth>

/** The column's box: centered, capped, with the gutter as padding. The gutter narrows through a container query. */
export function columnBox(width: ColumnWidth = 'page'): CSSProperties {
  return { width: '100%', maxWidth: COLUMN_MAX[width], marginInline: 'auto' }
}

/**
 * A page's column. Put it inside an element with `@container` (every page root here is one), so the gutter follows the
 * panel's width rather than the window's. The gutter classes are literal (Tailwind only sees whole class names):
 * px-[24px] is GUTTER_NARROW, @min-[760px] is GUTTER_BREAK and px-[40px] is GUTTER.
 */
export function PageColumn({ width = 'page', gap, top = PAGE_TOP, bottom = PAGE_BOTTOM, children, style, data }: { width?: ColumnWidth; gap?: number; top?: number; bottom?: number; children: ReactNode; style?: CSSProperties; data?: Record<string, string | boolean | undefined> }): ReactNode {
  return (
    <div data-page-column={width} className="px-[24px] @min-[760px]:px-[40px] flex flex-col" style={{ ...columnBox(width), paddingTop: top, paddingBottom: bottom, gap, ...style }} {...data}>
      {children}
    </div>
  )
}
